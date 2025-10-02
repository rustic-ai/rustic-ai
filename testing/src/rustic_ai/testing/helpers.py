from functools import partial
from typing import Dict, List, Optional, Tuple, TypeVar
from unittest.mock import MagicMock

from pydantic import BaseModel

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.execution.utils import build_agent_from_spec
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import (
    Message,
    MessageConstants,
    ProcessEntry,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneID

T = TypeVar("T", bound=Agent)


def wrap_agent_for_testing(
    agent_spec: AgentSpec, dependency_map: Dict[str, DependencySpec] = {}
) -> Tuple[Agent, List[Message]]:
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
            reason: Optional[str] = None,
        ) -> List[GemstoneID]:
            id_obj = self.agent._generate_id(self.message.priority)

            self.send_dict(
                data=data.model_dump(mode="json"),
                format=get_qualified_class_name(data.__class__),
                new_thread=new_thread,
                forwarding=forwarding,
                error_message=error_message,
            )

            return [id_obj]

        def send_dict(
            self,
            data: JsonDict,
            format: str = MessageConstants.RAW_JSON_FORMAT,
            new_thread: bool = False,
            forwarding: bool = False,
            error_message: bool = False,
            reason: Optional[str] = None,
        ) -> List[GemstoneID]:
            id_obj = self.agent._generate_id(self.message.priority)

            process_entry = ProcessEntry(
                agent=self.agent.get_agent_tag(),
                from_topic=self.message.topic_published_to,
                origin=self.message.id,
                result=id_obj.to_int(),
                processor=self.method_name,
                to_topics=self.message.topics if isinstance(self.message.topics, list) else [self.message.topics],
            )

            session_state = self.get_context()

            # Ensure nested payload is JSON-serializable (pydantic JsonValue). Datetime/AnyUrl -> string
            def _coerce_jsonable(obj):
                import datetime

                from pydantic import AnyUrl

                if isinstance(obj, dict):
                    return {k: _coerce_jsonable(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_coerce_jsonable(v) for v in obj]
                if isinstance(obj, (datetime.datetime, datetime.date)):
                    try:
                        return obj.isoformat()
                    except Exception:
                        return str(obj)
                if isinstance(obj, AnyUrl):
                    return str(obj)
                return obj

            data = _coerce_jsonable(data)

            msg = Message(
                topics=self.message.topics,
                format=format,
                sender=self.agent.get_agent_tag(),
                payload=data,
                id_obj=id_obj,
                in_response_to=self.message.id,
                thread=self.message.thread,
                recipient_list=[],
                message_history=[process_entry],
                session_state=session_state,
            )

            results.append(msg)

            return [id_obj]

    guild_spec = GuildBuilder(f"{agent_spec.id}_test_guild", "Test Guild", "Test Guild").build_spec()
    client_class = MagicMock()
    client_props: JsonDict = {}

    agent = build_agent_from_spec(
        agent_spec,
        guild_spec,
        dependency_map,
        client_class,
        client_props,
        1,
    )

    agent._make_process_context = MagicMock()  # type: ignore
    agent._make_process_context.side_effect = lambda message, mname, payload_type, sf, ef, omf: MockProcessContext(
        agent, message, mname, payload_type
    )

    def process_message(self, message: Message):
        message.topic_published_to = message.topics[0]
        self._original_on_message(message)

    agent._original_on_message = agent._on_message  # type: ignore

    agent._on_message = partial(process_message, agent)  # type: ignore

    return agent, results
