"""Redis pub/sub manager for handling publish/subscribe operations."""

import logging
import threading
import time
from typing import Callable, Dict, Optional, Union

import redis

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.redis.messaging.connection_manager import RedisBackendConfig
from rustic_ai.redis.messaging.exceptions import RedisConnectionFailureError
from rustic_ai.redis.messaging.retry_utils import (
    calculate_exponential_backoff,
    execute_with_retry,
)


class RedisPubSubManager:
    """Manages Redis pub/sub operations with retry logic and health monitoring."""

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
        self.subscriptions: Dict[str, Callable[[Message], None]] = {}
        self.failure_callback: Optional[Callable[[Exception], None]] = None

        # Thread safety
        self.lock = threading.RLock()
        self.reconnection_lock = threading.Lock()
        self.reconnection_active = False

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
                # Use 10ms polling to save CPU instead of aggressive 1ms polling
                self.redis_thread = self.pubsub.run_in_thread(sleep_time=0.01, daemon=True)  # type: ignore
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

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic with retry logic.

        Args:
            topic: Topic to subscribe to
            handler: Callback function for messages
        """
        # Perform the subscription first
        execute_with_retry(
            f"Subscribe to {topic}", self._subscribe_internal, self.config, self.shutdown_event, topic, handler
        )

        # Only store subscription after successful operation
        with self.lock:
            self.subscriptions[topic] = handler

    def _subscribe_internal(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Internal subscribe without storing in subscriptions dict."""

        def _handler(redis_message: Dict) -> None:
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

    def unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe from a topic with retry logic.

        Args:
            topic: Topic to unsubscribe from
        """
        logging.debug(f"Unsubscribing from topic: {topic}")

        # Remove from subscriptions first
        with self.lock:
            self.subscriptions.pop(topic, None)

        # Unsubscribe from Redis
        def unsubscribe_operation():
            with self.lock:
                if self.pubsub:
                    self.pubsub.unsubscribe(topic)

        execute_with_retry(f"Unsubscribe from {topic}", unsubscribe_operation, self.config, self.shutdown_event)
        logging.debug(f"Unsubscribed from topic: {topic}")

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

        for topic, handler in subscriptions_snapshot.items():
            execute_with_retry(
                f"Re-subscribe to {topic}", self._subscribe_internal, self.config, self.shutdown_event, topic, handler
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

        # Clean up pub/sub
        self._cleanup()

        # Wait for health monitor thread
        if self.health_thread and self.health_thread.is_alive():
            self.health_thread.join(timeout=1)

        self.health_thread = None

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing."""
        self.failure_callback = callback
