import logging
import time
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message

"""
This module provides a framework for a pipeable message bus system. It includes various clients and backoff strategies
to handle message processing, logging, filtering, transforming, throttling, and retrying.

Usage:
1. Define your clients by inheriting from the provided abstract base classes.
2. Connect clients using the '|' operator to form a pipeline.
3. Send messages through the pipeline.

Ensure to write unit tests for each client and strategy to guarantee system reliability.
"""


class Pipeable(ABC):
    """
    An abstract base class for creating pipeable message bus clients.

    Pipeable clients can be connected together to form a pipeline of message processing.
    Each client in the pipeline can process the message and pass it on to the next client in the pipeline.

    To create a pipeable client, inherit from this class and implement the `notify_new_message` method.

    Example usage:
    ```
    class MyPipeableClient(Pipeable):
        def notify_new_message(self, message):
            # process the message
            # ...
            # pass the message on to the next client in the pipeline
            self.notify_next_client(message)
    ```

    To connect two pipeable clients together, use the `|` operator:
    ```
    client1 = MyPipeableClient()
    client2 = MyPipeableClient()
    client1 | client2
    ```

    This will create a pipeline where messages are processed by `client1` first, then passed on to `client2`.
    """

    def __init__(self):
        self._next_client: Optional[Client] = None

    @classmethod
    def __init_subclass__(cls, **kwargs):  # type: ignore
        """
        Check that the subclass also inherits from `Client`.

        This is necessary to ensure that the pipeable client can be used in a message bus pipeline.
        """
        super().__init_subclass__(**kwargs)
        if not issubclass(cls, Client):
            raise TypeError(
                f"{cls.__name__} must also inherit from Client or its subclass when inheriting from Pipeable"
            )

    def notify_next_client(self, message: Message) -> None:
        """
        Notify the next client in the pipeline of a new message.

        Args:
            message: The new message.
        """
        if self._next_client:
            self._next_client.notify_new_message(message)

    def __or__(self, other: Client) -> Client:
        """
        Connect two pipeable clients together using the `|` operator.

        Args:
            other: The next client in the pipeline.

        Returns:
            The piped client.
        """
        return self.pipe(other)

    def pipe(self, other: Client) -> Client:
        """
        Connect two pipeable clients together.

        Args:
            other: The next client in the pipeline.

        Returns:
            The piped client in the pipeline.
        """
        if not isinstance(other, Client):
            raise TypeError("next_client must be a Client")
        self._next_client = other
        return PipelineClient(self, other)  # type: ignore

    @abstractmethod
    def notify_new_message(self, message: Message):
        """
        Process a new message.

        This method should be implemented by subclasses to process a new message.
        The message can be modified or passed on to the next client in the pipeline using `self.notify_next_client`.

        Args:
            message: The new message.
        """
        pass  # pragma: no cover


class LoggingClient(Pipeable, Client):
    """
    A pipeable client that logs incoming messages.

    This client logs incoming messages using the `logging` module and passes them on to the next client in the pipeline.

    Example usage:
    ```
    client = LoggingClient()
    ```
    """

    def __init__(self, log_level=logging.INFO):
        super().__init__()
        self.log_level = log_level

    def notify_new_message(self, message: Message):
        """
        Log the incoming message and pass it on to the next client in the pipeline.

        Args:
            message: The incoming message.
        """
        logging.log(self.log_level, message.to_json())
        self.notify_next_client(message)


class FilteringClient(Pipeable, Client):
    """
    A pipeable client that filters incoming messages.

    This client filters incoming messages using a user-defined filter function and passes on only the messages that pass the filter.

    Example usage:
    ```
    def my_filter(message):
        # return True if the message should be passed on, False otherwise
        # ...
    client = FilteringClient(my_filter)
    ```
    """

    def __init__(self, filter_func: Callable[[Message], bool]):
        """
        Initialize the FilteringClient with a filter function.

        Args:
            filter_func: A function that takes a message and returns True if the message should be passed on, False otherwise.
        """
        super().__init__()
        self.filter_func = filter_func

    def notify_new_message(self, message: Message):
        """
        Filter the incoming message and pass it on to the next client in the pipeline if it passes the filter.

        Args:
            message: The incoming message.
        """
        if self.filter_func(message):
            self.notify_next_client(message)


