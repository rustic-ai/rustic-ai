import logging
from typing import Optional

from sqlalchemy import Engine
from sqlmodel import Session

from rustic_ai.api_server.guilds.schema import GuildSpecResponse
from rustic_ai.core.guild import GuildSpec
from rustic_ai.core.guild.builders import GuildBuilder, GuildHelper
from rustic_ai.core.guild.metastore import GuildModel, GuildStore, Metastore
from rustic_ai.core.guild.metastore.models import AgentModel, GuildStatus


class GuildService:

    def create_guild(self, metastore_url: str, guild_spec: GuildSpec, organization_id: str) -> str:
        """
        Creates a new guild and adds it to the database.

        Args:
            metastore_url (str): The URL of the metastore database.
            guild_spec (GuildSpec): The specification of the guild to create.
            organization_id (str): The ID of the organization that owns this guild.

        Returns:
            str: The ID of the created guild.
        """
        if guild_spec.get_messaging() is None:
            default_messaging = GuildHelper.get_default_messaging_config()
            guild_spec.set_messaging(**default_messaging)

        if guild_spec.get_execution_engine() is None:
            guild_spec.set_execution_engine(GuildHelper.get_default_execution_engine())

        guild_spec.dependency_map = GuildHelper.get_guild_dependency_map(guild_spec)

        engine = Metastore.get_engine(metastore_url)
        with Session(engine) as session:
            logging.info(f"Creating new guild : [{guild_spec}]")
            guild_model = GuildModel.from_guild_spec(guild_spec, organization_id)
            guild_model.status = GuildStatus.REQUESTED
            session.add(guild_model)
            # Add the agents to the Metastore
            for guild_agent in guild_spec.agents:
                agent_model = AgentModel.from_agent_spec(guild_spec.id, guild_agent)
                session.add(agent_model)
            session.commit()

        guild = GuildBuilder.from_spec(guild_spec).bootstrap(metastore_url, organization_id)

        return guild.id

    def get_guild(self, engine: Engine, guild_id: str) -> Optional[GuildSpecResponse]:
        """
        Retrieves a guild and its agents from the database.

        Args:
            engine (Engine): The database engine.
            guild_id (str): The ID of the guild to retrieve.

        Returns:
            Optional[GuildSpec]: The guild specification if found, None otherwise.
        """
        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)

        guild_spec = guild_model.to_guild_spec() if guild_model else None

        if guild_spec is None:
            return None

        return GuildSpecResponse(
            **guild_spec.model_dump(), status=GuildStatus(guild_model.status) if guild_model else GuildStatus.UNKNOWN
        )
