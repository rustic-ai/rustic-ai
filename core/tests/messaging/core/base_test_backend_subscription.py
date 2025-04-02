import pytest

from rustic_ai.core.messaging.core.message import AgentTag, Message, MessageConstants
from rustic_ai.core.messaging.core.messaging_backend import MessagingBackend
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority

from .base_test_backend import BaseTestBackendABC


class BaseTestStorageWithSubscription(BaseTestBackendABC):
    @pytest.fixture
    def storage2(self) -> MessagingBackend:
        """
        Fixture that returns an instance of the storage implementation being tested.
        This should be overridden in subclasses that test specific storage implementations.
        """
        raise NotImplementedError("This fixture should be overridden in subclasses.")

    # Test subscribe and unsubscribe methods by creating 2 instances of the storage and subscribing to a topic
    def test_subscribe_and_unsubscribe(
        self,
        storage: MessagingBackend,
        storage2: MessagingBackend,
        generator: GemstoneGenerator,
    ):
        """
        Test subscribing and unsubscribing from a topic.
        """
        messages = []

        def handler(message: Message) -> None:
            messages.append(message)

        # Subscribe to a topic
        storage2.subscribe("topic", handler)

        # Unsubscribe from the topic
        m1 = Message(
            topics="topic",
            sender=AgentTag(id="userId", name="user"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "m1"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        storage.store_message("topic", m1)
