from abc import ABC, abstractmethod
import os
import re
import time
from typing import List, Tuple

import pytest

from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging import (
    Client,
    Message,
    MessagingConfig,
    MessagingInterface,
    SimpleClient,
)
from rustic_ai.core.messaging.client.exactly_once_client import ExactlyOnceClient
from rustic_ai.core.messaging.core.message import AgentTag, MessageConstants
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class BaseTestExactlyOnceClient(ABC):
    @abstractmethod
    @pytest.fixture
    def tracking_store_class(self):
        pass

    @abstractmethod
    @pytest.fixture
    def tracking_store_props(self):
        pass

    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.fixture
    def namespace(self, request) -> str:
        return "test_exactly_once_client"

    @pytest.fixture
    def messaging(self, namespace):
        """
        Fixture that returns an instance of the Messaging Interface initialized with the given storage.
        """
        messaging_config = MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

        mbus = MessagingInterface(namespace, messaging_config)
        yield mbus
        mbus.shutdown()

    @pytest.fixture
    def exactly_once_client(
        self, request, messaging, tracking_store_class, tracking_store_props
    ) -> Tuple[ExactlyOnceClient, List[Message], List[Message]]:
        messages_received: List[Message] = []

        notifications_received: List[Message] = []

        class TestClient(ExactlyOnceClient):
            def __init__(self, client_id: str, name: str):
                super().__init__(client_id, name, self.process_message, tracking_store_class, tracking_store_props)

            def notify_new_message(self, message: Message) -> None:
                notifications_received.append(message)
                return super().notify_new_message(message)

            def process_message(self, message: Message):
                messages_received.append(message)

        test_name = request.node.name
        sanitized_test_name = re.sub(r"[^\w\-_.]", "_", test_name)

        client = TestClient(sanitized_test_name, "Exactly Once Client")
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

    def test_client_registration(self, messaging, exactly_once_client):
        client, _, _ = exactly_once_client
        messaging.register_client(client)
        assert client.id in messaging.clients

    def test_message_publishing_and_notification(self, message_publisher, messaging, exactly_once_client, generator):
        client, _, notifications = exactly_once_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "test_message_publishing_and_notification"},
            generator.get_id(Priority.NORMAL),
        )

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        # Check if the new_message_event is set
        assert len(notifications) == 1

    def test_message_handling(
        self,
        messaging: MessagingInterface,
        exactly_once_client,
        generator,
        message_publisher,
    ):
        client, handled, notifications = exactly_once_client
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        message_id = generator.get_id(Priority.NORMAL)

        message_publisher.send_message(
            "topic1", MessageConstants.RAW_JSON_FORMAT, {"data": "test_message_handling"}, message_id
        )

        # Allow time for asynchronous message delivery
        time.sleep(0.5)

        assert len(notifications) == 1
        assert len(handled) == 1
        assert notifications[0].id == message_id.to_int()
        assert notifications[0].payload == {"data": "test_message_handling"}
        assert handled[0].id == message_id.to_int()
        assert handled[0].payload == {"data": "test_message_handling"}

    def test_handle_multiple_messages(self, messaging, exactly_once_client, generator, message_publisher):
        client, messages_received, _ = exactly_once_client
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

    def test_handle_message_while_processing(self, exactly_once_client, messaging, generator, message_publisher):
        client, messages_received, _ = exactly_once_client
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

    def test_backlog_message_handling(
        self, messaging, generator, message_publisher, tracking_store_class, tracking_store_props
    ):
        messages_received: List[Message] = []
        notifications_received: List[Message] = []

        class TestClient(ExactlyOnceClient):
            def __init__(self, client_id: str, name: str):
                super().__init__(client_id, name, self.process_message, tracking_store_class, tracking_store_props)

            def notify_new_message(self, message: Message) -> None:
                notifications_received.append(message)
                return super().notify_new_message(message)

            def process_message(self, message: Message):
                messages_received.append(message)

        client = TestClient("client1", "Exactly Once Client")
        messaging.register_client(client)
        messaging.subscribe("topic1", client)

        messaging.register_client(message_publisher)

        # Send some messages
        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "val1"},
            generator.get_id(Priority.NORMAL),
        )

        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "val2"},
            generator.get_id(Priority.NORMAL),
        )

        # Allow time for asynchronous message delivery
        time.sleep(2)

        # Check if both messages were processed
        assert len(messages_received) == 2
        client.disconnect()

        messages_received = []
        notifications_received = []

        client2 = TestClient("client1", "Exactly Once Client")
        messaging.register_client(client2)
        messaging.subscribe("topic1", client2)

        # Send some messages
        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "backlog1"},
            generator.get_id(Priority.NORMAL),
        )

        message_publisher.send_message(
            "topic1",
            MessageConstants.RAW_JSON_FORMAT,
            {"data": "backlog2"},
            generator.get_id(Priority.NORMAL),
        )

        time.sleep(1)
        assert len(messages_received) == 2
        assert messages_received[0].payload == {"data": "backlog1"}
        assert messages_received[1].payload == {"data": "backlog2"}


class TestExactlyOnceClientSql(BaseTestExactlyOnceClient):
    db_filename = "test_exactly_once_client.db"
    db_url = f"sqlite:///{db_filename}"

    def setup_class(cls):
        # Setup once before all tests in this class
        try:
            os.remove(cls.db_filename)
        except FileNotFoundError:
            pass
        Metastore.initialize_engine(cls.db_url)

    def teardown_class(cls):
        # Cleanup once after all tests in this class
        Metastore.drop_db(unsafe=True)
        try:
            os.remove(cls.db_filename)
        except FileNotFoundError:
            pass

    @pytest.fixture
    def tracking_store_class(self):
        return "rustic_ai.core.messaging.client.message_tracking_store.SqlMessageTrackingStore"

    @pytest.fixture
    def tracking_store_props(self):
        return {"db": TestExactlyOnceClientSql.db_url}
