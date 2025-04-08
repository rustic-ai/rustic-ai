from typing import Optional

from sqlalchemy import Engine

from rustic_ai.core.guild import GuildSpec
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.metastore import GuildStore


class GuildService:

    def create_guild(self, metastore_url: str, guild_spec: GuildSpec) -> str:
        """
        Creates a new guild and adds it to the database.
        """
        guild = GuildBuilder.from_spec(guild_spec).bootstrap(metastore_url)

        return guild.id

    def get_guild(self, engine: Engine, guild_id: str) -> Optional[GuildSpec]:
        """
        Retrieves a guild and its agents from the database.
        """

        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)

        guild_spec = guild_model.to_guild_spec() if guild_model else None

        return guild_spec
