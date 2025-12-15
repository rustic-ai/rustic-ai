import logging
import os
import pytest
from rustic_ai.claude.agent import ClaudeCodeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import Message, AgentTag
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UserMessage,
)
from rustic_ai.core.utils.priority import Priority
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class MockContext:
    def __init__(self, agent, message, payload):
        self.agent = agent
        self._message = message
        self._payload = payload
        self.sent_messages = []
        self.sent_errors = []

    @property
    def payload(self):
        return self._payload

    @property
    def message(self):
        return self._message

    def send(self, data, **kwargs):
        self.sent_messages.append(data)

    def send_error(self, payload, **kwargs):
        self.sent_errors.append(payload)


@pytest.mark.asyncio
class TestClaudeAgent:
    async def test_claude_agent_integration(self):
        """
        Integration test for ClaudeCodeAgent.
        Connects to the actual Claude Code agent SDK and verifies message flow.
        """
        # Initialize the agent
        agent, results = wrap_agent_for_testing(
            AgentBuilder(ClaudeCodeAgent)
            .set_name("TestClaudeAgent")
            .set_id("test_claude_agent")
            .set_description("Test Claude Agent")
            .build_spec()
        )

        req_payload = ChatCompletionRequest(
            messages=[UserMessage(content="Hello! Please reply with 'pong' and nothing else.")],
            model="claude-code",
        )

        message = Message(
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            format=get_qualified_class_name(ChatCompletionRequest),
            payload=req_payload.model_dump(),
            id_obj=agent._generate_id(Priority.NORMAL),
        )

        agent._on_message(message)

        logging.info(results)

        assert len(results) > 0
        assert results[0].priority == Priority.NORMAL
        assert results[0].in_response_to == message.id

        result = ChatCompletionResponse.model_validate(results[0].payload)
        assert result.choices[0].message.content == 'pong'