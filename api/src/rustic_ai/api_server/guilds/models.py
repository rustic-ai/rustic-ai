from datetime import datetime, timezone

import shortuuid
from sqlmodel import Field, SQLModel


class GuildRelaunchModel(SQLModel, table=True):
    __tablename__ = "guilds_relaunch"

    id: str = Field(primary_key=True, index=True, default_factory=shortuuid.uuid)
    guild_id: str = Field(index=True, foreign_key="guilds.id")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