class TransformingClient(Pipeable, Client):
    """
    A pipeable client that transforms incoming messages.

    This client transforms incoming messages using a user-defined transform function and passes on the transformed messages.

    Example usage:
    ```
    def my_transform(message):
        # transform the message
        # ...
        return transformed_message
    client = TransformingClient(my_transform)
    ```
    """

    def __init__(self, transform_func: Callable[[Message], Message]):
        """
        Initialize the TransformingClient with a transform function.

        Args:
            transform_func: A function that takes a message and returns the transformed message.
        """
        super().__init__()
        self.transform_func = transform_func

    def notify_new_message(self, message: Message):
        """
        Transform the incoming message and pass on the transformed message to the next client in the pipeline.

        Args:
            message: The incoming message.
        """
        transformed_message = self.transform_func(message)
        self.notify_next_client(transformed_message)


class ThrottlingClient(Pipeable, Client):
    """
    A pipeable client that throttles incoming messages.

    This client adds a delay between incoming messages before passing them on to the next client in the pipeline.

    Example usage:
    ```
    client = ThrottlingClient(0.5)  # add a delay of 0.5 seconds between messages
    ```
    """

    def __init__(self, delay_seconds: float):
        """
        Initialize the ThrottlingClient with a delay time.

        Args:
            delay_seconds: The delay time (in seconds) to add between incoming messages.
        """
        super().__init__()
        self.delay_seconds = delay_seconds

    def notify_new_message(self, message: Message):
        """
        Add a delay between incoming messages and pass them on to the next client in the pipeline.

        Args:
            message: The incoming message.
        """
        time.sleep(self.delay_seconds)
        self.notify_next_client(message)


class PipelineClient(Pipeable, Client):
    """
    A client that acts as a pipeline between two other clients.

    This client receives messages and forwards them to the head client,
    which can then forward them to the next client in the pipeline.

    Attributes:
        _head (Client): The head client in the pipeline.
        _tail (Client): The tail client in the pipeline.
    """

    def __init__(self, head: Client, tail: Client, pipeline: List[Client] = []):
        """
        Initializes a new PipelineClient.

        Args:
            head (Client): The head client in the pipeline.
            tail (Client): The tail client in the pipeline.
        """
        if not isinstance(head, Pipeable) and not isinstance(tail, Pipeable):
            raise TypeError("head and tail must be Pipeable")  # pragma: no cover

        self._head: Client = head
        self._tail: Client = tail

        self._pipeline: List[Client] = pipeline

        if not self._pipeline:
            self._pipeline = [head]

        self._pipeline.append(tail)

    def notify_new_message(self, message: Message):
        """
        Notifies the head client of a new message.

        Args:
            message (Message): The new message to forward to the head client.
        """
        self._head.notify_new_message(message)

    def pipe(self, other: Client) -> Client:
        """
        Pipes this client to another client.

        This method pipes the tail client of this pipeline to the specified
        client, and returns a new PipelineClient that connects the head
        client of this pipeline to the specified client.

        Args:
            other (Client): The client to pipe to.

        Returns:
            PipelineClient: A new PipelineClient that connects the head client of this pipeline to the specified client.
        """
        self._tail.pipe(other)  # type: ignore

        if isinstance(other, Pipeable):
            return PipelineClient(self._head, other, self._pipeline)
        else:
            return PipelinePlugClient(self._head, other, self._pipeline)


class PipelinePlugClient(Client):
    """
    A client that acts as a plug in a pipeline of clients.

    This client receives messages from the previous client in the pipeline and forwards them to the next client.
    It can be used to create a chain of clients that process messages in a specific order.

    :param head: The first client in the pipeline.
    :type head: Client
    :param tail: The last client in the pipeline.
    :type tail: Client
    :param pipeline: A list of clients that make up the pipeline (excluding the head and tail clients).
    :type pipeline: List[Client]
    """

    def __init__(self, head: Client, tail: Client, pipeline: List[Client] = []):
        self._head: Client = head
        self._tail: Client = tail
        if pipeline:
            self._pipeline: List[Client] = [head]

        self._pipeline.append(tail)

    def notify_new_message(self, message: Message):
        """
        Notifies the head client of a new message.

        This method is called by the previous client in the pipeline to forward a new message to this client.

        :param message: The new message.
        :type message: Message
        """
        self._head.notify_new_message(message)
