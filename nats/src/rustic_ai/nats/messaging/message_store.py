"""NATS message store using JetStream for durable storage and KV for ID lookups."""

import asyncio
import datetime
import logging
import os
from typing import Callable, List, Optional
import uuid

from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.nats.messaging.connection_manager import NATSBackendConfig
from rustic_ai.nats.messaging.retry_utils import execute_with_retry


def _sanitize(name: str) -> str:
    """Sanitize a name for use in NATS stream/bucket/consumer names.
    NATS allows only [a-zA-Z0-9_-] in names."""
    return name.replace(":", "_").replace(".", "_").replace("$", "_")


def _js_subject(topic: str) -> str:
    """Get the JetStream subject for a topic."""
    return f"persist.{_sanitize(topic)}"


def _stream_name(topic: str) -> str:
    """Get the JetStream stream name for a topic."""
    return f"MSGS_{_sanitize(topic)}"


def _kv_bucket_name(namespace: str) -> str:
    """Get the KV bucket name for a namespace."""
    return f"msg-cache-{_sanitize(namespace)}"


class NATSMessageStore:
    """Manages NATS JetStream message storage and KV retrieval operations."""

    def __init__(self, js, run_async: Callable, config: Optional[NATSBackendConfig] = None):
        """
        Initialize the message store.

        Args:
            js: JetStream context
            run_async: Sync bridge callable (run_async(coro, timeout) -> result)
            config: Optional configuration for retry behavior
        """
        self._js = js
        self._run_async = run_async
        self._config = config
        self._streams: dict = {}  # sanitized topic -> True (lazy cache)
        self._kv_buckets: dict = {}  # sanitized namespace -> KV handle
        self.message_ttl = int(os.environ.get("RUSTIC_AI_NATS_MSG_TTL", config.message_ttl if config else 3600))

    def _ensure_stream(self, topic: str) -> None:
        """Lazily create JetStream stream for a topic."""
        sanitized = _sanitize(topic)
        if sanitized in self._streams:
            return

        def operation():
            self._run_async(self._ensure_stream_async(topic))
            self._streams[sanitized] = True

        execute_with_retry(f"Ensure stream for {topic}", operation, self._config)

    async def _ensure_stream_async(self, topic: str) -> None:
        import nats.js.api

        stream_name = _stream_name(topic)
        subject = _js_subject(topic)

        try:
            await self._js.stream_info(stream_name)
        except Exception:
            try:
                await self._js.add_stream(
                    nats.js.api.StreamConfig(
                        name=stream_name,
                        subjects=[subject],
                        max_age=float(self.message_ttl),
                    )
                )
            except Exception as e:
                # Stream might have been created by a concurrent call - check again
                try:
                    await self._js.stream_info(stream_name)
                except Exception:
                    raise e

    def _ensure_kv_bucket(self, namespace: str) -> object:
        """Lazily create KV bucket for a namespace and return it."""
        sanitized = _sanitize(namespace)
        if sanitized in self._kv_buckets:
            return self._kv_buckets[sanitized]

        def operation():
            kv = self._run_async(self._ensure_kv_bucket_async(namespace))
            self._kv_buckets[sanitized] = kv
            return kv

        return execute_with_retry(f"Ensure KV bucket for {namespace}", operation, self._config)

    async def _ensure_kv_bucket_async(self, namespace: str):
        import nats.js.api

        bucket_name = _kv_bucket_name(namespace)
        try:
            return await self._js.create_key_value(
                nats.js.api.KeyValueConfig(
                    bucket=bucket_name,
                    ttl=float(self.message_ttl),
                )
            )
        except Exception:
            # Bucket may already exist
            try:
                return await self._js.key_value(bucket_name)
            except Exception as e:
                raise e

    def store_message(
        self, namespace: str, topic: str, message: Message, pubsub_publish: Callable[[str, str], None]
    ) -> None:
        """
        Store a message durably (JetStream + KV) and publish for real-time notification.

        Args:
            namespace: The namespace of the message.
            topic: The topic to which the message belongs.
            message: The message object to be stored.
            pubsub_publish: Function to publish message via core NATS pub/sub
        """
        message_json = message.to_json()
        data = message_json.encode("utf-8")

        def store_operation():
            logging.debug(
                "Persisting NATS message namespace=%s topic=%s message_id=%s sender=%s",
                namespace,
                topic,
                message.id,
                message.sender.id if message.sender else None,
            )
            self._ensure_stream(topic)
            kv = self._ensure_kv_bucket(namespace)
            self._run_async(self._store_message_async(topic, namespace, message, message_json, data, kv))
            logging.debug(
                "Publishing realtime NATS notification namespace=%s topic=%s message_id=%s",
                namespace,
                topic,
                message.id,
            )
            pubsub_publish(topic, message_json)
            logging.debug(f"Message {message.id} stored for topic {topic}")

        try:
            execute_with_retry(f"Store message {message.id} to topic {topic}", store_operation, self._config)
        except Exception as e:
            logging.error(f"Message storage failed for message {message.id} on topic {topic}: {e}")
            raise

    async def _store_message_async(self, topic, namespace, message, message_json, data, kv) -> None:
        subject = _js_subject(topic)
        # Store in JetStream for ordered topic retrieval
        ack = await self._js.publish(subject, data)
        # Store in KV for ID-based lookup
        await kv.put(str(message.id), data)
        logging.debug(
            "Persisted NATS message namespace=%s topic=%s subject=%s message_id=%s stream=%s seq=%s",
            namespace,
            topic,
            subject,
            message.id,
            getattr(ack, "stream", None),
            getattr(ack, "seq", None),
        )

    def get_messages_for_topic(self, topic: str) -> List[Message]:
        """Retrieve all messages for a given topic, sorted by message ID."""

        def get_operation():
            self._ensure_stream(topic)
            raw_msgs = self._run_async(self._fetch_messages_async(topic))
            messages = [Message.from_json(m.data.decode("utf-8")) for m in raw_msgs]
            return sorted(messages, key=lambda msg: msg.id)

        return execute_with_retry(f"Get messages for topic {topic}", get_operation, self._config)

    def get_messages_for_topic_since(self, topic: str, msg_id_since: int) -> List[Message]:
        """Retrieve messages for a topic after a given message ID's timestamp."""

        def get_operation():
            self._ensure_stream(topic)
            timestamp_ms = GemstoneID.from_int(msg_id_since).timestamp + 1
            opt_start_time = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0, tz=datetime.timezone.utc)
            raw_msgs = self._run_async(
                self._fetch_messages_async(
                    topic,
                    deliver_policy_str="by_start_time",
                    opt_start_time=opt_start_time,
                )
            )
            all_messages = [Message.from_json(m.data.decode("utf-8")) for m in raw_msgs]
            # In-memory filter: keep messages with timestamp >= timestamp_ms
            messages = [msg for msg in all_messages if msg.timestamp >= timestamp_ms]
            return sorted(messages, key=lambda msg: msg.id)

        return execute_with_retry(
            f"Get messages for topic {topic} since {msg_id_since}", get_operation, self._config
        )

    def get_next_message_for_topic_since(self, topic: str, last_message_id: int) -> Optional[Message]:
        """Retrieve the next message for a topic after a given message ID."""

        def get_operation():
            messages = self.get_messages_for_topic_since(topic, last_message_id)
            return messages[0] if messages else None

        return execute_with_retry(
            f"Get next message for topic {topic} since {last_message_id}", get_operation, self._config
        )

    def get_messages_by_id(self, namespace: str, msg_ids: List[int]) -> List[Message]:
        """Retrieve messages by their IDs from the KV bucket."""
        if not msg_ids:
            return []

        def get_operation():
            kv = self._ensure_kv_bucket(namespace)
            return self._run_async(self._get_messages_by_id_async(kv, msg_ids))

        return execute_with_retry(f"Get messages by IDs for namespace {namespace}", get_operation, self._config)

    async def _get_messages_by_id_async(self, kv, msg_ids: List[int]) -> List[Message]:
        import nats.js.errors

        result = []
        for msg_id in msg_ids:
            try:
                entry = await kv.get(str(msg_id))
                if entry and entry.value:
                    result.append(Message.from_json(entry.value.decode("utf-8")))
            except nats.js.errors.KeyNotFoundError:
                pass
            except Exception as e:
                logging.warning(f"Error retrieving message {msg_id} from KV: {e}")
        return result

    async def _fetch_messages_async(
        self,
        topic: str,
        deliver_policy_str: str = "all",
        opt_start_time: Optional[datetime.datetime] = None,
    ) -> list:
        """Fetch messages from JetStream stream using a temporary pull consumer."""
        import nats.errors
        import nats.js.api
        import nats.js.errors

        stream_name = _stream_name(topic)
        subject = _js_subject(topic)

        # Get stream info to determine message count
        try:
            stream_info = await self._js.stream_info(stream_name)
        except Exception:
            return []

        # For deliver_all, skip if 0 messages
        if deliver_policy_str == "all" and stream_info.state.messages == 0:
            return []

        consumer_name = f"query-{uuid.uuid4().hex[:12]}"

        deliver_policy = nats.js.api.DeliverPolicy.ALL
        if deliver_policy_str == "by_start_time":
            deliver_policy = nats.js.api.DeliverPolicy.BY_START_TIME

        consumer_config = nats.js.api.ConsumerConfig(
            durable_name=consumer_name,
            deliver_policy=deliver_policy,
            opt_start_time=opt_start_time,
            ack_policy=nats.js.api.AckPolicy.NONE,
            filter_subject=subject,
            max_deliver=1,
        )

        try:
            psub = await self._js.pull_subscribe(
                subject,
                durable=consumer_name,
                stream=stream_name,
                config=consumer_config,
            )
        except Exception as e:
            logging.warning(f"Failed to create pull subscriber for {topic}: {e}")
            return []

        messages = []
        total = stream_info.state.messages if deliver_policy_str == "all" else None

        try:
            if total is not None and total > 0:
                # Fetch exact count for deliver_all case
                try:
                    batch = await asyncio.wait_for(psub.fetch(batch=total, timeout=5.0), timeout=10.0)
                    messages.extend(batch)
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    pass
            else:
                # For time-based queries, fetch in batches until timeout
                while True:
                    try:
                        batch = await asyncio.wait_for(psub.fetch(batch=256, timeout=1.0), timeout=5.0)
                        messages.extend(batch)
                        if len(batch) < 256:
                            break
                    except (nats.errors.TimeoutError, asyncio.TimeoutError):
                        break
        finally:
            try:
                await psub.unsubscribe()
            except Exception:
                pass
            # Clean up the temporary consumer
            try:
                await self._js.delete_consumer(stream_name, consumer_name)
            except Exception:
                pass

        return messages
