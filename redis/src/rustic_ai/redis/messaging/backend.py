import logging
import os
import socket
import threading
import time
from typing import Awaitable, Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field
import redis

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils import GemstoneID


class RedisConnectionFailureError(Exception):
    """Raised when Redis connection cannot be established after maximum retries."""

    pass


class RedisBackendConfig(BaseModel):
    host: str
    port: int
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    ssl: bool = Field(default=False)
    ssl_certfile: Optional[str] = Field(default=None)
    ssl_keyfile: Optional[str] = Field(default=None)
    ssl_ca_certs: Optional[str] = Field(default=None)
    is_cluster: bool = Field(default=False)

    # Connection keepalive and stability settings
    socket_keepalive: bool = Field(default=True)
    socket_keepalive_options: Optional[Dict[int, int]] = Field(
        default_factory=lambda: {
            socket.TCP_KEEPIDLE: 300,  # Start keepalive after 5 minutes of inactivity
            socket.TCP_KEEPINTVL: 60,  # Send keepalive probes every 60 seconds
            socket.TCP_KEEPCNT: 3,  # Close connection after 3 failed probes
        }
    )
    health_check_interval: int = Field(default=30)  # Redis-level health check interval
    socket_connect_timeout: int = Field(default=10)  # Connection timeout
    socket_timeout: int = Field(default=30)  # Operation timeout

    # Pub/sub retry and reconnection settings
    pubsub_retry_enabled: bool = Field(default=True)
    pubsub_retry_initial_delay: float = Field(default=1.0)  # Initial retry delay in seconds
    pubsub_retry_max_delay: float = Field(default=60.0)  # Maximum retry delay in seconds
    pubsub_retry_multiplier: float = Field(default=2.0)  # Backoff multiplier
    pubsub_health_check_interval: float = Field(default=10.0)  # Check pub/sub health every N seconds

    # Fail-fast settings for Ray workers
    pubsub_max_retry_attempts: int = Field(default=5)  # Max retry attempts before crashing
    pubsub_max_retry_time: float = Field(default=300.0)  # Max total retry time (5 minutes) before crashing
    pubsub_crash_on_failure: bool = Field(default=True)  # Crash the app when retries are exhausted

    # Health monitoring settings
    pubsub_health_monitoring_enabled: bool = Field(default=True)  # Enable health monitoring (can disable for tests)
    pubsub_health_monitor_initial_delay: float = Field(default=1.0)  # Initial delay before starting health monitoring


