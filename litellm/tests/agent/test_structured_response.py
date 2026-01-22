import json
import os
import time

from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.litellm.agent import LiteLLMAgent
from rustic_ai.litellm.conf import LiteLLMConf


class CalendarEvent(BaseModel):
    name: str
    year: int
    participants: list[str]


class EventsList(BaseModel):
    events: list[CalendarEvent]


class TestStructuredResponse:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_pydantic_class_fmt(self, probe_spec, guild: Guild):
        agent_spec = (
            AgentBuilder(LiteLLMAgent)
            .set_name("Test Agent")
            .set_description("A test agent")
            .set_properties(
                LiteLLMConf(
                    model="vertex_ai/gemini-3-pro-preview",
                    vertex_location="global",
                    enable_json_schema_validation=True,
                )
            )
            .build_spec()
        )

        guild._add_local_agent(agent_spec)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        chat_completion_request = ChatCompletionRequest(
            messages=[UserMessage(content="5 important events in the XIX century")],
            response_format=get_qualified_class_name(EventsList)
        )

        probe_agent.publish(
            guild.DEFAULT_TOPIC,
            payload=chat_completion_request,
            in_response_to=1
        )

        time.sleep(1)

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].topics == guild.DEFAULT_TOPIC
        assert messages[0].format == get_qualified_class_name(ChatCompletionResponse)
        payload = messages[0].payload
        json_response = payload["choices"][0]["message"]["content"]
        result = json.loads(json_response)
        event_list = EventsList.model_validate(result)
        assert len(event_list.events) == 5

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_raw_json_schema(self, probe_spec, guild: Guild):
        agent_spec = (
            AgentBuilder(LiteLLMAgent)
            .set_name("Test Agent")
            .set_description("A test agent")
            .set_properties(
                LiteLLMConf(
                    model="gemini-3-pro-preview",
                    vertex_location="global",
                    enable_json_schema_validation=True
                )
            )
            .build_spec()
        )

        guild._add_local_agent(agent_spec)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        chat_completion_request = ChatCompletionRequest(
            messages=[UserMessage(content="List ingredients of Chocolate Chip Cookies.")],
            response_format={"type": "array", "items": {"type": "string"}, "maxItems": 6}
        )

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            chat_completion_request,
            in_response_to=1,
            format=ChatCompletionRequest,
        )

        time.sleep(1)

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].topics == guild.DEFAULT_TOPIC
        assert messages[0].format == get_qualified_class_name(ChatCompletionResponse)
        payload = messages[0].payload
        json_response = payload["choices"][0]["message"]["content"]
        result = json.loads(json_response)
        assert len(result) <= 6
        assert all(isinstance(elem, str) for elem in result)
