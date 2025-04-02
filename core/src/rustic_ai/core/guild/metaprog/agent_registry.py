from typing import Dict, List, Optional, Type

from pydantic import BaseModel, Field, JsonValue, computed_field

from rustic_ai.core.guild.dsl import BaseAgentProps


class SendMessageCall(BaseModel):
    calling_class: Optional[str] = Field(default=None, description="The class containing the calling function")
    calling_function: str
    call_type: str
    message_type: Optional[str] = Field(default=None, description="The type of the message being sent")


class HandlerEntry(BaseModel):
    handler_name: str = Field(..., description="The name of the handler.")
    message_format: str = Field(..., description="The format of the message.")
    message_format_schema: Dict[str, JsonValue] = Field(..., description="The schema for the message format.")
    handler_doc: Optional[str] = Field(default="", description="The documentation for the handler.")
    send_message_calls: List[SendMessageCall] = Field(..., description="The calls to send messages from this agent.")


class AgentDependency(BaseModel):
    """
    Represents a dependency for an agent.
    """

    dependency_key: str
    """
    The key for the dependency.
    """
    dependency_var: Optional[str] = None
    """
    The variable name to set the dependency on. If none, we assume that it is the same as the key.
    """
    guild_level: bool = False
    """
    Whether the dependency is at the guild level. This is shared across all agents in the guild.
    """

    @computed_field  # type: ignore[misc]
    @property
    def agent_level(self) -> bool:  # pragma: no cover
        """
        Whether the dependency is at the agent level.
        """
        return not self.guild_level

    @computed_field  # type: ignore[misc]
    @property
    def variable_name(self) -> str:
        return self.dependency_var or self.dependency_key

    @classmethod
    def from_string(cls, dep: str):
        deps = dep.split(":")
        if len(deps) == 1:
            return cls(dependency_key=deps[0])
        elif len(deps) == 2:
            return cls(dependency_key=deps[0], dependency_var=deps[1])
        elif len(deps) >= 3:
            return cls(
                dependency_key=deps[0],
                dependency_var=deps[1] or None,
                guild_level=bool(deps[2]),
            )


class AgentEntry(BaseModel):

    agent_name: str = Field(..., description="The name of the agent.")
    qualified_class_name: str = Field(..., description="The qualified class name of the agent.")
    agent_doc: Optional[str] = Field(default="", description="The documentation for the agent.")
    agent_props_schema: Dict[str, JsonValue] = Field(..., description="The type of the agent properties.")
    message_handlers: Dict[str, HandlerEntry] = Field(..., description="The handlers for the agent.")
    agent_dependencies: List[AgentDependency] = Field(..., description="The dependencies for the agent.")

    def __init__(
        self,
        agent_name: str,
        qualified_class_name: str,
        agent_doc: str,
        message_handlers: Dict[str, HandlerEntry],
        agent_props_type: type[BaseModel],
        agent_dependencies: List[AgentDependency],
    ):
        super().__init__(
            agent_name=agent_name,
            qualified_class_name=qualified_class_name,
            agent_doc=agent_doc,
            agent_props_schema=agent_props_type.model_json_schema(),
            message_handlers=message_handlers,
            agent_dependencies=agent_dependencies,
        )


class AgentRegistry:
    _agents: Dict[str, AgentEntry] = {}

    @classmethod
    def register(
        cls,
        agent_name: str,
        qualified_class_name: str,
        agent_doc: str,
        handlers: Dict[str, HandlerEntry],
        agent_props_type: Type[BaseAgentProps],
        agent_dependencies: List[AgentDependency],
    ):
        cls._agents[qualified_class_name] = AgentEntry(
            agent_name,
            qualified_class_name,
            agent_doc,
            handlers,
            agent_props_type,
            agent_dependencies,
        )

    @classmethod
    def list_agents(cls) -> Dict[str, AgentEntry]:
        return cls._agents

    @classmethod
    def get_agent(cls, qualified_class_name: str) -> Optional[AgentEntry]:
        return cls._agents.get(qualified_class_name)
