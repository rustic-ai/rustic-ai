import time

import pytest
from rustic_ai.litellm.agent import LiteLLMAgent
from rustic_ai.litellm.conf import LiteLLMConf

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    Models,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.guild import Guild


class TestLiteLLMAgent:
    def test_agent_initialization(self):
        with pytest.raises(RuntimeError, match=".*GEMINI_API_KEY not set"):
            AgentBuilder(LiteLLMAgent).set_name("Test Agent").set_description("A test agent").set_id(
                "lite_llm_agent"
            ).set_properties(
                LiteLLMConf(
                    model=Models.gemini_pro,
                    messages=[
                        SystemMessage(content="You are a helpful assistant."),
                    ],
                )
            ).build()

    def test_response_is_generated(self, probe_agent: ProbeAgent, guild: Guild):
        agent = (
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
            .build()
        )

        guild._add_local_agent(agent)
        guild._add_local_agent(probe_agent)

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
