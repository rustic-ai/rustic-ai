import heapq
from typing import Callable, List, Optional, Tuple

from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message


class SimpleClient(Client):
    """
    A simple implementation of the Client abstract base class.

    This client can receive a message handler function during initialization, which will be called
    whenever a new message is received.
    """

    def __init__(self, client_id: str, name: str, message_handler: Callable[[Message], None]):
        """
        Initializes the SimpleClient with a given client ID, name, and message handler.

        Args:
            client_id (str): The unique ID for this client.
            name (str): The name of the client.
            message_handler (Callable[[Message], None]): A function that will be called with a message as its argument
                                                        whenever a new message is received.
        """
        super().__init__(client_id, name, message_handler)
        self._message_queue: List[Tuple[int, Message]] = []
        self._last_message: Optional[Message] = None

    def notify_new_message(self, message: Message) -> None:
        """
        Notify the client of a new message by adding it to the priority queue and calling the message handler.

        Args:
            message (Message): The new message.
        """
        heapq.heappush(self._message_queue, (message.id, message))
        self.handle_message()

    def handle_message(self) -> None:
        """
        Handle a new message by calling the provided message handler with the highest priority message.
        """
        if self._last_message:
            self._message_handler(self._last_message)  # pragma: no cover
            self._last_message = None  # pragma: no cover
        elif self._message_queue:  # Check if there are messages in the queue
            _, message = heapq.heappop(self._message_queue)
            self._last_message = message
            self._message_handler(message)
            self._last_message = None