class RedisMessagingBackend(MessagingBackend):
    def __init__(self, redis_client: Union[redis.StrictRedis, RedisBackendConfig, dict]) -> None:
        """
        Initialize with a Redis client.

        Args:
            redis_client: A Redis client instance.
        """
        self.r: redis.StrictRedis | redis.RedisCluster  # type: ignore[attr-ignored]
        self._config: Optional[RedisBackendConfig] = None
        self._pubsub_thread: Optional[threading.Thread] = None
        self._pubsub_health_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._subscriptions: Dict[str, Callable[[Message], None]] = {}
        self._initialization_complete = False
        self._failure_callback: Optional[Callable[[Exception], None]] = None

        # Reconnection state management
        self._reconnection_in_progress = threading.Lock()
        self._reconnection_active = False

        if isinstance(redis_client, dict):
            redis_client = RedisBackendConfig(**redis_client)

        if isinstance(redis_client, RedisBackendConfig):
            self._config = redis_client
            if redis_client.is_cluster:
                self.r = redis.RedisCluster(
                    host=redis_client.host,
                    port=redis_client.port,
                    username=redis_client.username,
                    password=redis_client.password,
                    ssl=redis_client.ssl,
                    ssl_certfile=redis_client.ssl_certfile,
                    ssl_keyfile=redis_client.ssl_keyfile,
                    ssl_ca_certs=redis_client.ssl_ca_certs,
                    # Connection keepalive settings
                    socket_keepalive=redis_client.socket_keepalive,
                    socket_keepalive_options=redis_client.socket_keepalive_options,
                    health_check_interval=redis_client.health_check_interval,
                    socket_connect_timeout=redis_client.socket_connect_timeout,
                    socket_timeout=redis_client.socket_timeout,
                )  # type: ignore
            else:
                self.r = redis.StrictRedis(
                    host=redis_client.host,
                    port=redis_client.port,
                    username=redis_client.username,
                    password=redis_client.password,
                    ssl=redis_client.ssl,
                    ssl_certfile=redis_client.ssl_certfile,
                    ssl_keyfile=redis_client.ssl_keyfile,
                    ssl_ca_certs=redis_client.ssl_ca_certs,
                    # Connection keepalive settings
                    socket_keepalive=redis_client.socket_keepalive,
                    socket_keepalive_options=redis_client.socket_keepalive_options,
                    health_check_interval=redis_client.health_check_interval,
                    socket_connect_timeout=redis_client.socket_connect_timeout,
                    socket_timeout=redis_client.socket_timeout,
                )
        elif isinstance(redis_client, redis.StrictRedis):
            self.r = redis_client
        else:
            raise ValueError("Invalid Redis client")  # pragma: no cover

        # Mark initialization as complete before setting up pub/sub
        self._initialization_complete = True
        self._setup_pubsub()

    def _setup_pubsub(self, is_reconnection: bool = False) -> None:
        """Initialize pub/sub connection with retry logic.

        Args:
            is_reconnection: True if this is being called during a reconnection attempt.
        """
        try:
            self.p = self.r.pubsub(ignore_subscribe_messages=True)
            self.redis_thread = self.p.run_in_thread(sleep_time=0.001, daemon=True)

            # Start health monitoring if retry is enabled and health monitoring is enabled
            if self._config and self._config.pubsub_retry_enabled and self._config.pubsub_health_monitoring_enabled:
                self._start_pubsub_health_monitor()

            logging.info("Pub/sub connection established successfully")

            # Clear reconnection flag on successful connection
            if is_reconnection:
                with self._reconnection_in_progress:
                    self._reconnection_active = False

        except Exception as e:
            logging.error(f"Failed to setup pub/sub: {e}")

            # Only start retry logic if:
            # 1. Initialization is complete (to avoid race conditions)
            # 2. Retry is enabled
            # 3. We're not already in a reconnection context (to prevent recursive calls)
            if (
                self._initialization_complete
                and self._config
                and self._config.pubsub_retry_enabled
                and not is_reconnection
            ):
                self._schedule_pubsub_reconnect()
            elif self._config and self._config.pubsub_crash_on_failure:
                # If retry is disabled but crash_on_failure is enabled, crash immediately
                raise RedisConnectionFailureError(f"Initial Redis pub/sub connection failed: {e}")
            else:
                # Re-raise the original exception if no special handling is configured
                raise

    def _start_pubsub_health_monitor(self) -> None:
        """Start background thread to monitor pub/sub health."""
        # Always stop existing health monitor first to prevent multiple threads
        if self._pubsub_health_thread and self._pubsub_health_thread.is_alive():
            logging.debug("Stopping existing health monitor thread")
            # The thread will stop naturally when _shutdown_event is set or new setup happens

        self._pubsub_health_thread = threading.Thread(
            target=self._pubsub_health_monitor_loop, daemon=True, name="redis-pubsub-health-monitor"
        )
        self._pubsub_health_thread.start()
        logging.debug("Started new health monitor thread")

    def _pubsub_health_monitor_loop(self) -> None:
        """Monitor pub/sub thread health and handle thread failures."""
        if not self._config:
            return

        check_interval = self._config.pubsub_health_check_interval

        # Add initial delay to let initialization complete
        initial_delay = self._config.pubsub_health_monitor_initial_delay if self._config else 1.0
        if not self._shutdown_event.wait(initial_delay):
            while not self._shutdown_event.wait(check_interval):
                try:
                    # Only monitor pub/sub thread health - Redis client handles connection health
                    if not hasattr(self, "redis_thread") or not self.redis_thread.is_alive():
                        logging.warning("Pub/sub thread died, initiating reconnection")
                        self._schedule_pubsub_reconnect()
                        break

                    # No need for ping() - Redis client health_check_interval handles connection health
                    # We only care about pub/sub thread being alive

                except Exception as e:
                    logging.debug(f"Health monitor error (non-critical): {e}")
                    # Don't break the loop for non-critical errors
                    continue

    def _schedule_pubsub_reconnect(self) -> None:
        """Schedule pub/sub reconnection with exponential backoff and fail-fast limits."""
        if not self._config or not self._config.pubsub_retry_enabled:
            return

        # Prevent multiple concurrent reconnection attempts
        with self._reconnection_in_progress:
            if self._reconnection_active:
                logging.debug("Reconnection already in progress, skipping new attempt")
                return
            self._reconnection_active = True

        config = self._config  # Type guard for mypy

        def reconnect_with_backoff():
            delay = config.pubsub_retry_initial_delay
            max_delay = config.pubsub_retry_max_delay
            multiplier = config.pubsub_retry_multiplier
            max_attempts = config.pubsub_max_retry_attempts
            max_total_time = config.pubsub_max_retry_time
            crash_on_failure = config.pubsub_crash_on_failure

            start_time = time.time()
            attempt = 0

            try:
                while not self._shutdown_event.is_set():
                    attempt += 1
                    elapsed_time = time.time() - start_time

                    # Check if we've exceeded limits
                    if attempt > max_attempts:
                        error_msg = f"Redis pub/sub reconnection failed after {max_attempts} attempts"
                        logging.error(error_msg)
                        if crash_on_failure:
                            # For fail-fast behavior, we need to crash the main process, not just this thread
                            self._trigger_critical_failure(RedisConnectionFailureError(error_msg))
                            return
                        else:
                            logging.warning("Max retry attempts exceeded, giving up on pub/sub reconnection")
                            return

                    if elapsed_time > max_total_time:
                        error_msg = (
                            f"Redis pub/sub reconnection failed after {elapsed_time:.1f}s (max: {max_total_time}s)"
                        )
                        logging.error(error_msg)
                        if crash_on_failure:
                            # For fail-fast behavior, we need to crash the main process, not just this thread
                            self._trigger_critical_failure(RedisConnectionFailureError(error_msg))
                            return
                        else:
                            logging.warning("Max retry time exceeded, giving up on pub/sub reconnection")
                            return

                    try:
                        logging.info(f"Attempting pub/sub reconnection (attempt {attempt}/{max_attempts})...")

                        # Clean up old connection
                        self._cleanup_pubsub()

                        # Re-establish connection (pass is_reconnection=True to prevent recursive calls)
                        self._setup_pubsub(is_reconnection=True)

                        # Re-subscribe to all topics
                        self._resubscribe_all()

                        logging.info(f"Pub/sub reconnection successful after {attempt} attempts")
                        break

                    except Exception as e:
                        logging.warning(f"Pub/sub reconnection attempt {attempt} failed: {e}, retrying in {delay:.1f}s")
                        if self._shutdown_event.wait(delay):
                            break
                        delay = min(delay * multiplier, max_delay)
            finally:
                # Always clear the reconnection flag when done, regardless of success or failure
                with self._reconnection_in_progress:
                    self._reconnection_active = False

        # Run reconnection in background thread
        reconnect_thread = threading.Thread(target=reconnect_with_backoff, daemon=True, name="redis-pubsub-reconnect")
        reconnect_thread.start()

    def _trigger_critical_failure(self, exception: Exception) -> None:
        """Trigger a critical failure that should crash the application."""
        logging.critical(f"Critical Redis failure detected: {exception}")

        # If a failure callback is set, use it (for testing or custom handling)
        if self._failure_callback:
            self._failure_callback(exception)
        else:
            # For production use, we need to crash the process
            # This will cause Ray to restart the worker
            import os
            import signal

            logging.critical("Initiating fail-fast shutdown due to Redis connection failure")
            os.kill(os.getpid(), signal.SIGTERM)

    def _cleanup_pubsub(self) -> None:
        """Clean up existing pub/sub connection."""
        try:
            if hasattr(self, "redis_thread") and self.redis_thread.is_alive():
                self.redis_thread.stop()
                self.redis_thread.join(timeout=1)
            if hasattr(self, "p"):
                self.p.close()
        except Exception as e:
            logging.warning(f"Error during pub/sub cleanup: {e}")

    def _resubscribe_all(self) -> None:
        """Re-subscribe to all previously subscribed topics."""
        for topic, handler in self._subscriptions.items():
            try:
                self._subscribe_internal(topic, handler)
                logging.debug(f"Re-subscribed to topic: {topic}")
            except Exception as e:
                logging.error(f"Failed to re-subscribe to topic {topic}: {e}")

    def _subscribe_internal(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Internal subscribe method without storing in subscriptions dict."""

        def _handler(redis_message: Dict) -> None:
            logging.debug(f"[RedisStorage] Received message: {redis_message}")
            handler(Message.from_json(redis_message["data"]))

        logging.debug(f"Subscribing to topic: {topic}")
        self.p.subscribe(**{topic: _handler})

    @staticmethod
    def _get_msg_key(namespace: str, message_id: int):
        return f"msg:{namespace}:{message_id}"

    def store_message(self, namespace: str, topic: str, message: Message) -> None:
        """
        Store a message in Redis, sorted by timestamp.
        It also creates a secondary index for direct ID lookups with .

        Args:
            namespace: The namespace of the message.
            topic (str): The topic to which the message belongs.
            message (Message): The message object to be stored.
        """
        message_json = message.to_json()

        # Create a secondary index for direct ID lookup
        # Use a key pattern like "msg:ID" to store the message
        msg_key = self._get_msg_key(namespace, message.id)
        # Set an expiration time for the secondary index entry
        message_ttl = int(os.environ.get("RUSTIC_AI_REDIS_MSG_TTL", 3600))
        self.r.set(msg_key, message_json, ex=message_ttl)

        # Using the timestamp as the score for sorting in Redis sorted set.
        self.r.zadd(topic, {message_json: message.timestamp})
        self.r.publish(topic, message_json)

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """
        Retrieve all messages for a given topic.

        Args:
            topic (str): The topic to retrieve messages for.

        Returns:
            List[Message]: A list of messages for the given topic.
        """
        raw_messages = self.r.zrange(topic, 0, -1)

        if isinstance(raw_messages, Awaitable):  # runtime check
            raise RuntimeError("Unexpected awaitable from synchronous Redis client")

        messages = [Message.from_json(raw_message) for raw_message in raw_messages]
        return sorted(messages, key=lambda msg: msg.id)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """
        Retrieve all messages for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            msg_id_since (int): The ID of the message since which to retrieve messages.

        Returns:
            List[Message]: A list of messages for the given topic since the given message ID.
        """
        # Retrieve the timestamp corresponding to the given message ID.
        timestamp_since = self._get_timestamp_for_id(msg_id_since) + 1
        raw_messages = self.r.zrangebyscore(topic, timestamp_since, "+inf")

        if isinstance(raw_messages, Awaitable):  # runtime check
            raise RuntimeError("Unexpected awaitable from synchronous Redis client")

        messages = [Message.from_json(raw_message) for raw_message in raw_messages]
        return sorted(messages, key=lambda msg: msg.id)

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """
        Retrieve the next message for a given topic since a given message ID.

        Args:
            topic (str): The topic to retrieve messages for.
            last_message_id (int): The ID of the last message received.

        Returns:
            Optional[Message]: The next message for the given topic since the given message ID.
        """
        timestamp_since = self._get_timestamp_for_id(last_message_id) + 1
        raw_messages = self.r.zrangebyscore(topic, timestamp_since, "+inf", start=0, num=1)

        if isinstance(raw_messages, Awaitable):  # runtime check
            raise RuntimeError("Unexpected awaitable from synchronous Redis client")

        return Message.from_json(raw_messages[0]) if raw_messages else None

    def load_subscribers(self, namespace: str) -> Dict[str, Set[str]]:
        """
        Load all subscribers from Redis.

        Returns:
            Dict[str, Set[str]]: A dictionary mapping topics to sets of client IDs.
        """
        # TBD: Implement the logic to load subscribers.
        return {}

    def _get_timestamp_for_id(self, msg_id: int) -> float:
        """
        Helper method to retrieve the timestamp for a given message ID.

        Args:
            msg_id (int): The ID of the message.

        Returns:
            float: The timestamp of the message.
        """
        # Implement logic to retrieve the timestamp from a message ID.
        # This method needs to be adjusted based on how the timestamp is stored or derived from the message ID.
        return GemstoneID.from_int(msg_id).timestamp

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """
        Subscribe to a topic and handle incoming messages.

        Args:
            topic (str): The topic to subscribe to.
            handler (Callable[[Message], None]): The handler function to handle incoming messages.
        """
        # Store subscription for reconnection
        self._subscriptions[topic] = handler

        # Perform the actual subscription
        self._subscribe_internal(topic, handler)

    def unsubscribe(self, topic: str) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic (str): The topic to unsubscribe from.
        """
        logging.debug(f"Unsubscribing from topic: {topic}")
        # Remove from subscriptions tracking
        self._subscriptions.pop(topic, None)
        # Unsubscribe from Redis
        self.p.unsubscribe(topic)
        logging.debug(f"Unsubscribed from topic: {topic}")

    def set_failure_callback(self, callback: Optional[Callable[[Exception], None]]) -> None:
        """Set a custom failure callback for testing purposes."""
        self._failure_callback = callback

    def cleanup(self) -> None:
        """
        Clean up the Redis storage.
        """
        # Signal shutdown to all background threads
        self._shutdown_event.set()

        # Reset reconnection state to prevent any new reconnection attempts
        with self._reconnection_in_progress:
            self._reconnection_active = False

        # Clean up pub/sub connection
        self._cleanup_pubsub()

        # Wait for health monitor thread to finish
        if self._pubsub_health_thread and self._pubsub_health_thread.is_alive():
            self._pubsub_health_thread.join(timeout=1)

        # Clear the health monitor thread reference
        self._pubsub_health_thread = None

        # Close Redis connection
        self.r.close()

    def supports_subscription(self) -> bool:
        return True

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """
        Retrieve messages by their IDs using Redis pipelines for efficiency.

        Args:
            namespace: The namespace of the messages.
            msg_ids (List[int]): A list of message IDs to retrieve.

        Returns:
            List[Message]: A list of Message objects corresponding to the provided IDs.
        """
        if not msg_ids or len(msg_ids) == 0:
            return []

        result = []

        # Use Redis pipeline to batch operations for efficiency
        with self.r.pipeline() as pipe:
            # For each message ID, get the message from the secondary index
            for msg_id in msg_ids:
                pipe.get(self._get_msg_key(namespace, msg_id))

            # Execute pipeline and process results
            raw_messages = pipe.execute()

        # Convert raw messages to Message objects
        for raw_message in raw_messages:
            if raw_message:
                result.append(Message.from_json(raw_message))
        return result
