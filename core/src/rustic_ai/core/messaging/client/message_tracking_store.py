from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import create_engine
from sqlmodel import Session

from rustic_ai.core.messaging.client.models import LastProcessedMsg


class MessageTrackingStore(ABC):
    @abstractmethod
    def update_last_processed(self, client_id: str, message_id: int):
        pass

    @abstractmethod
    def get_last_processed(self, client_id: str) -> Optional[int]:
        pass


class SqlMessageTrackingStore(MessageTrackingStore):
    def __init__(self, db: str):
        self.engine = create_engine(db)

    def update_last_processed(self, client_id: str, message_id: int):
        msg_id_str = str(message_id)
        with Session(self.engine) as session:
            existing_entry = session.get(LastProcessedMsg, client_id)
            if existing_entry:
                existing_entry.message_id = msg_id_str
                session.add(existing_entry)
            else:
                entry = LastProcessedMsg(client_id=client_id, message_id=msg_id_str)
                session.add(entry)
            session.commit()

    def get_last_processed(self, client_id: str) -> Optional[int]:
        with Session(self.engine) as session:
            entry = session.get(LastProcessedMsg, client_id)
            if entry:
                return int(entry.message_id)
            else:
                return None
