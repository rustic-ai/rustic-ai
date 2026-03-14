"""Redis pub/sub manager for handling publish/subscribe operations."""

import logging
import queue
import threading
import time
from typing import Callable, Dict, Optional, Set, Tuple, Union

import redis

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.redis.messaging.connection_manager import RedisBackendConfig
from rustic_ai.redis.messaging.exceptions import RedisConnectionFailureError
from rustic_ai.redis.messaging.retry_utils import (
    calculate_exponential_backoff,
    execute_with_retry,
)


class RedisPubSubManager:
    """
    Manages Redis pub/sub operations with retry logic, health monitoring, and per-client delivery.

    Architecture:
    - ONE pub/sub subscription per topic (redis-py limitation: only one handler per channel)
    - Internal fan-out from the single pub/sub handler to per-client work queues
    - ONE worker thread per CLIENT for sequential, ordered delivery
    - Per-client position tracked in Redis: eo:pos:{client_id}:{topic}
    """

    def __init__(
        self, client: Union[redis.StrictRedis, redis.RedisCluster], config: Optional[RedisBackendConfig] = None
    ):
        """
        Initialize the pub/sub manager.

        Args:
            client: Redis client instance
            config: Optional configuration for retry behavior
        """
        self.client = client
        self.config = config
        self.pubsub: Optional[redis.client.PubSub] = None
        self.redis_thread: Optional[threading.Thread] = None
        self.health_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        # Legacy per-topic subscriptions (client_id=None path)
        self.subscriptions: Dict[str, Callable[[Message], None]] = {}
        self.failure_callback: Optional[Callable[[Exception], None]] = None

        # Thread safety
        self.lock = threading.RLock()
        self.reconnection_lock = threading.Lock()
        self.reconnection_active = False

        # Per-client delivery: (topic, client_id) -> handler
        self._client_handlers: Dict[Tuple[str, str], Callable[[Message], None]] = {}
        # topic -> set of client_ids subscribed via per-client path
        self._topic_client_ids: Dict[str, Set[str]] = {}
        # Per-client worker infrastructure
        self._client_queues: Dict[str, queue.Queue] = {}
        self._client_workers: Dict[str, threading.Thread] = {}
        # Fanout subscription handlers (for per-client topics, we register ONE internal handler per topic)
        # Key: topic, Value: the fanout callable (already registered in pub/sub)
        self._fanout_topics: Set[str] = set()

    def setup(self) -> None:
        """Initialize pub/sub connection with retry logic."""

        def setup_operation():
            self._setup_internal()

        try:
            execute_with_retry("Pub/sub setup", setup_operation, self.config, self.shutdown_event)
        except RedisConnectionFailureError:
            if self.config and self.config.pubsub_crash_on_failure:
                raise
            else:
                logging.error("Failed to setup pub/sub connection")
                raise
        except Exception as e:
            # Convert any setup failure to RedisConnectionFailureError when crash is enabled
            if self.config and self.config.pubsub_crash_on_failure:
                raise RedisConnectionFailureError(f"Pub/sub setup failed: {e}")
            else:
                logging.error("Failed to setup pub/sub connection")
                raise

    def _setup_internal(self) -> None:
        """Internal pub/sub setup without retry logic."""
        with self.lock:
            self.pubsub = self.client.pubsub(ignore_subscribe_messages=True)
            # For fakeredis compatibility, handle case where run_in_thread might not work exactly like real redis
            try:
                self.redis_thread = self.pubsub.run_in_thread(sleep_time=0.001, daemon=True)  # type: ignore
            except AttributeError:
                # Fallback for test environments that might not have run_in_thread
                self.redis_thread = None
                logging.warning("Pub/sub run_in_thread not available, running in test mode")

        # Start health monitoring if retry is enabled and health monitoring is enabled
        # Only start if we have a config and thread is available
        should_start_monitoring = (
            self.config
            and self.config.pubsub_retry_enabled
            and self.config.pubsub_health_monitoring_enabled
            and self.redis_thread is not None
        )
        if should_start_monitoring:
            self._start_health_monitor()

        logging.info("Pub/sub connection established successfully")

    def _start_health_monitor(self) -> None:
        """Start background thread to monitor pub/sub health."""
        # Stop existing health monitor if running
        if self.health_thread and self.health_thread.is_alive():
            logging.debug("Stopping existing health monitor thread")
            # Signal it to stop by setting shutdown event temporarily
            # The thread will exit on next check

        # Clear shutdown event in case it was set during previous cleanup
        # This prevents the new monitor from exiting immediately in tests
        self.shutdown_event.clear()

        self.health_thread = threading.Thread(
            target=self._health_monitor_loop, daemon=True, name="redis-pubsub-health-monitor"
        )
        self.health_thread.start()
        logging.debug("Started new health monitor thread")

    def _health_monitor_loop(self) -> None:
        """Monitor pub/sub thread health and handle failures."""
        if not self.config:
            return

        check_interval = self.config.pubsub_health_check_interval
        initial_delay = self.config.pubsub_health_monitor_initial_delay

        # Initial delay
        if not self.shutdown_event.wait(initial_delay):
            while not self.shutdown_event.wait(check_interval):
                try:
                    # Check if pub/sub thread is alive
                    with self.lock:
                        thread_alive = self.redis_thread is not None and self.redis_thread.is_alive()

                    if not thread_alive:
                        logging.warning("Pub/sub thread died, initiating reconnection")
                        self._schedule_reconnect()
                        break

                except Exception as e:
                    logging.debug(f"Health monitor error (non-critical): {e}")
                    continue

    # =========================================================================
    # Legacy per-topic subscribe (client_id=None)
    # =========================================================================

    def subscribe(self, topic: str, handler: Callable[[Message], None], client_id: Optional[str] = None) -> None:
        """
        Subscribe to a topic with retry logic.

        When client_id is provided, uses per-client delivery with sequential processing
        and position-tracked crash recovery.

        Args:
            topic: Topic to subscribe to
            handler: Callback function for messages
            client_id: If provided, enables per-client durable delivery
        """
        if client_id is None:
            # Legacy per-topic subscribe
            execute_with_retry(
                f"Subscribe to {topic}", self._subscribe_internal, self.config, self.shutdown_event, topic, handler
            )
            with self.lock:
                self.subscriptions[topic] = handler
        else:
            # Per-client subscribe
            self._subscribe_per_client(topic, handler, client_id)

    def _subscribe_per_client(self, topic: str, handler: Callable[[Message], None], client_id: str) -> None:
        """Register a per-client subscription with sequential delivery and backlog replay."""
        with self.lock:
            # Store per-client handler
            self._client_handlers[(topic, client_id)] = handler

            # Track which clients are subscribed to this topic
            if topic not in self._topic_client_ids:
                self._topic_client_ids[topic] = set()
            self._topic_client_ids[topic].add(client_id)

            # Ensure per-client worker thread + queue exists
            if client_id not in self._client_queues:
                self._client_queues[client_id] = queue.Queue()
                worker = threading.Thread(
                    target=self._client_worker_loop,
                    args=(client_id,),
                    daemon=True,
                    name=f"redis-client-worker-{client_id[:16]}",
                )
                self._client_workers[client_id] = worker
                worker.start()

            # Subscribe topic to pub/sub fanout if first client on this topic
            needs_fanout_subscribe = topic not in self._fanout_topics

        if needs_fanout_subscribe:
            def fanout_handler(msg: Message, _topic=topic) -> None:
                self._fanout_to_clients(_topic, msg)

            execute_with_retry(
                f"Subscribe fanout to {topic}",
                self._subscribe_internal,
                self.config,
                self.shutdown_event,
                topic,
                fanout_handler,
            )
            with self.lock:
                self._fanout_topics.add(topic)

        # Replay backlog: deliver messages since last processed position
        self._replay_backlog(topic, client_id, handler)

    def _replay_backlog(self, topic: str, client_id: str, handler: Callable[[Message], None]) -> None:
        """Replay messages from last processed position for crash recovery."""
        last_id = self._load_position(client_id, topic)

        if last_id == 0:
            # No position saved — replay from beginning
            timestamp_since = 0.0
        else:
            timestamp_since = GemstoneID.from_int(last_id).timestamp

        try:
            # Use inclusive timestamp range, then filter by ID to handle same-millisecond messages
            if timestamp_since == 0.0:
                raw_messages = self.client.zrange(topic, 0, -1)
            else:
                raw_messages = self.client.zrangebyscore(topic, timestamp_since, "+inf")

            if raw_messages:
                messages = [Message.from_json(m) for m in raw_messages]  # type: ignore[union-attr]
                messages = sorted(messages, key=lambda m: m.id)
                # Filter: only messages AFTER last_id (not including it)
                backlog = [m for m in messages if m.id > last_id]
                for msg in backlog:
                    self._enqueue_for_client(client_id, topic, handler, msg)
        except Exception as e:
            logging.warning(f"Error replaying backlog for client {client_id} on topic {topic}: {e}")

    def _fanout_to_clients(self, topic: str, message: Message) -> None:
        """Fan out a message from pub/sub to all per-client queues subscribed to this topic."""
        with self.lock:
            client_ids = list(self._topic_client_ids.get(topic, set()))
            handlers = {cid: self._client_handlers.get((topic, cid)) for cid in client_ids}

        for client_id, handler in handlers.items():
            if handler is not None:
                self._enqueue_for_client(client_id, topic, handler, message.model_copy(deep=True))

    def _enqueue_for_client(
        self, client_id: str, topic: str, handler: Callable[[Message], None], message: Message
    ) -> None:
        """Enqueue a message for a specific client's worker thread."""
        with self.lock:
            q = self._client_queues.get(client_id)
        if q is not None:
            q.put((topic, handler, message))

    def _client_worker_loop(self, client_id: str) -> None:
        """Worker thread for a single client — processes messages sequentially."""
        while not self.shutdown_event.is_set():
            try:
                item = self._client_queues[client_id].get(timeout=0.5)
            except queue.Empty:
                continue
            except KeyError:
                break  # Queue removed (client unsubscribed all topics)

            topic, handler, message = item
            try:
                handler(message)
                # Handler succeeded — advance position
                self._save_position(client_id, topic, message.id)
            except Exception:
                logging.exception(
                    "Handler failed for client %s on topic %s message %s — position NOT advanced, requeueing",
                    client_id,
                    topic,
                    message.id,
                )
                # Re-enqueue so the message is retried (at-least-once semantics)
                self._enqueue_for_client(client_id, topic, handler, message)
            finally:
                self._client_queues[client_id].task_done()

    def _load_position(self, client_id: str, topic: str) -> int:
        """Load last processed message ID for a client+topic from Redis."""
        key = f"eo:pos:{client_id}:{topic}"
        try:
            val = self.client.get(key)
            if val is not None:
                return int(val)  # type: ignore[arg-type]
        except Exception as e:
            logging.warning(f"Error loading position for {client_id}/{topic}: {e}")
        return 0

    def _save_position(self, client_id: str, topic: str, message_id: int) -> None:
        """Save last processed message ID for a client+topic to Redis."""
        key = f"eo:pos:{client_id}:{topic}"
        try:
            self.client.set(key, str(message_id))
        except Exception as e:
            logging.warning(f"Error saving position for {client_id}/{topic}: {e}")

    def _subscribe_internal(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Internal subscribe without storing in subscriptions dict."""

        def _handler(redis_message: dict) -> None:
            logging.debug(f"[RedisStorage] Received message: {redis_message}")
            # Handle both bytes and string data for decode_responses compatibility
            message_data = redis_message["data"]
            if isinstance(message_data, bytes):
                message_data = message_data.decode("utf-8")
            handler(Message.from_json(message_data))

        logging.debug(f"Subscribing to topic: {topic}")
        with self.lock:
            if not self.pubsub:
                raise redis.exceptions.ConnectionError("Pub/sub connection not available")
            self.pubsub.subscribe(**{topic: _handler})

    def unsubscribe(self, topic: str, client_id: Optional[str] = None) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            client_id: If provided, unsubscribes a specific per-client subscription
        """
        if client_id is None:
            # Legacy per-topic unsubscribe
            logging.debug(f"Unsubscribing from topic: {topic}")
            with self.lock:
                self.subscriptions.pop(topic, None)

            def unsubscribe_operation():
                with self.lock:
                    if self.pubsub:
                        self.pubsub.unsubscribe(topic)
            execute_with_retry(f"Unsubscribe from {topic}", unsubscribe_operation, self.config, self.shutdown_event)
            logging.debug(f"Unsubscribed from topic: {topic}")
        else:
            self._unsubscribe_per_client(topic, client_id)

    def _unsubscribe_per_client(self, topic: str, client_id: str) -> None:
        """Remove a per-client subscription and clean up if no more clients on topic."""
        with self.lock:
            self._client_handlers.pop((topic, client_id), None)
            if topic in self._topic_client_ids:
                self._topic_client_ids[topic].discard(client_id)
                remaining_clients = self._topic_client_ids[topic]
            else:
                remaining_clients = set()

            # Check if this client still has other topic subscriptions
            client_still_has_subscriptions = any(
                k[1] == client_id for k in self._client_handlers
            )

        if not remaining_clients:
            # No more clients on this topic — unsubscribe from Redis pub/sub fanout
            with self.lock:
                self._fanout_topics.discard(topic)
                self._topic_client_ids.pop(topic, None)

            def unsubscribe_operation():
                with self.lock:
                    if self.pubsub:
                        self.pubsub.unsubscribe(topic)
            try:
                execute_with_retry(
                    f"Unsubscribe fanout from {topic}", unsubscribe_operation, self.config, self.shutdown_event
                )
            except Exception as e:
                logging.warning(f"Error unsubscribing fanout from {topic}: {e}")

        if not client_still_has_subscriptions:
            # No more subscriptions for this client — stop worker thread
            with self.lock:
                self._client_queues.pop(client_id, None)
                self._client_workers.pop(client_id, None)
            # Worker thread will exit on its own when queue is removed

    def publish(self, topic: str, message: str) -> int:
        """
        Publish a message to a topic.

        Args:
            topic: Topic to publish to
            message: Message data (JSON string)

        Returns:
            Number of subscribers that received the message
        """
        result = self.client.publish(topic, message)
        # Handle potential awaitable response
        if hasattr(result, "__await__"):
            raise RuntimeError("Unexpected awaitable from synchronous Redis client")
        return result  # type: ignore

    def _schedule_reconnect(self) -> None:
        """Schedule pub/sub reconnection with exponential backoff."""
        if not self.config or not self.config.pubsub_retry_enabled:
            return

        # Prevent multiple concurrent reconnection attempts
        with self.reconnection_lock:
            if self.reconnection_active:
                logging.debug("Reconnection already in progress")
                return
            self.reconnection_active = True

        def reconnect_with_backoff():
            assert self.config is not None  # Type guard - we checked this above
            delay = self.config.pubsub_retry_initial_delay
            max_delay = self.config.pubsub_retry_max_delay
            multiplier = self.config.pubsub_retry_multiplier
            max_attempts = self.config.pubsub_max_retry_attempts
            max_total_time = self.config.pubsub_max_retry_time
            crash_on_failure = self.config.pubsub_crash_on_failure

            start_time = time.time()
            attempt = 0

            try:
                while not self.shutdown_event.is_set():
                    attempt += 1
                    elapsed_time = time.time() - start_time

                    # Check limits
                    if attempt > max_attempts:
                        error_msg = f"Redis pub/sub reconnection failed after {max_attempts} attempts"
                        logging.error(error_msg)
                        if crash_on_failure:
                            self._trigger_critical_failure(RedisConnectionFailureError(error_msg))
                            return
                        else:
                            logging.warning("Max retry attempts exceeded, giving up")
                            return

                    if elapsed_time > max_total_time:
                        error_msg = f"Redis pub/sub reconnection failed after {elapsed_time:.1f}s"
                        logging.error(error_msg)
                        if crash_on_failure:
                            self._trigger_critical_failure(RedisConnectionFailureError(error_msg))
                            return
                        else:
                            logging.warning("Max retry time exceeded, giving up")
                            return

                    try:
                        logging.info(f"Attempting pub/sub reconnection (attempt {attempt}/{max_attempts})...")

                        # Clean up and reconnect
                        self._cleanup()
                        self._setup_internal()

                        # Re-subscribe to all topics
                        self._resubscribe_all()

                        logging.info(f"Pub/sub reconnection successful after {attempt} attempts")
                        break

                    except Exception as e:
                        logging.warning(f"Reconnection attempt {attempt} failed: {e}, retrying in {delay:.1f}s")
                        if self.shutdown_event.wait(delay):
                            break
                        # Apply exponential backoff with jitter to avoid herd reconnections
                        delay = calculate_exponential_backoff(delay, multiplier, max_delay)
            finally:
                # Clear reconnection flag
                with self.reconnection_lock:
                    self.reconnection_active = False

        # Run in background thread
        reconnect_thread = threading.Thread(target=reconnect_with_backoff, daemon=True, name="redis-pubsub-reconnect")
        reconnect_thread.start()

    def _resubscribe_all(self) -> None:
        """Re-subscribe to all previously subscribed topics."""
        with self.lock:
            subscriptions_snapshot = self.subscriptions.copy()
            fanout_topics_snapshot = set(self._fanout_topics)

        # Re-subscribe legacy per-topic subscriptions
        for topic, handler in subscriptions_snapshot.items():
            execute_with_retry(
                f"Re-subscribe to {topic}", self._subscribe_internal, self.config, self.shutdown_event, topic, handler
            )

        # Re-subscribe fanout handlers for per-client topics
        for topic in fanout_topics_snapshot:
            def fanout_handler(msg: Message, _topic=topic) -> None:
                self._fanout_to_clients(_topic, msg)

            execute_with_retry(
                f"Re-subscribe fanout to {topic}",
                self._subscribe_internal,
                self.config,
                self.shutdown_event,
                topic,
                fanout_handler,
            )

    def _trigger_critical_failure(self, exception: Exception) -> None:
        """Trigger a critical failure."""
        logging.critical(f"Critical Redis failure detected: {exception}")

        if self.failure_callback:
            self.failure_callback(exception)
        else:
            # For production, crash the process (Ray will restart)
            import os
            import signal

            logging.critical("Initiating fail-fast shutdown due to Redis connection failure")
            os.kill(os.getpid(), signal.SIGTERM)

    def _cleanup(self) -> None:
        """Clean up pub/sub connection."""
        with self.lock:
            try:
                if self.redis_thread and self.redis_thread.is_alive():
                    # Redis pub/sub threads have a stop() method
                    if hasattr(self.redis_thread, "stop"):
                        self.redis_thread.stop()  # type: ignore
                    # Wait briefly for thread to stop
                    self.redis_thread.join(timeout=1)
                if self.pubsub:
                    # Unsubscribe from all topics first to prevent event handler leaks
                    try:
                        self.pubsub.unsubscribe()
                    except Exception as e:
                        logging.debug(f"Error during unsubscribe in cleanup: {e}")
                    # Now close the pubsub connection
                    self.pubsub.close()
            except Exception as e:
                logging.warning(f"Error during pub/sub cleanup: {e}")
            finally:
                self.redis_thread = None
                self.pubsub = None

    def cleanup(self) -> None:
        """Clean up all resources."""
        # Signal shutdown
        self.shutdown_event.set()

        # Stop reconnection attempts
        with self.reconnection_lock:
            self.reconnection_active = False

        # Clean up per-client workers
        with self.lock:
            worker_threads = list(self._client_workers.values())
        for worker in worker_threads:
            if worker.is_alive():
                worker.join(timeout=1)

        # Clean up pub/sub
        self._cleanup()

        # Wait for health monitor thread
        if self.health_thread and self.health_thread.is_alive():
            self.health_thread.join(timeout=1)

        self.health_thread = None

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing."""
        self.failure_callback = callback
