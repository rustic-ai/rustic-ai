"""Integration tests for complete Socket Mode flow"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rustic_ai.slack.models.events import SlackEventMessage


@pytest.fixture
def guild_spec_path():
    """Get path to slack_guild.json"""
    return Path(__file__).parent.parent / "slack_guild.json"


@pytest.fixture
def mock_env_tokens(monkeypatch):
    """Mock environment variables"""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    yield


class TestGuildSpecification:
    """Tests for guild specification"""

    def test_guild_spec_valid_json(self, guild_spec_path):
        """Test that guild spec is valid JSON"""
        with open(guild_spec_path) as f:
            spec = json.load(f)

        assert "name" in spec
        assert "description" in spec
        assert "spec" in spec
        assert "agents" in spec["spec"]

    def test_guild_spec_has_required_agents(self, guild_spec_path):
        """Test that guild spec includes all required agents"""
        with open(guild_spec_path) as f:
            spec = json.load(f)

        agent_names = [agent["name"] for agent in spec["spec"]["agents"]]

        # Required agents for Socket Mode
        assert "SlackSocketMode" in agent_names
        assert "SlackEventHandler" in agent_names
        assert "SlackConnector" in agent_names
        assert "SlackLLM" in agent_names

    def test_guild_spec_has_correct_topics(self, guild_spec_path):
        """Test that agents subscribe to correct topics"""
        with open(guild_spec_path) as f:
            spec = json.load(f)

        agents = {agent["name"]: agent for agent in spec["spec"]["agents"]}

        # Check topic subscriptions
        assert "SLACK_INBOUND" in agents["SlackEventHandler"]["additional_topics"]
        assert "SLACK_API" in agents["SlackConnector"]["additional_topics"]
        assert "SLACK_CHAT" in agents["SlackLLM"]["additional_topics"]

    def test_guild_spec_has_routing(self, guild_spec_path):
        """Test that guild spec includes routing configuration"""
        with open(guild_spec_path) as f:
            spec = json.load(f)

        assert "routing_slip" in spec["spec"] or "routes" in spec["spec"]

    def test_guild_spec_agent_types(self, guild_spec_path):
        """Test that agent types are correct"""
        with open(guild_spec_path) as f:
            spec = json.load(f)

        agents = {agent["name"]: agent for agent in spec["spec"]["agents"]}

        assert "socket_mode_agent" in agents["SlackSocketMode"]["class_name"].lower()
        assert "event_handler_agent" in agents["SlackEventHandler"]["class_name"].lower()
        assert "connector_agent" in agents["SlackConnector"]["class_name"].lower()


class TestErrorRecovery:
    """Test error handling and recovery"""

    @pytest.mark.asyncio
    async def test_socket_mode_handles_connection_failure(self, mock_env_tokens):
        """Test that Socket Mode handles connection failures gracefully"""
        from rustic_ai.slack.agents.socket_mode_agent import SlackSocketModeAgent

        with patch('rustic_ai.slack.agents.socket_mode_agent.SocketModeClient') as mock_client, \
             patch('rustic_ai.slack.agents.socket_mode_agent.WebClient'):

            # Make connect fail
            mock_client.return_value.connect.side_effect = Exception("Connection failed")

            agent = SlackSocketModeAgent()
            agent._app_token = "xapp-test"
            agent._bot_token = "xoxb-test"
            agent._socket_client = mock_client.return_value

            # Should not raise exception
            agent._run_socket_mode()

            # Should mark as not connected
            assert agent._is_connected is False

    def test_event_handler_handles_processing_errors(self):
        """Test that Event Handler handles processing errors"""
        # This is tested in test_event_handler_agent.py::test_error_handling
        pass


class TestPerformance:
    """Performance and load tests"""

    def test_event_model_performance(self):
        """Test that event models perform well"""
        import time

        start = time.time()
        for i in range(1000):
            event = SlackEventMessage(
                event_type="app_mention",
                workspace_id="T123",
                user="U456",
                channel="C789",
                ts=f"{i}.123456",
                text=f"message {i}",
                event_ts=f"{i}.123456"
            )
            _ = event.model_dump()

        elapsed = time.time() - start
        # Should be able to create and serialize 1000 events quickly
        assert elapsed < 1.0  # Less than 1 second

    def test_mention_cleaning_performance(self):
        """Test mention cleaning performance"""
        import time

        from rustic_ai.slack.agents.event_handler_agent import SlackEventHandlerAgent

        agent = SlackEventHandlerAgent()
        text = "<@U123BOT> " * 10 + "hello " * 100

        start = time.time()
        for _ in range(100):
            _ = agent._clean_mention_text(text)
        elapsed = time.time() - start

        # Should be fast
        assert elapsed < 0.1  # Less than 100ms for 100 iterations
