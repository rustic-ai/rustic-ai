from typing import Type, TypeVar

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.core.utils.basic_class_utils import get_class_from_name


def get_agent_class(full_class_name: str) -> Type[Agent]:
    agent_class = get_class_from_name(full_class_name)
    if not issubclass(agent_class, Agent):
        raise TypeError(f"Class {full_class_name} is not a subclass of Agent")
    return agent_class


def create_agent_from_spec(agent_spec: AgentSpec) -> Agent:
    agent_class = get_agent_class(agent_spec.class_name)
    return agent_class(agent_spec)  # type: ignore


T = TypeVar("T", bound=Agent, covariant=True)


def get_agent_from_spec_with_type(agent_spec: AgentSpec, agent_type: Type[T]) -> T:
    agent_class = get_agent_class(agent_spec.class_name)
    return agent_class(agent_spec)  # type: ignore


def get_execution_class(full_class_name: str) -> Type[ExecutionEngine]:
    execution_class = get_class_from_name(full_class_name)
    if not issubclass(execution_class, ExecutionEngine):
        raise TypeError(f"Class {full_class_name} is not a subclass of ExecutionEngine")
    return execution_class


def create_execution_engine(full_class_name: str, guild_id: str) -> ExecutionEngine:
    execution_class = get_execution_class(full_class_name)
    return execution_class(guild_id=guild_id)


def get_client_class(full_class_name: str) -> Type[Client]:
    client_class = get_class_from_name(full_class_name)
    if not issubclass(client_class, Client):
        raise TypeError(f"Class {full_class_name} is not a subclass of Client")
    return client_class


def get_state_manager_class(full_class_name: str) -> Type[StateManager]:
    state_manager_class = get_class_from_name(full_class_name)
    if not issubclass(state_manager_class, StateManager):
        raise TypeError(f"Class {full_class_name} is not a subclass of StateManager")
    return state_manager_class


def get_state_manager(full_class_name: str) -> StateManager:
    state_manager_class = get_state_manager_class(full_class_name)
    if not issubclass(state_manager_class, StateManager):
        raise TypeError(f"Class {full_class_name} is not a subclass of StateManager")

    return state_manager_class()
