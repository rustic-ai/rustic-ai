from typing import Callable

from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message


class SimpleClient(Client):
    """
    A simple implementation of the Client abstract base class.

    This client directly invokes the message handler on each received message.
    Ordering, exactly-once, and sequential processing guarantees are provided
    by the backend (not the client).
    """

    def __init__(self, id: str, name: str, message_handler: Callable[[Message], None]):
        """
        Initializes the SimpleClient with a given client ID, name, and message handler.

        Args:
            id (str): The unique ID for this client.
            name (str): The name of the client.
            message_handler (Callable[[Message], None]): A function that will be called with a message as its argument
                                                        whenever a new message is received.
        """
        super().__init__(id, name, message_handler)

    def notify_new_message(self, message: Message) -> None:
        """
        Notify the client of a new message by directly invoking the message handler.

        Args:
            message (Message): The new message.
        """
        self._message_handler(message)
