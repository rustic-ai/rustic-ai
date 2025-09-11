from datetime import datetime, timezone

import shortuuid
from sqlmodel import Field, SQLModel


class Board(SQLModel, table=True):
    __tablename__ = "board"

    id: str = Field(primary_key=True, index=True, default_factory=shortuuid.uuid)
    name: str = Field(index=True)
    guild_id: str = Field(index=True, foreign_key="guilds.id")
    created_by: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_default: bool = Field(default=False)
    is_private: bool = Field(default=False)


class BoardMessage(SQLModel, table=True):
    __tablename__ = "board_message"

    board_id: str = Field(primary_key=True, foreign_key="board.id")
    message_id: str = Field(primary_key=True)
