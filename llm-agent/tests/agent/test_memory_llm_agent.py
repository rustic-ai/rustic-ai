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
from rustic_ai.llm_agent.memories.queue_memories_store import QueueBasedMemoriesStore

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestMemoryEnabledLLMAgent:

    @pytest.fixture
    def agent_spec(self):
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_id("llm_agent")
            .set_name("LLM Agent")
            .set_description("An agent that uses a large language model with memory")
            .set_properties(
                LLMAgentConfig(
                    model="gpt-5-mini",
                    default_system_prompt="You are a helpful assistant.",
                    llm_request_wrappers=[QueueBasedMemoriesStore(memory_queue_size=5)],
                )
            )
            .build_spec()
        )
        return agent_spec

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_invoke_llm_with_memory_queue(self, agent_spec, generator, build_message_from_payload, dependency_map):
        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        # First user message
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        UserMessage(
                            content="Hello, We will name you Astro. What should be the name of your best friend? Reply only with the name."
                        ),
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

        friends_name = first_choice.message.content

        # Validate input messages include system and user
        input_messages = payload.input_messages

        assert len(input_messages) > 0

        # Validate that is remembers the user provided info (Agent's Name)
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        UserMessage(content="Based on our last chat, remind me of your name."),
                    ],
                ),
            )
        )

        assert len(results) > 1
        second = results[1]
        assert second.format == get_qualified_class_name(ChatCompletionResponse)
        payload2 = ChatCompletionResponse.model_validate(second.payload)
        assert len(payload2.input_messages) >= 2

        # The memory queue should have captured prior user and assistant messages; at least system + memory + new user
        # We assert system is first and the latest user is present
        assert payload2.input_messages[0].role == Role.system
        assert payload2.input_messages[-1].role == Role.user
        assert payload2.input_messages[-1].content == "Based on our last chat, remind me of your name."

        # Sanity check response
        first_choice2 = payload2.choices[0]
        assert first_choice2.finish_reason == FinishReason.stop
        assert isinstance(first_choice2.message.content, str)
        assert "Astro" in first_choice2.message.content

        # Validate that is remembers it's own past generation (Best friend's Name)
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        UserMessage(content="What is your best friend's name?"),
                    ],
                ),
            )
        )

        assert len(results) > 2
        third = results[2]
        assert third.format == get_qualified_class_name(ChatCompletionResponse)
        payload3 = ChatCompletionResponse.model_validate(third.payload)
        assert len(payload3.input_messages) >= 3

        # Sanity check response
        first_choice3 = payload3.choices[0]
        assert first_choice3.finish_reason == FinishReason.stop
        assert isinstance(first_choice3.message.content, str)
        assert friends_name in first_choice3.message.content
