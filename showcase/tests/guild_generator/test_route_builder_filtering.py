"""
Tests for the agent filtering functionality in RouteBuilderAgent.

Tests that excluded agents are filtered from the agent list shown to the LLM.
"""

import pytest

from rustic_ai.showcase.guild_generator.route_builder import RouteBuilderAgent, RouteBuilderAgentProps


class TestRouteBuilderFiltering:
    """Tests for agent filtering in RouteBuilderAgent."""

    def test_is_agent_excluded_simple_class_name(self):
        """Test filtering by simple class name."""
        # Create agent directly without wrap_agent_for_testing to avoid LLM dependency issues
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(excluded_agents=["FlowchartAgent", "GuildExportAgent"])

        # Should exclude FlowchartAgent
        assert agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
            "Flowchart Agent"
        )

        # Should exclude GuildExportAgent
        assert agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.guild_export.GuildExportAgent",
            "Guild Export"
        )

        # Should NOT exclude other agents
        assert not agent._is_agent_excluded(
            "rustic_ai.llm_agent.llm_agent.LLMAgent",
            "LLM Agent"
        )

    def test_is_agent_excluded_by_agent_name(self):
        """Test filtering by agent display name."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(excluded_agents=["Flowchart Agent", "Guild Export"])

        # Should exclude by name match
        assert agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
            "Flowchart Agent"
        )

        # Should NOT exclude if name doesn't match
        assert not agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
            "Different Name"
        )

    def test_is_agent_excluded_fully_qualified_name(self):
        """Test filtering by fully qualified class name."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(
            excluded_agents=["rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent"]
        )

        # Should exclude by exact match
        assert agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
            "Flowchart Agent"
        )

        # Should NOT exclude different class
        assert not agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.other_agent.FlowchartAgent",
            "Flowchart Agent"
        )

    def test_get_agent_message_info_filters_excluded(self):
        """Test that _get_agent_message_info filters out excluded agents."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(excluded_agents=["FlowchartAgent", "GuildExportAgent"])

        # Mock guild state with various agents
        agent._guild_state = {
            "guild_builder": {
                "agent_message_info": [
                    {
                        "agent_id": "llm_agent",
                        "agent_name": "LLM Agent",
                        "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                        "input_formats": ["TextFormat"],
                        "output_formats": ["TextFormat"],
                    },
                    {
                        "agent_id": "flowchart_agent",
                        "agent_name": "Flowchart Agent",
                        "class_name": "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
                        "input_formats": ["FlowchartUpdateRequest"],
                        "output_formats": ["VegaLiteFormat"],
                    },
                    {
                        "agent_id": "guild_export",
                        "agent_name": "Guild Export",
                        "class_name": "rustic_ai.showcase.guild_generator.guild_export.GuildExportAgent",
                        "input_formats": ["ExportRequest"],
                        "output_formats": ["ExportResponse"],
                    },
                ]
            }
        }

        # Mock get_guild_state method
        agent.get_guild_state = lambda: agent._guild_state

        agent_info = agent._get_agent_message_info()

        # Should include LLM Agent
        assert "LLM Agent" in agent_info

        # Should NOT include FlowchartAgent
        assert "Flowchart Agent" not in agent_info
        assert "FlowchartUpdateRequest" not in agent_info
        assert "VegaLiteFormat" not in agent_info

        # Should NOT include GuildExportAgent
        assert "Guild Export" not in agent_info
        assert "ExportRequest" not in agent_info

        # Should still include UserProxyAgent
        assert "UserProxyAgent" in agent_info

    def test_default_excluded_agents(self):
        """Test that FlowchartAgent and GuildExportAgent are excluded by default."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps()  # Use defaults

        # Should have default exclusions
        assert "FlowchartAgent" in agent.config.excluded_agents
        assert "GuildExportAgent" in agent.config.excluded_agents

    def test_custom_excluded_agents(self):
        """Test that custom excluded agents can be specified."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(excluded_agents=["CustomAgent", "AnotherAgent"])

        # Should have custom exclusions
        assert agent.config.excluded_agents == ["CustomAgent", "AnotherAgent"]

        # Should exclude custom agents
        assert agent._is_agent_excluded(
            "test.CustomAgent",
            "Custom Agent"
        )

    def test_empty_excluded_agents_list(self):
        """Test that an empty exclusion list doesn't filter any agents."""
        agent = RouteBuilderAgent.__new__(RouteBuilderAgent)
        agent.config = RouteBuilderAgentProps(excluded_agents=[])

        # Should NOT exclude any agents
        assert not agent._is_agent_excluded(
            "rustic_ai.showcase.guild_generator.flowchart_agent.FlowchartAgent",
            "Flowchart Agent"
        )
        assert not agent._is_agent_excluded(
            "rustic_ai.llm_agent.llm_agent.LLMAgent",
            "LLM Agent"
        )
