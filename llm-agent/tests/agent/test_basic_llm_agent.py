import os

import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    FinishReason,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.basic_llm_agent import BasicLLMAgent, BasicLLMAgentConfig

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestBasicLLMAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_invoke_llm(self, generator, build_message_from_payload, dependency_map):
        agent_spec: AgentSpec = (
            AgentBuilder(BasicLLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("An agent that uses a large language model")
            .set_properties(
                BasicLLMAgentConfig(
                    model="gpt-5-mini",
                    system_prompt="You are a helpful assistant.",
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        SystemMessage(content="You are a helpful assistant."),
                        UserMessage(content="Hello, how are you?"),
                    ],
                ),
            )
        )

        assert len(results) > 0
        result = results[0]
        assert result.format == get_qualified_class_name(ChatCompletionResponse)

        assert len(result.message_history) > 0
        pe = result.message_history[0]
        assert pe.processor == BasicLLMAgent.invoke_llm.__name__

        payload = ChatCompletionResponse.model_validate(result.payload)

        assert len(payload.choices) > 0

        first_choice = payload.choices[0]

        assert first_choice.finish_reason == FinishReason.stop
        assert isinstance(first_choice.message.content, str)
        assert len(first_choice.message.content) > 1

        usage = payload.usage

        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
