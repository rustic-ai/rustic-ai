import os
import shutil

import pytest

from rustic_ai.claude.agent import (
    AddClaudeAgentRequest,
    AddClaudeSkillRequest,
    ClaudeCodeAgent,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def cleanup_claude_dir():
    # Cleanup before test
    if os.path.exists("./.claude"):
        shutil.rmtree("./.claude")
    yield
    # Cleanup after test
    if os.path.exists("./.claude"):
        shutil.rmtree("./.claude")


@pytest.mark.asyncio
class TestClaudeDynamicLoading:
    @pytest.mark.skipif(
        os.getenv("ANTHROPIC_VERTEX_PROJECT_ID") is None,
        reason="ANTHROPIC_VERTEX_PROJECT_ID environment variable not set",
    )
    async def test_add_agent_via_message(self, cleanup_claude_dir):
        # Initialize agent
        agent, results = wrap_agent_for_testing(
            AgentBuilder(ClaudeCodeAgent)
            .set_name("TestClaudeAgent")
            .set_id("test_claude_agent")
            .set_description("Test Claude Agent")
            .build_spec()
        )

        # Prepare payload
        request_payload = AddClaudeAgentRequest(name="test_agent_msg", config="# Agent Config via Msg")

        # Create message
        message = Message(
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            format=get_qualified_class_name(AddClaudeAgentRequest),
            payload=request_payload.model_dump(),
            id_obj=agent._generate_id(Priority.NORMAL),
        )

        # Send message
        agent._on_message(message)

        # Verify file creation
        assert os.path.exists("./.claude/agents/test_agent_msg.md")
        with open("./.claude/agents/test_agent_msg.md", "r") as f:
            assert f.read() == "# Agent Config via Msg"

    @pytest.mark.skipif(
        os.getenv("ANTHROPIC_VERTEX_PROJECT_ID") is None,
        reason="ANTHROPIC_VERTEX_PROJECT_ID environment variable not set",
    )
    async def test_add_skill_via_message(self, cleanup_claude_dir):
        # Initialize agent
        agent, results = wrap_agent_for_testing(
            AgentBuilder(ClaudeCodeAgent)
            .set_name("TestClaudeAgent")
            .set_id("test_claude_agent")
            .set_description("Test Claude Agent")
            .build_spec()
        )

        # Prepare payload
        request_payload = AddClaudeSkillRequest(name="test_skill_msg", skill="# Skill Content via Msg")

        # Create message
        message = Message(
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            format=get_qualified_class_name(AddClaudeSkillRequest),
            payload=request_payload.model_dump(),
            id_obj=agent._generate_id(Priority.NORMAL),
        )

        # Send message
        agent._on_message(message)

        # Verify file creation
        assert os.path.exists("./.claude/skills/test_skill_msg.md")
        with open("./.claude/skills/test_skill_msg.md", "r") as f:
            assert f.read() == "# Skill Content via Msg"
