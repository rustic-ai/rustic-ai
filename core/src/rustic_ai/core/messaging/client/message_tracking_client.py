import heapq
import logging
import threading
from typing import Callable, List, Tuple

from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message


class MessageTrackingClient(Client):
    """
    A client that tracks messages received from a message bus.

    Attributes:
        client_id (str): The unique ID of the client.
        name (str): The name of the client.
        last_processed_message_id (str): The ID of the last processed message.
        new_message_event (threading.Event): An event that is set when a new message is received.
        is_processing (bool): A flag indicating whether the client is currently processing a message.
        message_heap (List[Tuple[int, Message]]): A heap (priority queue) of messages, ordered by message ID.
    """

    def __init__(self, id: str, name: str, message_handler: Callable[[Message], None]):
        super().__init__(id, name, message_handler)
        self.last_processed_message_id: int = 0
        self.new_message_event = threading.Event()
        self.is_processing = False
        self.message_heap: List[Tuple[int, Message]] = []  # Priority queue (heap) for messages
        logging.basicConfig(level=logging.INFO)

    def notify_new_message(self, message: Message) -> None:
        """
        Notifies the client of a new message by adding it to the priority queue and setting the new message event.

        Args:
            message (Message): The new message.
        """
        # Add the message to the heap (priority queue)
        # logging.debug(f"{self.id} :: Received new message: {message}. is processing: {self.is_processing}")
        heapq.heappush(self.message_heap, (message.id, message))
        self.new_message_event.set()
        if not self.is_processing:
            logging.debug("{self.id} :: Starting message processing thread")
            self.handle_message()

    def handle_message(self) -> None:
        """
        Handles new messages by processing them and updating the last processed message ID.
        """
        self.is_processing = True
        while self.new_message_event.is_set():
            if self.message_heap:
                try:
                    # Get the message with the smallest ID from the heap
                    _, next_message = heapq.heappop(self.message_heap)
                    # Process the next message
                    # logging.debug(f"{self.id} :: Processing message: {next_message}")
                    self._message_handler(next_message)
                    # Update the last processed message ID
                    self.last_processed_message_id = next_message.id
                except Exception as e:  # noqa
                    logging.exception(f"{self.id} :: Error processing message:")

                    continue
            else:
                # If no more messages, clear the event
                self.new_message_event.clear()
        self.is_processing = False

        logging.debug(
            f"{self.id} :: Finished processing messages. Event set: {self.new_message_event.is_set()} | is processing: {self.is_processing}"
        )
