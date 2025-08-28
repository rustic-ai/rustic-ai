from sqlmodel import Field, SQLModel


class LastProcessedMsg(SQLModel, table=True):
    __tablename__ = "last_processed_msg"
    client_id: str = Field(primary_key=True)
    message_id: str
