import time
from typing import List, Tuple

import pytest

from rustic_ai.core.messaging.client.retrying_client import (
    ExponentialBackoff,
    FixedBackoff,
    RandomizedExponentialBackoff,
    RetryingClient,
)
from rustic_ai.core.messaging.client.simple_client import SimpleClient
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import AgentTag, Message, MessageConstants
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class TestRetryingClient:
    @pytest.fixture
    def gemstone_generator(self):
        """Fixture that returns a GemstoneGenerator instance with a seed of 1."""
        return GemstoneGenerator(1)

    @pytest.fixture
    def simple_client_with_failing_handler(self) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        def message_handler(message: Message):
            messages_received.append(message)
            raise Exception("Test exception")

        client = SimpleClient("client1", "Simple Client", message_handler)
        return client, messages_received

    @pytest.fixture
    def retrying_client_with_fixed_backoff(self, simple_client_with_failing_handler):
        """Fixture that returns a RetryingClient wrapping around a SimpleClient with a FixedBackoff strategy."""
        simple_client, messages_received = simple_client_with_failing_handler
        return (
            RetryingClient(client=simple_client, max_retries=3, backoff_strategy=FixedBackoff(0.1)),
            messages_received,
        )

    @pytest.fixture
    def simple_client_with_eventual_success_handler(
        self,
    ) -> Tuple[Client, List[Message]]:
        messages_received: List[Message] = []

        def message_handler(message: Message):
            messages_received.append(message)
            if len(messages_received) < 2:
                raise Exception("Test exception")

        client = SimpleClient("client1", "Simple Client", message_handler)
        return client, messages_received

    @pytest.fixture
    def retrying_client_with_exponential_backoff(self, simple_client_with_failing_handler):
        """Fixture that returns a RetryingClient wrapping around a SimpleClient with an ExponentialBackoff strategy."""
        simple_client, messages_received = simple_client_with_failing_handler
        return (
            RetryingClient(
                client=simple_client,
                max_retries=3,
                backoff_strategy=ExponentialBackoff(0.1),
            ),
            messages_received,
        )

    def test_retries_with_fixed_backoff(self, retrying_client_with_fixed_backoff, gemstone_generator):
        """Test that the RetryingClient retries the expected number of times with a FixedBackoff strategy."""
        retrying_client, messages_received = retrying_client_with_fixed_backoff

        # Send a message to the RetryingClient
        test_message = Message(
            topics="test_topic",
            sender=AgentTag(id="testSenderId", name="test_sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"content": "Test content"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        retrying_client.notify_new_message(test_message)

        time.sleep(0.01)

        # Verify that the original handle_message was called max_retries times
        assert len(messages_received) == 3

    def test_retries_with_exponential_backoff(self, retrying_client_with_exponential_backoff, gemstone_generator):
        """Test that the RetryingClient retries the expected number of times with an ExponentialBackoff strategy."""
        # Mock the original handle_message to count the number of times it's called
        retrying_client, messages_received = retrying_client_with_exponential_backoff

        # Send a message to the RetryingClient
        test_message = Message(
            topics="test_topic",
            sender=AgentTag(id="testSenderId", name="test_sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"content": "Test content"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )
        retrying_client.notify_new_message(test_message)

        # Verify that the original handle_message was called max_retries times
        assert len(messages_received) == 3

    def test_retries_with_zero_max_retries(self, simple_client_with_failing_handler, gemstone_generator):
        """Test that the RetryingClient does not retry when max_retries is set to 0."""
        # Create a RetryingClient with a FixedBackoff strategy and max_retries set to 0
        simple_client, messages_received = simple_client_with_failing_handler

        with pytest.raises(Exception):
            RetryingClient(client=simple_client, max_retries=0, backoff_strategy=FixedBackoff(0.1))

    # Test that the RetryingClient eventually succeeds when the message handler succeeds
    def test_eventual_success_with_fixed_backoff(self, simple_client_with_eventual_success_handler, gemstone_generator):
        """Test that the RetryingClient eventually succeeds when the message handler succeeds with a FixedBackoff strategy."""
        # Create a RetryingClient with a FixedBackoff strategy and max_retries set to 0
        simple_client, messages_received = simple_client_with_eventual_success_handler

        # Send a message to the RetryingClient
        test_message = Message(
            topics="test_topic",
            sender=AgentTag(id="testSenderId", name="test_sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"content": "Test content"},
            id_obj=gemstone_generator.get_id(Priority.NORMAL),
        )

        client = RetryingClient(client=simple_client, max_retries=5, backoff_strategy=FixedBackoff(0.1))

        client.notify_new_message(test_message)

        # Verify that the original handle_message was called max_retries times
        assert len(messages_received) == 2

    # Test RandomizedExponentialBackoff strategy
    def test_randomized_exponential_backoff(self, gemstone_generator):
        """Test that the RandomizedExponentialBackoff strategy returns a random delay time between the delay and twice the delay."""
        backoff_strategy = RandomizedExponentialBackoff(0.1)
        delay = backoff_strategy.get_delay(1)
        assert delay >= 0.2
        assert delay <= 0.4
