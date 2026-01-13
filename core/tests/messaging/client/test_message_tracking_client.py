import time
from typing import List, Tuple

import pytest

from rustic_ai.core.messaging import (
    Client,
    Message,
    MessageTrackingClient,
    MessagingConfig,
    MessagingInterface,
    SimpleClient,
)
from rustic_ai.core.messaging.core.message import AgentTag, MessageConstants
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class TestMessageTrackingClient:

    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.fixture
    def namespace(self) -> str:
        return "test_namespace"

    @pytest.fixture
    def messaging(self, namespace) -> MessagingInterface:
        """
        Fixture that returns an instance of the Messaging Interface initialized with the given storage.
        """
        messaging_config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )
        return MessagingInterface(namespace, messaging_config)

    @pytest.fixture
    def message_tracking_client(self, messaging) -> Tuple[MessageTrackingClient, List[Message], List[Message]]:
        messages_received: List[Message] = []

        notifications_received: List[Message] = []

        class TestClient(MessageTrackingClient):
            def __init__(self, client_id: str, name: str):
                super().__init__(client_id, name, self.process_message)

            def notify_new_message(self, message: Message) -> None:
                notifications_received.append(message)
                return super().notify_new_message(message)

            def process_message(self, message: Message):
                messages_received.append(message)

        client = TestClient("client1", "Message Tracking Client")
        return client, messages_received, notifications_received

    @pytest.fixture
    def message_publisher(self) -> Client:
        class TestClient(SimpleClient):
            def __init__(self, client_id: str, name: str):
                super().__init__(client_id, name, self._handle_message)

            def _handle_message(self, message: Message):
                pass

            def send_message(self, topic: str, format: str, payload: dict, message_id):
                message = Message(
                    topics=topic,
                    sender=AgentTag(id=self.id, name=self.name),
                    format=format,
                    payload=payload,
                    id_obj=message_id,
                )
                self.publish(message)
                return message

        return TestClient("sender1", "Simple Publishing Client")

    def test_client_registration(self, messaging, message_tracking_client):
        client, _, _ = message_tracking_client
        messaging.register_client(client)
        assert client.id in messaging.clients

    def test_message_publishing_and_notification(
        self, message_publisher, messaging, message_tracking_client, generator
    ):
        client, _, notifications = message_tracking_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "test"},
            generator.get_id(Priority.NORMAL),
        )

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        # Check if the new_message_event is set
        assert len(notifications) == 1

    def test_message_handling(
        self,
        messaging: MessagingInterface,
        message_tracking_client,
        generator,
        message_publisher,
    ):
        client, handled, notifications = message_tracking_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_id = generator.get_id(Priority.NORMAL)

        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "test"}, message_id)

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        assert len(notifications) == 1
        assert len(handled) == 1
        assert notifications[0].id == message_id.to_int()
        assert notifications[0].payload == {"data": "test"}
        assert handled[0].id == message_id.to_int()
        assert handled[0].payload == {"data": "test"}

    def test_message_tracking(self, messaging, message_tracking_client, generator, message_publisher):
        client, _, _ = message_tracking_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        message_id2 = generator.get_id(Priority.NORMAL)

        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "test1"}, message_id1)
        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "test2"}, message_id2)

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        # Check if the last_processed_message_id is updated to the ID of the last message
        assert client.last_processed_message_id == message_id2.to_int()

    def test_handle_multiple_messages(self, messaging, message_tracking_client, generator, message_publisher):
        client, messages_received, _ = message_tracking_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_id1 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        message_id2 = generator.get_id(Priority.NORMAL)
        time.sleep(0.001)
        message_id3 = generator.get_id(Priority.NORMAL)

        # Send three messages
        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value1"}, message_id1)
        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value2"}, message_id2)
        message_publisher.send_message("topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "value3"}, message_id3)

        # Allow time for asynchronous message delivery
        time.sleep(1.0)  # Wait for message delivery

        # Check if all messages were processed
        assert len(messages_received) == 3
        assert messages_received[0].payload == {"data": "value1"}
        assert messages_received[1].payload == {"data": "value2"}
        assert messages_received[2].payload == {"data": "value3"}

    def test_handle_message_while_processing(self, message_tracking_client, messaging, generator, message_publisher):
        client, messages_received, _ = message_tracking_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        # Send a message
        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "value1"},
            generator.get_id(Priority.NORMAL),
        )
        time.sleep(0.001)

        # While processing, send another message
        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "value2"},
            generator.get_id(Priority.NORMAL),
        )

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        # Check if both messages were processed
        assert len(messages_received) == 2
        assert messages_received[0].payload == {"data": "value1"}
        assert messages_received[1].payload == {"data": "value2"}
