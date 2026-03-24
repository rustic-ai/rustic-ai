import threading
import time
import uuid

import pytest

from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging import InMemoryMessagingBackend
from rustic_ai.core.messaging.backend.in_memory_backend import MemoryStore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    MessageConstants,
    Priority,
)
from rustic_ai.core.utils import GemstoneGenerator

from ..core.base_test_backend import BaseTestBackendABC
from rustic_ai.testing.messaging.base_test_delivery_guarantees import (
    BaseTestBackendDeliveryGuarantees,
)


class TestInMemoryBackend(BaseTestBackendABC):
    @pytest.fixture
    def backend(self):
        """Fixture that returns an instance of InMemoryStorage."""
        inmem = InMemoryMessagingBackend()
        yield inmem
        inmem.cleanup()

    # No need to re-implement the test methods from TestStorageABC unless there's a specific behavior
    # of InMemoryStorage that needs to be tested differently.


class TestInMemoryDeliveryGuarantees(BaseTestBackendDeliveryGuarantees):
    @pytest.fixture
    def backend(self):
        inmem = InMemoryMessagingBackend()
        yield inmem
        inmem.cleanup()

    def test_backlog_replay(self, backend, generator, topic, namespace):
        super().test_backlog_replay(backend, generator, topic, namespace)

    def test_crash_recovery(self, backend, generator, topic, namespace):
        super().test_crash_recovery(backend, generator, topic, namespace)

    def test_handler_failure_dead_letters_and_advances_position(self, backend, generator, topic, namespace):
        super().test_handler_failure_dead_letters_and_advances_position(backend, generator, topic, namespace)


def _make_message(topic: str, generator: GemstoneGenerator, payload: dict) -> Message:
    return Message(
        topics=topic,
        sender=AgentTag(id="senderId", name="sender"),
        format=MessageConstants.RAW_JSON_FORMAT,
        payload=payload,
        id_obj=generator.get_id(Priority.NORMAL),
    )


class TestInMemoryClientQueueBehavior:
    def test_failed_message_is_dead_lettered_without_replaying_later_successes(self):
        backend = InMemoryMessagingBackend()
        generator = GemstoneGenerator(1)
        topic = f"inmem_topic_{uuid.uuid4().hex[:8]}"
        namespace = f"inmem_ns_{uuid.uuid4().hex[:8]}"
        client_id = "concurrent_failure_client"
        first_handler_started = threading.Event()
        allow_first_failure = threading.Event()
        later_messages_event = threading.Event()
        dead_letter_event = threading.Event()
        replay_event = threading.Event()
        lock = threading.Lock()
        successful_deliveries: list[int] = []
        dead_letter_ids: list[int] = []
        replayed: list[int] = []

        def dead_letter_handler(msg: Message):
            with lock:
                dead_letter_ids.append(msg.payload["original_message_id"])
                dead_letter_event.set()

        def handler(msg: Message):
            if msg.payload["n"] == 0:
                first_handler_started.set()
                assert allow_first_failure.wait(timeout=5.0)
                raise RuntimeError("blocked failure")
            with lock:
                successful_deliveries.append(msg.id)
                if len(successful_deliveries) >= 2:
                    later_messages_event.set()

        def replay_handler(msg: Message):
            with lock:
                replayed.append(msg.id)
                replay_event.set()

        backend.subscribe(GuildTopics.DEAD_LETTER_QUEUE, dead_letter_handler, namespace=namespace)
        backend.subscribe(topic, handler, client_id=client_id, namespace=namespace)

        messages = [_make_message(topic, generator, {"n": i}) for i in range(3)]
        first_publish_thread = threading.Thread(
            target=backend.store_message,
            args=(namespace, topic, messages[0]),
            daemon=True,
        )
        first_publish_thread.start()

        assert first_handler_started.wait(timeout=5.0), "Expected first handler invocation to block"
        backend.store_message(namespace, topic, messages[1])
        backend.store_message(namespace, topic, messages[2])
        allow_first_failure.set()
        first_publish_thread.join(timeout=5.0)
        assert not first_publish_thread.is_alive(), "Expected blocked publisher thread to finish"

        assert dead_letter_event.wait(timeout=5.0), "Expected failed message to be dead-lettered"
        assert later_messages_event.wait(timeout=5.0), "Expected later queued messages to keep flowing"

        backend.unsubscribe(GuildTopics.DEAD_LETTER_QUEUE)
        backend.unsubscribe(topic, client_id=client_id)
        backend.subscribe(topic, replay_handler, client_id=client_id, namespace=namespace)

        extra = _make_message(topic, generator, {"n": 99})
        backend.store_message(namespace, topic, extra)
        assert replay_event.wait(timeout=5.0), "Expected new message after re-subscribe"
        time.sleep(0.2)

        with lock:
            assert successful_deliveries == [messages[1].id, messages[2].id]
            assert dead_letter_ids == [messages[0].id]
            assert replayed == [extra.id]

        backend.unsubscribe(topic, client_id=client_id)
        backend.cleanup()


class TestInMemoryCleanup:
    def test_cleanup_unregisters_instance_handlers_from_memory_store(self):
        backend_a = InMemoryMessagingBackend()
        backend_b = InMemoryMessagingBackend()
        generator = GemstoneGenerator(1)
        topic = f"cleanup_topic_{uuid.uuid4().hex[:8]}"
        namespace = f"cleanup_ns_{uuid.uuid4().hex[:8]}"
        stale_handler_called = threading.Event()

        def stale_handler(_: Message):
            stale_handler_called.set()

        backend_a.subscribe(topic, stale_handler)
        store = MemoryStore.get_instance()
        assert backend_a.subscriber_id in store.get_subscribers(topic)
        assert backend_a.subscriber_id in store.get_callback_handlers(topic)

        backend_a.cleanup()

        assert backend_a.subscriber_id not in store.get_subscribers(topic)
        assert backend_a.subscriber_id not in store.get_callback_handlers(topic)

        backend_b.store_message(namespace, topic, _make_message(topic, generator, {"n": 1}))

        assert not stale_handler_called.wait(timeout=0.2), "Cleanup should remove stale singleton handlers"

        backend_b.cleanup()
