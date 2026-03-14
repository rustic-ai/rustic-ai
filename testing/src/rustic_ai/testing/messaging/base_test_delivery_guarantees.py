"""Abstract base class for testing backend delivery guarantees (per-client subscriptions)."""

from abc import ABC
import threading
import time

import pytest

from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    MessageConstants,
    Priority,
)
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


def _make_message(topic: str, generator: GemstoneGenerator, payload: dict) -> Message:
    return Message(
        topics=topic,
        sender=AgentTag(id="senderId", name="sender"),
        format=MessageConstants.RAW_JSON_FORMAT,
        payload=payload,
        id_obj=generator.get_id(Priority.NORMAL),
    )


class BaseTestBackendDeliveryGuarantees(ABC):
    """
    Abstract base class for testing per-client delivery guarantees.

    Backends that support per-client durable subscriptions (Redis, NATS) should
    subclass this and implement all 4 tests. The InMemory backend only runs
    test_exactly_once_delivery; it skips crash_recovery and handler_failure
    since it has no persistent position tracking.
    """

    @pytest.fixture
    def generator(self):
        return GemstoneGenerator(1)

    @pytest.fixture
    def backend(self) -> MessagingBackend:
        raise NotImplementedError("Override in subclass.")

    @pytest.fixture
    def topic(self) -> str:
        return "dg_topic"

    @pytest.fixture
    def namespace(self) -> str:
        return "dg_namespace"

    def test_exactly_once_delivery(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, namespace: str
    ):
        """
        Subscribe a client, store 5 messages, verify handler called exactly 5 times,
        each message ID appearing exactly once.
        """
        received_ids = []
        lock = threading.Lock()
        done_event = threading.Event()

        def handler(msg: Message):
            with lock:
                received_ids.append(msg.id)
                if len(received_ids) >= 5:
                    done_event.set()

        backend.subscribe(topic, handler, client_id="eo_client")

        msgs = [_make_message(topic, generator, {"n": i}) for i in range(5)]
        for msg in msgs:
            backend.store_message(namespace, topic, msg)
            time.sleep(0.01)

        done_event.wait(timeout=10.0)

        with lock:
            assert len(received_ids) == 5, f"Expected 5 deliveries, got {len(received_ids)}"
            assert len(set(received_ids)) == 5, "Each message ID should appear exactly once"

        backend.unsubscribe(topic, client_id="eo_client")

    def test_backlog_replay(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, namespace: str
    ):
        """
        Store 3 messages BEFORE subscribing, then subscribe and verify all 3 are delivered.
        """
        msgs = [_make_message(topic, generator, {"n": i}) for i in range(3)]
        for msg in msgs:
            backend.store_message(namespace, topic, msg)
            time.sleep(0.01)

        received_ids = []
        lock = threading.Lock()
        done_event = threading.Event()

        def handler(msg: Message):
            with lock:
                received_ids.append(msg.id)
                if len(received_ids) >= 3:
                    done_event.set()

        backend.subscribe(topic, handler, client_id="backlog_client")

        done_event.wait(timeout=10.0)

        with lock:
            assert len(received_ids) == 3, f"Expected 3 backlog messages, got {len(received_ids)}"
            expected_ids = sorted([m.id for m in msgs])
            assert sorted(received_ids) == expected_ids

        backend.unsubscribe(topic, client_id="backlog_client")

    def test_crash_recovery(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, namespace: str
    ):
        """
        Subscribe, process 3 messages, unsubscribe (simulate crash), store 2 more,
        re-subscribe with SAME client_id, verify exactly 2 new messages delivered.
        """
        # Phase 1: subscribe and process 3 messages
        phase1_received = []
        phase1_event = threading.Event()
        phase1_lock = threading.Lock()

        def phase1_handler(msg: Message):
            with phase1_lock:
                phase1_received.append(msg.id)
                if len(phase1_received) >= 3:
                    phase1_event.set()

        backend.subscribe(topic, phase1_handler, client_id="crash_client")

        msgs_phase1 = [_make_message(topic, generator, {"phase": 1, "n": i}) for i in range(3)]
        for msg in msgs_phase1:
            backend.store_message(namespace, topic, msg)
            time.sleep(0.01)

        phase1_event.wait(timeout=10.0)
        assert len(phase1_received) == 3

        # Simulate crash/disconnect
        backend.unsubscribe(topic, client_id="crash_client")
        time.sleep(0.1)

        # Phase 2: store 2 more messages while disconnected
        msgs_phase2 = [_make_message(topic, generator, {"phase": 2, "n": i}) for i in range(2)]
        for msg in msgs_phase2:
            backend.store_message(namespace, topic, msg)
            time.sleep(0.01)

        # Phase 3: re-subscribe with same client_id - should get only the 2 new messages
        phase3_received = []
        phase3_event = threading.Event()
        phase3_lock = threading.Lock()

        def phase3_handler(msg: Message):
            with phase3_lock:
                phase3_received.append(msg.id)
                if len(phase3_received) >= 2:
                    phase3_event.set()

        backend.subscribe(topic, phase3_handler, client_id="crash_client")

        phase3_event.wait(timeout=10.0)

        with phase3_lock:
            assert len(phase3_received) == 2, f"Expected 2 new messages after reconnect, got {len(phase3_received)}"
            expected_phase2_ids = sorted([m.id for m in msgs_phase2])
            assert sorted(phase3_received) == expected_phase2_ids, "Should only receive the 2 new messages"
            # Must NOT have replayed the 3 previously-processed messages
            for prev_id in phase1_received:
                assert prev_id not in phase3_received, "Previously processed messages must not be replayed"

        backend.unsubscribe(topic, client_id="crash_client")

    def test_handler_failure_no_position_advance(
        self, backend: MessagingBackend, generator: GemstoneGenerator, topic: str, namespace: str
    ):
        """
        When a handler raises on a message, the position is NOT advanced.
        On re-subscribe with the same client_id, the failed message is replayed.
        """
        call_counts: dict[int, int] = {}
        lock = threading.Lock()
        received: list[Message] = []
        done_event = threading.Event()

        def failing_handler(msg: Message):
            with lock:
                n = call_counts.get(msg.id, 0) + 1
                call_counts[msg.id] = n
            if len(received) == 0 and n == 1:
                # Fail on first ever call for the first message
                raise RuntimeError("Simulated handler failure")
            with lock:
                received.append(msg.id)
                if len(received) >= 3:
                    done_event.set()

        backend.subscribe(topic, failing_handler, client_id="failure_client")

        msgs = [_make_message(topic, generator, {"n": i}) for i in range(3)]
        for msg in msgs:
            backend.store_message(namespace, topic, msg)
            time.sleep(0.01)

        done_event.wait(timeout=30.0)  # longer timeout for redelivery after ack_wait

        with lock:
            assert len(received) >= 3, f"Expected at least 3 successful deliveries, got {len(received)}"
            # The first message should have been retried (called more than once)
            first_msg_id = msgs[0].id
            assert call_counts.get(first_msg_id, 0) >= 2, "First message should have been retried after failure"

        backend.unsubscribe(topic, client_id="failure_client")
