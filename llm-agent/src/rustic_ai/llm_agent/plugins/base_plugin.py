"""
Base plugin class with dependency injection support.

All LLM Agent plugins (RequestPreprocessor, LLMCallWrapper, ResponsePostprocessor)
inherit from this class to gain access to dependency resolution capabilities.
"""

from abc import ABC
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from rustic_ai.core.guild.agent import Agent


class BasePlugin(BaseModel, ABC):
    """
    Base class for all LLM Agent plugins.

    Provides dependency injection support through the `get_dep()` method.
    Plugins can declare their dependencies via the `depends_on` field and
    then retrieve them using `self.get_dep(agent, "dependency_name")`.

    Example:
        class MyPlugin(LLMCallWrapper):
            depends_on: List[str] = ["logger", "config"]

            def preprocess(self, agent, ctx, request, llm):
                logger = self.get_dep(agent, "logger")
                config = self.get_dep(agent, "config")
                logger.log(f"Processing with config: {config.name}")
                return request
    """

    kind: Optional[str] = Field(default=None, frozen=True, description="FQCN of the plugin class")

    depends_on: List[str] = Field(
        default_factory=list,
        description="List of dependency keys this plugin requires. "
        "These must be defined in the guild/agent dependency_map and listed "
        "in the agent's additional_dependencies.",
    )

    @model_validator(mode="after")
    def _enforce_kind_matches_class(self):
        fqcn = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if self.kind and self.kind != fqcn:
            raise ValueError(f"`kind` must be {fqcn!r}, got {self.kind!r}")

        if not self.kind:
            object.__setattr__(self, "kind", fqcn)

        return self

    def get_dep(self, agent: Agent, name: str) -> Any:
        """
        Get a resolved dependency by name.

        Args:
            agent: The agent instance to use for dependency resolution.
            name: The dependency key to resolve. Must be declared in `depends_on`
                  and configured in the agent's dependency map.

        Returns:
            The resolved dependency instance.

        Raises:
            ValueError: If the dependency is not found in the agent's resolvers.

        Example:
            def preprocess(self, agent, ctx, request, llm):
                logger = self.get_dep(agent, "logger")
                logger.info("Processing request")
                return request
        """
        if name not in agent._dependency_resolvers:
            raise ValueError(
                f"Dependency '{name}' not found in agent's dependency resolvers. "
                f"Make sure it's defined in guild/agent dependency_map and listed "
                f"in agent's additional_dependencies."
            )
        resolver = agent._dependency_resolvers[name]
        return resolver.get_or_resolve(
            org_id=agent.get_organization(),
            guild_id=agent.guild_id,
            agent_id=agent.id,
        )
