from typing import Any, Dict, Type

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.dsl import AgentSpec, GuildSpec
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.messaging_interface import MessagingInterface
from rustic_ai.core.utils.class_utils import get_agent_class
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


def build_agent_from_spec(
    agent_spec: AgentSpec,
    guild_spec: GuildSpec,
    dependencies: Dict[str, DependencySpec],
    client_class: Type[Client],
    client_props: Dict[str, Any],
    machine_id: int,
) -> Agent:

    agent_class = get_agent_class(agent_spec.class_name)

    # Initialize the agent's dependencies
    agent_deps = agent_class.list_all_dependencies()

    dependency_resolvers = {
        dep.dependency_key: load_dependency_resolver(dependencies, dep.dependency_key) for dep in agent_deps
    }

    # Create the agent instance
    new_agent = agent_class.__new__(agent_class)
    Agent.__init__(
        self=new_agent,
        agent_spec=agent_spec,
        guild_spec=guild_spec,
        dependency_resolvers=dependency_resolvers,
        client_class=client_class,
        client_props=client_props.copy(),
        id_generator=GemstoneGenerator(machine_id),
    )

    if "__init__" in agent_class.__dict__:  # Only call custom __init__ if defined in this class
        agent_class.__init__(self=new_agent)

    return new_agent


def load_dependency_resolver(dependencies: Dict[str, DependencySpec], name: str) -> DependencyResolver:
    """
    Loads the dependency resolver for the given name.

    Args:
        dependencies (Dict[str, DependencySpec]): The agent's dependencies.
        name (str): The name of the dependency resolver.

    Returns:
        DependencyResolver: The dependency resolver for the agent.
    """
    if name in dependencies:
        resolver = dependencies[name].to_resolver()
        resolver.set_dependency_specs(dependencies)
        return resolver
    else:  # pragma: no cover
        raise ValueError(f"Dependency {name} not found in agent dependencies.")


def subscribe_agent_with_messaging(
    agent: Agent,
    messaging: MessagingInterface,
) -> None:
    """
    Subscribes the agent's client to the messaging system and registers it.

    Args:
        agent (Agent): The agent whose client is being subscribed.
        messaging (MessagingInterface): The messaging interface to use.
    """
    client = agent._client
    messaging.register_client(client)
    for topic in agent.subscribed_topics:
        messaging.subscribe(topic, client)
        agent.logger.debug(f"Client [{agent.name}:{agent.id}] registered and subscribed to topic: {topic}")
