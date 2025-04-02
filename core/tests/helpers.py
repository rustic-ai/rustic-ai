from typing import Dict, List, Tuple, TypeVar
from unittest.mock import MagicMock

from pydantic import BaseModel

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import Message, MessageConstants
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator, GemstoneID

T = TypeVar("T", bound=Agent)


def wrap_agent_for_testing(
    agent: T, generator: GemstoneGenerator, dependency_map: Dict[str, DependencySpec] = {}
) -> Tuple[T, List[Message]]:
    """
    Wrap agent for testing.
    """

    results: List[Message] = []

    class MockProcessContext(ProcessContext):

        def __init__(self, agent: T, message: Message, method_name: str, payload_type: type):
            super().__init__(agent, message, method_name, payload_type)

        def send(
            self: ProcessContext,
            data: BaseModel,
            new_thread: bool = False,
            forwarding: bool = False,
            error_message: bool = False,
        ) -> List[GemstoneID]:
            id_obj = self.agent._generate_id(self.message.priority)
            msg = Message(
                topics=self.message.topics,
                format=get_qualified_class_name(data.__class__),
                sender=self.agent.get_agent_tag(),
                payload=data.model_dump(),
                id_obj=id_obj,
                in_response_to=self.message.id,
                thread=self.message.thread,
                recipient_list=[],
            )

            results.append(msg)

            return [id_obj]

        def send_dict(
            self,
            data: JsonDict,
            format: str = MessageConstants.RAW_JSON_FORMAT,
            new_thread: bool = False,
            forwarding: bool = False,
            error_message: bool = False,
        ) -> List[GemstoneID]:
            id_obj = self.agent._generate_id(self.message.priority)
            msg = Message(
                topics=self.message.topics,
                format=format,
                sender=self.agent.get_agent_tag(),
                payload=data,
                id_obj=id_obj,
                in_response_to=self.message.id,
                thread=self.message.thread,
                recipient_list=[],
            )

            results.append(msg)

            return [id_obj]

    agent._make_process_context = MagicMock()  # type: ignore
    agent._make_process_context.side_effect = lambda message, mname, payload_type, sf, ef, omf: MockProcessContext(
        agent, message, mname, payload_type
    )

    agent._set_generator(generator)

    resolvers: Dict[str, DependencyResolver] = {}
    for dep_name, dep_spec in dependency_map.items():
        resolver = dep_spec.to_resolver()
        resolver.set_dependency_specs(dependency_map)
        resolvers[dep_name] = resolver

    agent._set_dependency_resolvers(resolvers)

    guild_spec = GuildBuilder(f"{agent.id}_test_guild", "Test Guild", "Test Guild").build_spec()
    agent._set_guild_spec(guild_spec)

    return agent, results
