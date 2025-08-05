import os
import time

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Models,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging.core.message import (
    FunctionalTransformer,
    RoutingRule,
    RoutingSlip,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.jexpr import JObj, JxScript
from rustic_ai.litellm.agent import LiteLLMAgent
from rustic_ai.litellm.conf import LiteLLMConf

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def setup_default_env(monkeypatch):
    if "OPENAI_API_KEY" not in os.environ:
        monkeypatch.setenv("OPENAI_API_KEY", "dummy_key")


class TestLiteLLMAgent:
    def test_agent_initialization(self):
        GEMINI_API_KEY = None
        GOOGLE_API_KEY = None
        if "GEMINI_API_KEY" in os.environ:
            GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
            del os.environ["GEMINI_API_KEY"]

        if "GOOGLE_API_KEY" in os.environ:
            GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
            del os.environ["GOOGLE_API_KEY"]
        with pytest.raises(RuntimeError, match=".*GEMINI_API_KEY not set"):
            spec = (
                AgentBuilder(LiteLLMAgent)
                .set_name("Test Agent")
                .set_description("A test agent")
                .set_id("lite_llm_agent")
                .set_properties(
                    LiteLLMConf(
                        model=Models.gemini_2_5_flash,
                        messages=[
                            SystemMessage(content="You are a helpful assistant."),
                        ],
                    )
                )
                .build_spec()
            )
            wrap_agent_for_testing(spec)
        if GEMINI_API_KEY:
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
        if GOOGLE_API_KEY:
            os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

    def test_response_is_generated(self, setup_default_env, probe_spec, guild: Guild):
        agent_spec = (
            AgentBuilder(LiteLLMAgent)
            .set_name("Test Agent")
            .set_description("A test agent")
            .set_id("lite_llm_agent")
            .set_properties(
                LiteLLMConf(
                    model=Models.gpt_3_5_turbo_16k,
                    messages=[
                        SystemMessage(content="You are a helpful assistant."),
                    ],
                )
            )
            .build_spec()
        )

        agent = guild._add_local_agent(agent_spec)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        chat_completion_request = ChatCompletionRequest(
            messages=[UserMessage(content="What is the capital of India?")],
            mock_response="Capital of India is New Delhi.",
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
        result = ChatCompletionResponse.model_validate(payload)
        assert "New Delhi" in result.choices[0].message.content

        chat_completion_request2 = ChatCompletionRequest(
            messages=[UserMessage(content="What is the capital of Telangana?")],
        )

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            chat_completion_request2,
            in_response_to=messages[0].id,
            format=ChatCompletionRequest,
            routing_slip=RoutingSlip(
                steps=[
                    RoutingRule(
                        agent=agent.get_agent_tag(),
                        method_name="llm_completion",
                        transformer=FunctionalTransformer(
                            handler=JxScript(JObj({"enrich_with_history": 3})).serialize()
                        ),
                    )
                ]
            ),
        )

        time.sleep(3)

        messages = probe_agent.get_messages()

        assert len(messages[1].message_history) == 1

        assert len(messages[1].session_state["enriched_history"]) == 1
