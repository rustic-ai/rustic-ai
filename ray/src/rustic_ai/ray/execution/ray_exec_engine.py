from typing import Any, Dict, List, Type, Union

import ray
import ray.util.state
from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

from .ray_agent_wrapper import RayAgentWrapper


class RayExecutionEngine(ExecutionEngine):
    def __init__(self, guild_id: str) -> None:
        super().__init__(guild_id=guild_id)
        # Initialize Ray if not already done
        if not ray.is_initialized():
            raise Exception("Ray must be initialized before using RayExecutionEngine.")  # pragma: no cover
        self.agent_wrappers: Dict[str, Dict[str, RayAgentWrapper]] = {}
        self.agent_actors: Dict[str, Dict[str, ray.actor.ActorHandle]] = {}

    def run_agent(
        self,
        guild_spec: GuildSpec,
        agent_spec: Union[AgentSpec, Agent],
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
        default_topic: str = "default_topic",
    ) -> None:
        """
        Wraps the agent in a RayAgentWrapper and runs it asynchronously using Ray.
        """
        # Instantiate the RayAgentWrapper with provided parameters. Note the use of Ray's remote function.
        guild_id = guild_spec.id
        agent_wrapper = RayAgentWrapper.options(name=agent_spec.id, namespace=guild_id, lifetime="detached").remote(  # type: ignore
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        # Execute the agent asynchronously
        actor = ray.get(agent_wrapper.run.remote())  # type: ignore

        if guild_id not in self.agent_wrappers:
            self.agent_wrappers[guild_id] = {}

        if guild_id not in self.agent_actors:
            self.agent_actors[guild_id] = {}

        self.agent_wrappers[guild_id][agent_spec.id] = agent_wrapper
        self.agent_actors[guild_id][agent_spec.id] = actor

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        actor_refs = ray.util.list_named_actors(all_namespaces=True)
        agent_specs = {}
        for actor_ref in actor_refs:
            if actor_ref["namespace"] == guild_id:
                actor = ray.get_actor(name=actor_ref["name"], namespace=guild_id)  # type: ignore
                if self._is_rustic_agent(actor):
                    agent_spec: AgentSpec = ray.get(actor.get_agent_spec.remote())  # type: ignore
                    agent_specs[agent_spec.id] = agent_spec
        return agent_specs

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        try:
            actor = ray.get_actor(name=agent_id, namespace=guild_id)
            if actor is not None:
                if self._is_rustic_agent(actor):
                    return ray.get(actor.is_running.remote())
            return False
        except ValueError:
            return False
        except ray.exceptions.RayActorError:
            return False

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        agents = self.get_agents_in_guild(guild_id)
        return [agent_spec for agent_id, agent_spec in agents.items() if agent_spec.name == agent_name]

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops the agent with the given ID in the guild with the given ID.
        """
        agent_wrapper = ray.get_actor(name=agent_id, namespace=guild_id)  # type: ignore
        if agent_wrapper is not None:
            if self._is_rustic_agent(agent_wrapper):
                ray.get(agent_wrapper.shutdown.remote())
                ray.kill(agent_wrapper)

            del self.agent_wrappers[guild_id][agent_id]
            del self.agent_actors[guild_id][agent_id]

    def _is_rustic_agent(self, agent_wrapper) -> bool:
        if (
            agent_wrapper is not None
            and hasattr(agent_wrapper, "is_rustic_agent")
            and ray.get(agent_wrapper.is_rustic_agent.remote())
        ):
            return True
        else:
            return False

    def shutdown(self) -> None:
        """
        Shutdown the Ray execution engine.
        """
        actors = ray.util.list_named_actors()
        for actor_name in actors:
            self.stop_agent(guild_id=self.guild_id, agent_id=actor_name)
        ray.shutdown()
