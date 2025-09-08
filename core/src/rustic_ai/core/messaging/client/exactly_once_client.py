import logging
import threading
from typing import Callable

from rustic_ai.core.messaging.client.message_tracking_store import MessageTrackingStore
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils import JsonDict
from rustic_ai.core.utils.basic_class_utils import get_class_from_name


class ExactlyOnceClient(Client):

    def __init__(
        self,
        id: str,
        name: str,
        message_handler: Callable[[Message], None],
        tracking_store_class: str,
        tracking_store_props: JsonDict,
    ):
        super().__init__(id, name, message_handler)
        store_class = get_class_from_name(tracking_store_class)
        self.message_tracking_store: MessageTrackingStore = store_class(**tracking_store_props)
        self.new_message_event = threading.Event()
        self.is_processing = False

    def notify_new_message(self, message: Message) -> None:
        self.new_message_event.set()
        if not self.is_processing:
            logging.debug(f"{self.id} :: Starting message processing thread")
            self.handle_message()

    def handle_message(self) -> None:
        """
        Handles new messages by processing them and updating the last processed message ID.
        """
        self.is_processing = True
        while self.new_message_event.is_set():
            last_msg_id = self.message_tracking_store.get_last_processed(self.id) or 0
            next_message = self._messaging.get_next_message_for_client(self.id, last_msg_id)
            if next_message:
                try:
                    # Update the last processed message ID
                    self.message_tracking_store.update_last_processed(self.id, next_message.id)
                    # Process the next message
                    # logging.debug(f"{self.id} :: Processing message: {next_message}")
                    self._message_handler(next_message)
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
