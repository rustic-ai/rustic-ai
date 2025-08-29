import os

import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    FinishReason,
    Role,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestBasicLLMAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_invoke_llm(self, generator, build_message_from_payload, dependency_map):
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("An agent that uses a large language model")
            .set_properties(
                LLMAgentConfig(
                    model="gpt-5-mini", default_system_prompt="You are a helpful assistant. Your name is Astro."
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
                        UserMessage(content="Hello, how are you? What is your name?"),
                    ],
                ),
            )
        )

        assert len(results) > 0
        result = results[0]
        assert result.format == get_qualified_class_name(ChatCompletionResponse)

        assert len(result.message_history) > 0
        pe = result.message_history[0]
        assert pe.processor == LLMAgent.invoke_llm.__name__

        payload = ChatCompletionResponse.model_validate(result.payload)

        assert len(payload.choices) > 0

        first_choice = payload.choices[0]

        assert first_choice.finish_reason == FinishReason.stop

        response = first_choice.message.content
        assert isinstance(response, str)
        assert len(response) > 1
        assert "Astro" in response

        input_messages = payload.input_messages

        assert len(input_messages) > 0

        system_message = input_messages[0]
        assert system_message.role == Role.system
        assert system_message.content == "You are a helpful assistant. Your name is Astro."

        user_message = input_messages[1]
        assert user_message.role == Role.user
        assert user_message.content == "Hello, how are you? What is your name?"

        usage = payload.usage
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
