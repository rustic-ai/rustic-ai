"""NATS pub/sub manager for handling publish/subscribe operations via core NATS."""

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from rustic_ai.core.messaging.core.dead_letter import (
    build_dead_letter_message,
    resolve_dead_letter_namespace,
    resolve_dead_letter_topic,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.nats.messaging.connection_manager import NATSBackendConfig
from rustic_ai.nats.messaging.exceptions import NATSConnectionFailureError
from rustic_ai.nats.messaging.message_store import (
    NATSMessageStore,
    _js_subject,
    _sanitize,
)
from rustic_ai.nats.messaging.retry_utils import (
    calculate_exponential_backoff,
    execute_with_retry,
)


class NATSPubSubManager:
    """
    Manages NATS pub/sub operations with health monitoring and per-client push consumers.

    Architecture:
    - Core NATS pub/sub: one subscription per topic (legacy, client_id=None path)
    - JetStream push consumers: one durable consumer per (client_id, topic) pair
      These provide ordered, exactly-once, crash-resilient delivery.
    """

    def __init__(
        self,
        client,
        js,
        run_async: Callable,
        config: Optional[NATSBackendConfig] = None,
        ensure_stream: Optional[Callable] = None,
    ):
        """
        Initialize the pub/sub manager.

        Args:
            client: NATS client instance
            js: JetStream context
            run_async: Sync bridge callable
            config: Optional configuration for retry behavior
            ensure_stream: Optional callable(topic) to ensure stream exists before creating push consumer
        """
        self._client = client
        self._js = js
        self._run_async = run_async
        self._config = config
        self._ensure_stream = ensure_stream
        self._subscriptions: Dict[str, Any] = {}  # topic -> NATS Subscription (core pub/sub)
        self._handlers: Dict[str, Callable] = {}  # topic -> Message handler (core pub/sub)
        # Per-client push consumers: (topic, client_id) -> NATS JetStream Subscription
        self._push_subscriptions: Dict[tuple, Any] = {}
        self._push_namespaces: Dict[tuple, Optional[str]] = {}
        # Per-client locks for cross-topic sequential delivery.
        # Each push consumer for a client runs its handler via run_in_executor,
        # which means handlers for different topics can race. The lock ensures
        # only one handler runs at a time per client (matching Redis/InMemory semantics).
        self._client_locks: Dict[str, threading.Lock] = {}
        self._shutdown_event = threading.Event()
        self._health_thread: Optional[threading.Thread] = None
        self._failure_callback: Optional[Callable[[Exception], None]] = None
        self._reconnection_lock = threading.Lock()
        self._reconnection_active = False
        self._lock = threading.RLock()
        self._dead_letter_store = NATSMessageStore(js, run_async, config)

    def setup(self) -> None:
        """Initialize pub/sub and start health monitoring if configured."""
        should_monitor = (
            self._config
            and self._config.pubsub_retry_enabled
            and self._config.pubsub_health_monitoring_enabled
        )
        if should_monitor:
            self._start_health_monitor()
        logging.info("NATS pub/sub manager initialized")

    def _start_health_monitor(self) -> None:
        """Start background thread to monitor NATS connection health."""
        self._shutdown_event.clear()
        self._health_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True,
            name="nats-pubsub-health-monitor",
        )
        self._health_thread.start()

    def _health_monitor_loop(self) -> None:
        """Monitor NATS connection health and trigger reconnect if needed."""
        if not self._config:
            return

        check_interval = self._config.pubsub_health_check_interval
        initial_delay = self._config.pubsub_health_monitor_initial_delay

        if not self._shutdown_event.wait(initial_delay):
            while not self._shutdown_event.wait(check_interval):
                try:
                    is_connected = self._client.is_connected
                    if not is_connected:
                        logging.warning("NATS connection lost, initiating reconnection")
                        self._schedule_reconnect()
                        break
                except Exception as e:
                    logging.debug(f"Health monitor error (non-critical): {e}")
                    continue

    # =========================================================================
    # Core pub/sub (legacy, client_id=None)
    # =========================================================================

    def subscribe(
        self,
        topic: str,
        handler: Callable[[Message], None],
        client_id: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """
        Subscribe to a topic.

        When client_id is provided, creates a durable JetStream push consumer for ordered,
        exactly-once, crash-resilient delivery.

        Args:
            topic: Topic to subscribe to
            handler: Callback function for received messages
            client_id: If provided, enables per-client durable push consumer
        """
        if client_id is None:
            # Legacy core pub/sub subscribe
            logging.debug("Subscribing NATS handler to topic=%s", topic)

            def subscribe_operation():
                self._subscribe_internal(topic, handler)

            execute_with_retry(
                f"Subscribe to {topic}", subscribe_operation, self._config, self._shutdown_event
            )

            with self._lock:
                self._handlers[topic] = handler
            logging.debug("Subscribed NATS handler to topic=%s", topic)
        else:
            # Per-client durable push consumer
            self._subscribe_push_consumer(topic, handler, client_id, namespace)

    def _subscribe_push_consumer(
        self, topic: str, handler: Callable[[Message], None], client_id: str, namespace: Optional[str]
    ) -> None:
        """
        Create a durable JetStream push consumer for per-client delivery.

        Consumer semantics:
        - DeliverPolicy.ALL: replay all messages (unacked) from stream beginning
        - AckPolicy.EXPLICIT: each message must be acked after success or dead-lettering
        - Sequential: await run_in_executor ensures one message processed at a time
        """
        consumer_name = f"eo_{_sanitize(client_id)}_{_sanitize(topic)}"
        js_subject = _js_subject(topic)

        logging.debug(
            "Creating push consumer name=%s subject=%s client_id=%s", consumer_name, js_subject, client_id
        )

        # Ensure stream exists before creating push consumer (sync call)
        if self._ensure_stream:
            self._ensure_stream(topic)

        # Get or create per-client lock for cross-topic sequential delivery
        with self._lock:
            if client_id not in self._client_locks:
                self._client_locks[client_id] = threading.Lock()
            client_lock = self._client_locks[client_id]

        async def _create_push_consumer():
            from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

            captured_handler = handler

            def locked_handler(msg: Message) -> bool:
                """Run the handler under a per-client lock for cross-topic sequential delivery."""
                with client_lock:
                    try:
                        captured_handler(msg)
                    except Exception as e:
                        logging.exception(
                            "Handler failed for client %s on topic %s message %s; dead-lettering and acknowledging",
                            client_id,
                            topic,
                            msg.id,
                        )
                        self._store_dead_letter_sync(namespace, topic, client_id, msg, e)
                        return False
                    return True

            async def push_handler(nats_msg):
                try:
                    data = nats_msg.data.decode("utf-8")
                    message = Message.from_json(data)
                    logging.debug(
                        "Push consumer received topic=%s message_id=%s consumer=%s",
                        topic,
                        message.id,
                        consumer_name,
                    )
                    loop = asyncio.get_event_loop()
                    # AWAIT ensures ack fires AFTER handler / dead-letter handling completes.
                    # locked_handler ensures cross-topic sequential delivery per client.
                    await loop.run_in_executor(None, locked_handler, message)
                except Exception as e:
                    logging.exception(
                        "Error in push consumer callback topic=%s consumer=%s: %s", topic, consumer_name, e
                    )
                finally:
                    await nats_msg.ack()

            # Create the durable push consumer (manual_ack=True → explicit ack/nak)
            sub = await self._js.subscribe(
                js_subject,
                durable=consumer_name,
                cb=push_handler,
                config=ConsumerConfig(
                    ack_policy=AckPolicy.EXPLICIT,
                    deliver_policy=DeliverPolicy.ALL,
                    ack_wait=30.0,  # Fallback redelivery if nak is not sent (e.g. process crash)
                ),
                manual_ack=True,
            )
            return sub

        try:
            sub = self._run_async(_create_push_consumer())
            with self._lock:
                self._push_subscriptions[(topic, client_id)] = sub
                self._push_namespaces[(topic, client_id)] = namespace
            logging.debug(
                "Created push consumer name=%s topic=%s client_id=%s", consumer_name, topic, client_id
            )
        except Exception as e:
            logging.error(
                "Failed to create push consumer name=%s topic=%s: %s", consumer_name, topic, e
            )
            raise

    def _subscribe_internal(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Internal subscribe implementation for legacy core pub/sub."""
        captured_handler = handler

        async def async_handler(msg):
            try:
                data = msg.data.decode("utf-8")
                message = Message.from_json(data)
                logging.debug(
                    "Received live NATS message topic=%s message_id=%s published_topic=%s sender=%s",
                    topic,
                    message.id,
                    message.topic_published_to,
                    message.sender.id if message.sender else None,
                )
                # Run the sync handler in a thread pool so it doesn't block the event loop.
                # This is critical: the sync handler may call run_async() to schedule further
                # async work on this same event loop. If we called it directly here (in the
                # event loop), that would deadlock.
                # We do NOT await so the event loop stays free immediately; the handler
                # runs concurrently in the thread pool.
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, captured_handler, message)
            except Exception as e:
                logging.error(f"Error handling NATS message on topic {topic}: {e}")

        sub = self._run_async(self._client.subscribe(topic, cb=async_handler))
        with self._lock:
            self._subscriptions[topic] = sub
        logging.debug("Created NATS subscription topic=%s sid=%s", topic, getattr(sub, "_id", None))

    # =========================================================================
    # Unsubscribe
    # =========================================================================

    def unsubscribe(self, topic: str, client_id: Optional[str] = None) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            client_id: If provided, unsubscribes the per-client push consumer
        """
        if client_id is None:
            # Legacy core pub/sub unsubscribe
            logging.debug(f"Unsubscribing from topic: {topic}")

            with self._lock:
                self._handlers.pop(topic, None)
                sub = self._subscriptions.pop(topic, None)

            if sub:
                try:
                    self._run_async(sub.unsubscribe())
                except Exception as e:
                    logging.warning(f"Error unsubscribing from {topic}: {e}")

            logging.debug(f"Unsubscribed from topic: {topic}")
        else:
            # Per-client push consumer unsubscribe
            with self._lock:
                sub = self._push_subscriptions.pop((topic, client_id), None)
                self._push_namespaces.pop((topic, client_id), None)
                # Clean up client lock if no more push subscriptions for this client
                has_remaining = any(k[1] == client_id for k in self._push_subscriptions)
                if not has_remaining:
                    self._client_locks.pop(client_id, None)

            if sub:
                try:
                    self._run_async(sub.unsubscribe())
                    logging.debug(
                        "Unsubscribed push consumer topic=%s client_id=%s", topic, client_id
                    )
                except Exception as e:
                    logging.warning(
                        "Error unsubscribing push consumer topic=%s client_id=%s: %s", topic, client_id, e
                    )

    # =========================================================================
    # Publish
    # =========================================================================

    def publish(self, topic: str, message_json: str) -> None:
        """
        Publish a message via core NATS pub/sub (fire-and-forget).

        Args:
            topic: Topic to publish to
            message_json: Message data as JSON string
        """
        data = message_json.encode("utf-8")
        try:
            logging.debug("Publishing live NATS message topic=%s bytes=%s", topic, len(data))
            self._run_async(self._client.publish(topic, data))
            logging.debug("Published live NATS message topic=%s", topic)
        except Exception as e:
            logging.warning(f"Error publishing to {topic}: {e}")

    def _store_dead_letter_sync(
        self,
        namespace: Optional[str],
        topic: str,
        client_id: str,
        message: Message,
        error: Exception,
    ) -> None:
        dead_letter_topic = resolve_dead_letter_topic(topic, namespace)
        dead_letter_namespace = resolve_dead_letter_namespace(topic, namespace)
        if topic == dead_letter_topic:
            logging.error(
                "Dead-letter handler failed for client %s message %s; skipping recursive dead-letter publish",
                client_id,
                message.id,
            )
            return

        try:
            dead_letter_message = build_dead_letter_message(
                backend_name=self.__class__.__name__,
                client_id=client_id,
                original_topic=topic,
                original_message=message,
                error=error,
            )
            self._dead_letter_store.store_message(
                dead_letter_namespace,
                dead_letter_topic,
                dead_letter_message,
                self.publish,
            )
        except Exception:
            logging.exception(
                "Failed to publish dead-letter message for client %s topic %s message %s",
                client_id,
                topic,
                message.id,
            )

    # =========================================================================
    # Reconnect / recovery
    # =========================================================================

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        if not self._config or not self._config.pubsub_retry_enabled:
            return

        with self._reconnection_lock:
            if self._reconnection_active:
                logging.debug("Reconnection already in progress")
                return
            self._reconnection_active = True

        def reconnect_with_backoff():
            assert self._config is not None
            delay = self._config.pubsub_retry_initial_delay
            max_delay = self._config.pubsub_retry_max_delay
            multiplier = self._config.pubsub_retry_multiplier
            max_attempts = self._config.pubsub_max_retry_attempts
            max_total_time = self._config.pubsub_max_retry_time
            crash_on_failure = self._config.pubsub_crash_on_failure

            start_time = time.time()
            attempt = 0

            try:
                while not self._shutdown_event.is_set():
                    attempt += 1
                    elapsed = time.time() - start_time

                    if attempt > max_attempts:
                        error_msg = f"NATS pub/sub reconnection failed after {max_attempts} attempts"
                        logging.error(error_msg)
                        if crash_on_failure:
                            self._trigger_critical_failure(NATSConnectionFailureError(error_msg))
                        return

                    if elapsed > max_total_time:
                        error_msg = f"NATS pub/sub reconnection failed after {elapsed:.1f}s"
                        logging.error(error_msg)
                        if crash_on_failure:
                            self._trigger_critical_failure(NATSConnectionFailureError(error_msg))
                        return

                    try:
                        logging.info(f"Attempting NATS reconnection (attempt {attempt}/{max_attempts})...")
                        self._resubscribe_all()
                        logging.info(f"NATS reconnection successful after {attempt} attempts")
                        break
                    except Exception as e:
                        logging.warning(f"Reconnection attempt {attempt} failed: {e}, retrying in {delay:.1f}s")
                        if self._shutdown_event.wait(delay):
                            break
                        delay = calculate_exponential_backoff(delay, multiplier, max_delay)
            finally:
                with self._reconnection_lock:
                    self._reconnection_active = False

        reconnect_thread = threading.Thread(
            target=reconnect_with_backoff, daemon=True, name="nats-pubsub-reconnect"
        )
        reconnect_thread.start()

    def _resubscribe_all(self) -> None:
        """Re-subscribe to all previously subscribed topics (core pub/sub only)."""
        with self._lock:
            handlers_snapshot = self._handlers.copy()

        for topic, handler in handlers_snapshot.items():
            execute_with_retry(
                f"Re-subscribe to {topic}", self._subscribe_internal, self._config, self._shutdown_event, topic, handler
            )

    def _trigger_critical_failure(self, exception: Exception) -> None:
        """Trigger a critical failure response."""
        logging.critical(f"Critical NATS failure: {exception}")

        if self._failure_callback:
            self._failure_callback(exception)
        else:
            import os
            import signal

            logging.critical("Initiating fail-fast shutdown due to NATS connection failure")
            os.kill(os.getpid(), signal.SIGTERM)

    def cleanup(self) -> None:
        """Clean up all subscriptions and stop monitoring."""
        self._shutdown_event.set()

        with self._reconnection_lock:
            self._reconnection_active = False

        # Unsubscribe legacy core pub/sub topics
        with self._lock:
            topics = list(self._subscriptions.keys())

        for topic in topics:
            self.unsubscribe(topic)

        # Unsubscribe per-client push consumers
        with self._lock:
            push_keys = list(self._push_subscriptions.keys())

        for topic, client_id in push_keys:
            self.unsubscribe(topic, client_id=client_id)

        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=1)

        self._health_thread = None

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing."""
        self._failure_callback = callback
