import random
from typing import Optional

from sqlalchemy import Engine

from rustic_ai.core.agents.system.models import GuildReadyMessage
from rustic_ai.core.guild import GuildSpec
from rustic_ai.core.guild.builders import GuildBuilder, GuildHelper
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.guild.metastore import GuildStore
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.messaging.core.messaging_interface import MessagingInterface
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority


class GuildService:

    def create_guild(self, metastore_url: str, guild_spec: GuildSpec) -> str:
        """
        Creates a new guild and adds it to the database.
        """
        if guild_spec.get_messaging() is None:
            default_messaging = GuildHelper.get_default_messaging_config()
            guild_spec.set_messaging(**default_messaging)

        if guild_spec.get_execution_engine() is None:
            guild_spec.set_execution_engine(GuildHelper.get_default_execution_engine())

        guild_spec.dependency_map = GuildHelper.get_guild_dependency_map(guild_spec)

        guild = GuildBuilder.from_spec(guild_spec).bootstrap(metastore_url)

        messaging_config = GuildHelper.get_messaging_config(guild_spec)
        messaging = MessagingInterface(guild.id, messaging_config)
        msg_id = GemstoneGenerator(random.randint(10, 100)).get_id(priority=Priority.HIGH)
        system_agent = AgentTag(id="api_server", name="API Server")

        message = Message(
            id_obj=msg_id,
            topics=[GuildTopics.SYSTEM_TOPIC],
            sender=system_agent,
            format=get_qualified_class_name(GuildReadyMessage),
            payload={"guild_id": guild.id, "guild_name": guild_spec.name},
        )

        messaging.publish(sender=system_agent, message=message)

        return guild.id

    def get_guild(self, engine: Engine, guild_id: str) -> Optional[GuildSpec]:
        """
        Retrieves a guild and its agents from the database.
        """

        guild_store = GuildStore(engine)
        guild_model = guild_store.get_guild(guild_id)

        guild_spec = guild_model.to_guild_spec() if guild_model else None

        return guild_spec
