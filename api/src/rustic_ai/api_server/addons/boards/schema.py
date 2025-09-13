from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CreateBoardRequest(BaseModel):
    guild_id: str
    name: str
    created_by: str
    is_default: Optional[bool] = False
    is_private: Optional[bool] = False


class BoardResponse(BaseModel):
    id: str
    name: str
    guild_id: str
    created_by: str
    created_at: datetime
    is_default: bool
    is_private: bool


class BoardsResponse(BaseModel):
    boards: List[BoardResponse]


class AddMessageToBoardRequest(BaseModel):
    message_id: str


class BoardMessagesResponse(BaseModel):
    ids: List[str]
