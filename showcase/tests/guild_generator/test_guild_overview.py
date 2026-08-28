"""
Tests for the guild overview functionality in StateManagerAgent.

Tests the new markdown-based guild overview that replaced FlowchartAgent.
"""

import pytest
from pydantic import BaseModel

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    OrchestratorAction,
)
from rustic_ai.showcase.guild_generator.state_manager import StateManagerAgent
from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def generator():
    return GemstoneGenerator(machine_id=1)


@pytest.fixture
def build_message_from_payload():
    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
        session_state: dict | None = None,
    ) -> Message:
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            payload=payload_dict,
            format=computed_format,
            session_state=session_state or {},
            topics=["test-topic"],
        )

    return _build_message_from_payload


class TestGuildOverview:
    """Tests for the guild overview generation."""

    def test_generate_guild_overview_empty(self):
        """Test overview generation with no agents or routes."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, _ = wrap_agent_for_testing(agent_spec)

        # Initialize with empty state
        agent._local_guild_builder = {
            "name": "Test Guild",
            "description": "A test guild",
            "agents": [],
            "routes": [],
            "agent_message_info": [],
        }

        overview = agent._generate_guild_overview()

        # Check header
        assert "# Test Guild" in overview
        assert "A test guild" in overview

        # Check empty states
        assert "*No agents added yet.*" in overview
        assert "*No routes configured yet.*" in overview

        # Check tip for empty guild
        assert "Start by adding an agent" in overview

    def test_generate_guild_overview_with_agents(self):
        """Test overview generation with agents but no routes."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, _ = wrap_agent_for_testing(agent_spec)

        # Initialize with agents
        agent._local_guild_builder = {
            "name": "Test Guild",
            "description": "A test guild",
            "agents": [
                {
                    "id": "agent1",
                    "name": "Text Summarizer",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "description": "Summarizes text input",
                },
                {
                    "id": "agent2",
                    "name": "Mindmap Generator",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "description": "Creates mindmaps from text",
                },
            ],
            "routes": [],
            "agent_message_info": [
                {
                    "agent_id": "agent1",
                    "agent_name": "Text Summarizer",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "input_formats": ["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"],
                    "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                },
                {
                    "agent_id": "agent2",
                    "agent_name": "Mindmap Generator",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "input_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                    "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                },
            ],
        }

        overview = agent._generate_guild_overview()

        # Check agents table
        assert "## 📦 Agents" in overview
        assert "Text Summarizer" in overview
        assert "Mindmap Generator" in overview
        assert "`LLMAgent`" in overview
        assert "ChatCompletionRequest" in overview
        assert "TextFormat" in overview

        # Check routes section is empty
        assert "*No routes configured yet.*" in overview

        # Check tip for adding routes
        assert "Connect your agents" in overview

    def test_generate_guild_overview_with_routes(self):
        """Test overview generation with both agents and routes."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, _ = wrap_agent_for_testing(agent_spec)

        # Initialize with agents and routes
        agent._local_guild_builder = {
            "name": "Complete Guild",
            "description": "A complete guild with routes",
            "agents": [
                {
                    "id": "agent1",
                    "name": "Text Summarizer",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "description": "Summarizes text",
                }
            ],
            "routes": [
                {
                    "agent": {"name": "Text Summarizer"},
                    "message_format": "rustic_ai.core.ui_protocol.types.TextFormat",
                    "destination": {"topics": "user_message_broadcast"},
                    "transformer": {"style": "jsonata", "expression": "$.payload"},
                    "process_status": "completed",
                },
                {
                    "agent_type": "rustic_ai.core.agents.utils.user_proxy_agent.UserProxyAgent",
                    "message_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
                    "destination": {"topics": "agent1"},
                    "process_status": "ongoing",
                },
            ],
            "agent_message_info": [
                {
                    "agent_id": "agent1",
                    "agent_name": "Text Summarizer",
                    "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                    "input_formats": ["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"],
                    "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                }
            ],
        }

        overview = agent._generate_guild_overview()

        # Check routes table
        assert "## 🔀 Routes" in overview
        assert "Text Summarizer" in overview
        assert "user_message_broadcast" in overview
        assert "UserProxyAgent" in overview
        assert "`TextFormat`" in overview
        assert "`ChatCompletionRequest`" in overview

        # Check transformer column
        assert "✓" in overview  # Has transformer
        assert "-" in overview  # No transformer

        # Check status column
        assert "completed" in overview
        assert "ongoing" in overview

        # Check tip for exporting
        assert "Export your guild" in overview

    def test_generate_guild_overview_truncates_long_descriptions(self):
        """Test that long agent descriptions are truncated in the table."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, _ = wrap_agent_for_testing(agent_spec)

        long_description = "A" * 100  # Long description

        agent._local_guild_builder = {
            "name": "Test Guild",
            "description": "Test",
            "agents": [
                {
                    "id": "agent1",
                    "name": "Test Agent",
                    "class_name": "test.TestAgent",
                    "description": long_description,
                }
            ],
            "routes": [],
            "agent_message_info": [],
        }

        overview = agent._generate_guild_overview()

        # Should truncate at 50 chars
        assert "..." in overview
        # Should not have full 100 chars
        assert long_description not in overview

    def test_show_flow_processor(self, generator, build_message_from_payload):
        """Test that show_flow processor sends guild overview."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(agent_spec)

        # Initialize with some state
        agent._local_guild_builder = {
            "name": "Test Guild",
            "description": "A test guild",
            "agents": [
                {
                    "id": "agent1",
                    "name": "Test Agent",
                    "class_name": "test.TestAgent",
                    "description": "Test",
                }
            ],
            "routes": [],
            "agent_message_info": [],
        }

        # Send SHOW_FLOW action
        action = OrchestratorAction(
            action=ActionType.SHOW_FLOW,
            details={},
            user_message="@Orchestrator show flow",
        )

        agent._on_message(build_message_from_payload(generator, action))

        # Should send TextFormat with overview
        assert len(results) == 1
        assert results[0].format == get_qualified_class_name(TextFormat)

        text_payload = TextFormat.model_validate(results[0].payload)
        assert "Test Guild" in text_payload.text
        assert "Test Agent" in text_payload.text
        assert "## 📦 Agents" in text_payload.text
        assert "## 🔀 Routes" in text_payload.text

    def test_generate_guild_overview_with_multiple_destination_topics(self):
        """Test overview generation when route has list of destination topics."""
        agent_spec = (
            AgentBuilder(StateManagerAgent)
            .set_id("state_manager")
            .set_name("State Manager")
            .set_description("Test state manager")
            .build_spec()
        )

        agent, _ = wrap_agent_for_testing(agent_spec)

        agent._local_guild_builder = {
            "name": "Test Guild",
            "description": "Test",
            "agents": [],
            "routes": [
                {
                    "agent": {"name": "Splitter"},
                    "message_format": "rustic_ai.core.ui_protocol.types.TextFormat",
                    "destination": {"topics": ["agent1", "agent2", "agent3"]},
                    "process_status": "ongoing",
                }
            ],
            "agent_message_info": [],
        }

        overview = agent._generate_guild_overview()

        # Should join multiple topics with comma
        assert "agent1, agent2, agent3" in overview
