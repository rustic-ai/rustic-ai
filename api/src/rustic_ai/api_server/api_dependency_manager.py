from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy import Engine

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.builders import GuildHelper
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.guild.metastore.guild_store import GuildStore
from rustic_ai.core.utils.basic_class_utils import get_class_from_name


class ApiDependencyManager:
    """Singleton class to access dependencies for a guild from the API server."""

    __instance: Optional["ApiDependencyManager"] = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super(ApiDependencyManager, cls).__new__(cls)
        return cls.__instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.dependency_map_cache: Dict[str, Dict[str, DependencySpec]] = {}
            self.dependency_resolver_cache: Dict[str, Dict[str, DependencyResolver]] = {}
            self.initialized = True

    def get_dependency(self, dependency_name: str, engine: Engine, guild_id: str, agent_id: Optional[str] = None):
        """
        Gets the dependency resolver for the given dependency name.

        Args:
            dependency_name (str): The name of the dependency.
            engine (Engine): The database engine.
            guild_id (str): The guild id.
            agent_id (str): The agent id.

        Returns:
            Any: The dependency.
        """

        if (
            guild_id not in self.dependency_resolver_cache
            or dependency_name not in self.dependency_resolver_cache[guild_id]
        ):
            if guild_id not in self.dependency_map_cache:

                guild_store = GuildStore(engine)
                guild_model = guild_store.get_guild(guild_id)

                if not guild_model:
                    raise HTTPException(status_code=404, detail="Guild not found")

                guild_spec = guild_model.to_guild_spec()

                self.dependency_map_cache[guild_id] = GuildHelper.get_guild_dependency_map(guild_spec)

            if dependency_name not in self.dependency_map_cache[guild_id]:  # pragma: no cover
                raise HTTPException(
                    status_code=404, detail=f"Dependency for {dependency_name} not configured for guild {guild_id}"
                )

            if guild_id not in self.dependency_resolver_cache:
                self.dependency_resolver_cache[guild_id] = {}

            self.dependency_resolver_cache[guild_id][dependency_name] = self._load_dependency_resolver(
                guild_id, dependency_name
            )

        resolver = self.dependency_resolver_cache[guild_id][dependency_name]
        dependency = resolver.get_or_resolve(guild_id, agent_id)

        return dependency

    def _load_dependency_resolver(self, guild_id: str, name: str) -> DependencyResolver:
        """
        Loads the dependency resolver for the given name.

        Args:
            guild_id (str): The guild id.
            name (str): The name of the dependency resolver.

        Returns:
            DependencyResolver: The dependency resolver for the agent.
        """
        dependencies = self.dependency_map_cache[guild_id]
        if name in dependencies:
            resolver_spec = dependencies[name]
            resolver_class = get_class_from_name(resolver_spec.class_name)
            if issubclass(resolver_class, DependencyResolver):
                return resolver_class(**resolver_spec.properties)
            else:  # pragma: no cover
                raise ValueError(f"Dependency resolver {resolver_spec} is not a valid dependency resolver.")
        else:  # pragma: no cover
            raise ValueError(f"Dependency {name} not found in agent dependencies.")

    @classmethod
    def get_instance(cls) -> "ApiDependencyManager":
        api_dependency_manager = ApiDependencyManager()
        return api_dependency_manager
