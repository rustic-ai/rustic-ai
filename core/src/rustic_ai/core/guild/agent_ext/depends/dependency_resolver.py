from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, Field

from rustic_ai.core.messaging.core.message import JsonDict
from rustic_ai.core.utils.basic_class_utils import get_class_from_name

DT = TypeVar("DT")
D = TypeVar("D")

GUILD_GLOBAL = "GUILD_GLOBAL"


class DependencySpec(BaseModel):
    class_name: str = Field(min_length=1, max_length=512)
    properties: JsonDict = {}

    def to_resolver(self) -> DependencyResolver:
        resolver_class = get_class_from_name(self.class_name)
        if issubclass(resolver_class, DependencyResolver):
            return resolver_class(**self.properties)
        else:  # pragma: no cover
            raise ValueError(f"The class {self.class_name} is not a valid DependencyResolver.")


class DependencyResolver(ABC, Generic[DT]):

    memoize_resolution: bool = True

    def __init__(self):
        self.cache: Dict[str, Dict[str, DT]] = {}
        self._dependency_specs: Dict[str, DependencySpec] = {}
        self._injectors: Dict[str, DependencyResolver] = {}

    @abstractmethod
    def resolve(self, guild_id: str, agent_id: str) -> DT:
        """
        Resolve a dependency.

        Args:
            guild_id: The ID of the guild.
            agent_id: The ID of the agent. If this is None, resolve the dependency is guild-scoped.

        Returns:
            The resolved dependency.
        """
        pass  # pragma: no cover

    def get_or_resolve(self, guild_id: str, agent_id: Optional[str] = None) -> DT:
        """
        Get or resolve a dependency.

        Args:
            guild_id: The ID of the guild.
            agent_id: The ID of the agent. If this is None, resolve the dependency is guild-scoped.

        Returns:
            The resolved dependency.
        """
        agent_id = agent_id or GUILD_GLOBAL
        if self.memoize_resolution:
            if guild_id not in self.cache:
                self.cache[guild_id] = {}

            if agent_id not in self.cache[guild_id]:
                self.cache[guild_id][agent_id] = self.resolve(guild_id, agent_id)
            return self.cache[guild_id][agent_id]
        else:
            return self.resolve(guild_id, agent_id)

    @classmethod
    def get_qualified_class_name(cls) -> str:
        """
        Get the qualified class name of the dependency resolver.

        Returns:
            The qualified class name of the dependency resolver.
        """
        return f"{cls.__module__}.{cls.__name__}"

    def set_dependency_specs(self, specs: Dict[str, DependencySpec]) -> None:
        """
        Set the dependency specs for the resolver.

        Args:
            specs: The dependency specs to set.
        """
        self._dependency_specs = specs

    def inject(self, cls: Type[D], name: str, guild_id: str, agent_id: Optional[str] = None) -> D:
        """
        Inject a dependency into the resolver resolving it from the dependency specs.

        Args:
            cls: The class of the dependency.
            name: The name of the dependency.
            guild_id: The ID of the guild.
            agent_id: The ID of the agent. If this is None, resolve the dependency is guild-scoped.

        Returns:
            The resolved dependency.

        Raises:
            ValueError: If the dependency is not registered in the resolver or
                if the dependency is not an instance of the given class.
        """
        if name not in self._dependency_specs:
            raise ValueError(f"Dependency {name} is not registered in the resolver.")

        if name not in self._injectors:
            injector = self._dependency_specs[name].to_resolver()
            injector.set_dependency_specs(self._dependency_specs)
            self._injectors[name] = injector

        dep = self._injectors[name].get_or_resolve(guild_id, agent_id)

        if not issubclass(type(dep), cls):
            raise ValueError(f"Dependency {name} is not an instance of {cls}.")

        return dep
