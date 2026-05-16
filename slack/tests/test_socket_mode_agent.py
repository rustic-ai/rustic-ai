"""Unit tests for SlackSocketModeAgent"""

import time
from unittest.mock import MagicMock, patch

import pytest
from slack_sdk.socket_mode.request import SocketModeRequest

from rustic_ai.slack.agents.socket_mode_agent import SlackSocketModeAgent
from rustic_ai.slack.models.events import SlackEventMessage


@pytest.fixture
def socket_mode_agent():
    """Create a SlackSocketModeAgent instance for testing"""
    # Create a minimal instance without full initialization
    agent = object.__new__(SlackSocketModeAgent)
    agent._socket_client = None
    agent._socket_thread = None
    agent._app_token = None
    agent._bot_token = None
    agent._workspace_id = None
    agent._bot_user_id = None
    agent._is_connected = False
    # Add required Agent attributes
    agent._agent_tag = MagicMock()
    agent._send_dict_to_self = MagicMock()
    agent._id_generator = MagicMock()
    agent._self_inbox = "test_inbox"
    return agent


@pytest.fixture
def mock_slack_client():
    """Mock SocketModeClient"""
    with patch('rustic_ai.slack.agents.socket_mode_agent.SocketModeClient') as mock:
        client = MagicMock()
        client.socket_mode_request_listeners = []
        client.connect = MagicMock()
        client.close = MagicMock()
        client.send_socket_mode_response = MagicMock()
        mock.return_value = client
        yield mock


@pytest.fixture
def mock_web_client():
    """Mock WebClient for auth"""
    with patch('rustic_ai.slack.agents.socket_mode_agent.WebClient') as mock:
        client = MagicMock()
        client.auth_test = MagicMock(return_value={
            "ok": True,
            "user": "testbot",
            "user_id": "U123BOT",
            "team": "TestTeam",
            "team_id": "T123WORKSPACE"
        })
        mock.return_value = client
        yield mock


@pytest.fixture
def mock_env_tokens(monkeypatch):
    """Mock environment variables with tokens"""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-bot-token")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-app-token")
    yield


class TestSocketModeAgentCreation:
    """Tests for agent creation and initialization"""

    def test_agent_creation(self, socket_mode_agent):
        """Test that agent can be created"""
        assert socket_mode_agent is not None
        assert isinstance(socket_mode_agent, SlackSocketModeAgent)

    def test_agent_initial_state(self, socket_mode_agent):
        """Test agent initial state"""
        assert socket_mode_agent._socket_client is None
        assert socket_mode_agent._socket_thread is None
        assert socket_mode_agent._app_token is None
        assert socket_mode_agent._bot_token is None
        assert socket_mode_agent._workspace_id is None
        assert socket_mode_agent._bot_user_id is None
        assert socket_mode_agent._is_connected is False

    def test_get_connection_status_before_connection(self, socket_mode_agent):
        """Test connection status before connecting"""
        status = socket_mode_agent.get_connection_status()
        assert status["connected"] is False
        assert status["workspace_id"] is None
        assert status["bot_user_id"] is None


class TestSocketModeConnection:
    """Tests for Socket Mode connection"""

    def test_init_with_tokens(
        self, mock_env_tokens, mock_slack_client, mock_web_client
    ):
        """Test __init__ starts Socket Mode with tokens"""
        # Create agent (initialization happens in __init__)
        agent = SlackSocketModeAgent()

        # Should have read tokens from environment
        assert agent._app_token == "xapp-test-app-token"
        assert agent._bot_token == "xoxb-test-bot-token"

        # Give thread time to start
        time.sleep(0.1)

        # Should have created SocketModeClient
        mock_slack_client.assert_called_once()

        # Should have started background thread
        assert agent._socket_thread is not None
        assert agent._socket_thread.daemon is True
        assert agent._socket_thread.name == "slack-socket-mode"

    def test_init_without_app_token(self, monkeypatch):
        """Test __init__ fails gracefully without app token"""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        # SLACK_APP_TOKEN not set

        agent = SlackSocketModeAgent()

        # Should not have created client
        assert agent._socket_client is None

    def test_init_without_bot_token(self, monkeypatch):
        """Test __init__ fails gracefully without bot token"""
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
        # SLACK_BOT_TOKEN not set

        agent = SlackSocketModeAgent()

        # Should not have created client
        assert agent._socket_client is None

    def test_run_socket_mode_success(
        self, socket_mode_agent, mock_env_tokens, mock_slack_client, mock_web_client
    ):
        """Test _run_socket_mode connects successfully"""
        socket_mode_agent._app_token = "xapp-test"
        socket_mode_agent._bot_token = "xoxb-test"
        socket_mode_agent._socket_client = mock_slack_client.return_value

        # Run in main thread for testing
        socket_mode_agent._run_socket_mode()

        # Should have authenticated
        mock_web_client.return_value.auth_test.assert_called_once()

        # Should have set workspace and bot IDs
        assert socket_mode_agent._workspace_id == "T123WORKSPACE"
        assert socket_mode_agent._bot_user_id == "U123BOT"

        # Should have connected
        socket_mode_agent._socket_client.connect.assert_called_once()
        assert socket_mode_agent._is_connected is True

    def test_run_socket_mode_connection_error(
        self, socket_mode_agent, mock_env_tokens, mock_slack_client, mock_web_client
    ):
        """Test _run_socket_mode handles connection errors"""
        socket_mode_agent._app_token = "xapp-test"
        socket_mode_agent._bot_token = "xoxb-test"
        socket_mode_agent._socket_client = mock_slack_client.return_value

        # Make connect fail
        socket_mode_agent._socket_client.connect.side_effect = Exception("Connection failed")

        # Should not raise exception
        socket_mode_agent._run_socket_mode()

        # Should mark as not connected
        assert socket_mode_agent._is_connected is False


class TestEventHandling:
    """Tests for event handling"""

    def test_handle_socket_mode_request_ack(self, socket_mode_agent):
        """Test that socket mode requests are acknowledged"""

        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"

        mock_client = MagicMock()
        mock_req = MagicMock(spec=SocketModeRequest)
        mock_req.envelope_id = "env-123"
        mock_req.type = "events_api"
        mock_req.payload = {
            "event": {
                "type": "app_mention",
                "user": "U456",
                "channel": "C789",
                "ts": "1234567890.123456",
                "text": "<@U123BOT> hello",
                "event_ts": "1234567890.123456"
            }
        }

        # Mock _publish_event_to_guild
        socket_mode_agent._publish_event_to_guild = MagicMock()

        # Handle the request
        socket_mode_agent._handle_socket_mode_request(mock_client, mock_req)

        # Should have sent ACK
        mock_client.send_socket_mode_response.assert_called_once()
        response = mock_client.send_socket_mode_response.call_args[0][0]
        assert response.envelope_id == "env-123"

    def test_handle_app_mention_event(self, socket_mode_agent):
        """Test handling app_mention event"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "app_mention",
            "user": "U456",
            "channel": "C789",
            "ts": "1234567890.123456",
            "text": "<@U123BOT> hello",
            "event_ts": "1234567890.123456"
        }

        socket_mode_agent._handle_app_mention(event, "env-123")

        # Should have published to guild
        socket_mode_agent._publish_event_to_guild.assert_called_once()
        event_msg = socket_mode_agent._publish_event_to_guild.call_args[0][0]

        assert isinstance(event_msg, SlackEventMessage)
        assert event_msg.event_type == "app_mention"
        assert event_msg.user == "U456"
        assert event_msg.channel == "C789"
        assert event_msg.text == "<@U123BOT> hello"
        assert event_msg.workspace_id == "T123"
        assert event_msg.envelope_id == "env-123"

    def test_handle_app_mention_ignores_bot_messages(self, socket_mode_agent):
        """Test that bot's own messages are ignored"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "app_mention",
            "user": "U456",
            "channel": "C789",
            "ts": "1234567890.123456",
            "text": "<@U123BOT> hello",
            "event_ts": "1234567890.123456",
            "bot_id": "B123BOT"  # This is from a bot
        }

        socket_mode_agent._handle_app_mention(event, "env-123")

        # Should not publish bot's own messages
        socket_mode_agent._publish_event_to_guild.assert_not_called()

    def test_handle_message_event_dm(self, socket_mode_agent):
        """Test handling DM message event"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "message",
            "user": "U456",
            "channel": "D123",
            "channel_type": "im",
            "ts": "1234567890.123456",
            "text": "hello",
            "event_ts": "1234567890.123456"
        }

        socket_mode_agent._handle_message(event, "env-123")

        # Should publish DM messages
        socket_mode_agent._publish_event_to_guild.assert_called_once()
        event_msg = socket_mode_agent._publish_event_to_guild.call_args[0][0]
        assert event_msg.event_type == "message"

    def test_handle_message_event_with_bot_mention(self, socket_mode_agent):
        """Test that channel messages with mentions are skipped (handled by app_mention)"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "message",
            "user": "U456",
            "channel": "C789",
            "channel_type": "channel",
            "ts": "1234567890.123456",
            "text": "hey <@U123BOT> how are you?",
            "event_ts": "1234567890.123456"
        }

        socket_mode_agent._handle_message(event, "env-123")

        # Channel messages are skipped - handled by app_mention event instead
        socket_mode_agent._publish_event_to_guild.assert_not_called()

    def test_handle_message_event_ignores_regular_channel_messages(self, socket_mode_agent):
        """Test that regular channel messages (no mention) are ignored"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "message",
            "user": "U456",
            "channel": "C789",
            "channel_type": "channel",
            "ts": "1234567890.123456",
            "text": "just a regular message",
            "event_ts": "1234567890.123456"
        }

        socket_mode_agent._handle_message(event, "env-123")

        # Should not publish regular channel messages
        socket_mode_agent._publish_event_to_guild.assert_not_called()

    def test_handle_message_with_subtype_ignored(self, socket_mode_agent):
        """Test that messages with subtypes are ignored"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "message",
            "subtype": "message_changed",  # Edit event
            "user": "U456",
            "channel": "C789",
            "ts": "1234567890.123456",
            "text": "edited message",
            "event_ts": "1234567890.123456"
        }

        socket_mode_agent._handle_message(event, "env-123")

        # Should ignore edited messages
        socket_mode_agent._publish_event_to_guild.assert_not_called()

    def test_handle_threaded_message(self, socket_mode_agent):
        """Test handling message in a thread"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        event = {
            "type": "app_mention",
            "user": "U456",
            "channel": "C789",
            "ts": "1234567890.999999",
            "text": "<@U123BOT> follow up",
            "thread_ts": "1234567890.000000",  # Parent thread
            "event_ts": "1234567890.999999"
        }

        socket_mode_agent._handle_app_mention(event, "env-123")

        # Should preserve thread_ts
        socket_mode_agent._publish_event_to_guild.assert_called_once()
        event_msg = socket_mode_agent._publish_event_to_guild.call_args[0][0]
        assert event_msg.thread_ts == "1234567890.000000"
        assert event_msg.ts == "1234567890.999999"


class TestPublishEventToGuild:
    """Tests for publishing events to guild"""

    def test_publish_event_to_guild(self, socket_mode_agent):
        """Test publishing event to guild message bus"""
        from rustic_ai.core.messaging.core.message import AgentTag
        from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

        # Mock the required agent internals
        socket_mode_agent._client = MagicMock()
        gemstone = GemstoneGenerator(1)
        socket_mode_agent._id_generator = gemstone
        socket_mode_agent.get_agent_tag = MagicMock(return_value=AgentTag(id="socket", name="Socket"))
        socket_mode_agent.guild_spec = MagicMock()
        socket_mode_agent.guild_spec.routes = None

        event_msg = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="<@U123BOT> hello",
            event_ts="1234567890.123456"
        )

        socket_mode_agent._publish_event_to_guild(event_msg)

        # Should have published message to client
        socket_mode_agent._client.publish.assert_called_once()

    def test_publish_event_handles_errors(self, socket_mode_agent):
        """Test that publish handles errors gracefully"""
        socket_mode_agent._send_dict_to_self = MagicMock(
            side_effect=Exception("Guild error")
        )

        event_msg = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="test",
            event_ts="1234567890.123456"
        )

        # Should not raise exception
        socket_mode_agent._publish_event_to_guild(event_msg)


class TestShutdown:
    """Tests for agent shutdown"""

    @pytest.mark.asyncio
    async def test_on_shutdown_closes_client(self, socket_mode_agent):
        """Test that shutdown closes Socket Mode client"""
        mock_client = MagicMock()
        socket_mode_agent._socket_client = mock_client

        await socket_mode_agent._on_shutdown()

        # Should have closed client
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_shutdown_without_client(self, socket_mode_agent):
        """Test that shutdown works without client"""
        socket_mode_agent._socket_client = None

        # Should not raise exception
        await socket_mode_agent._on_shutdown()

    @pytest.mark.asyncio
    async def test_on_shutdown_handles_errors(self, socket_mode_agent):
        """Test that shutdown handles errors gracefully"""
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("Close error")
        socket_mode_agent._socket_client = mock_client

        # Should not raise exception
        await socket_mode_agent._on_shutdown()


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_handle_malformed_event(self, socket_mode_agent):
        """Test handling malformed event"""
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"
        socket_mode_agent._publish_event_to_guild = MagicMock()

        # Missing required fields
        event = {
            "type": "app_mention",
            "user": "U456"
            # Missing: channel, ts, text, event_ts
        }

        # Should handle gracefully
        socket_mode_agent._handle_app_mention(event, "env-123")

        # Should not have published due to validation error
        socket_mode_agent._publish_event_to_guild.assert_not_called()

    def test_handle_unknown_event_type(self, socket_mode_agent):
        """Test handling unknown event type"""
        from slack_sdk.socket_mode.request import SocketModeRequest

        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"

        mock_client = MagicMock()
        mock_req = MagicMock(spec=SocketModeRequest)
        mock_req.envelope_id = "env-123"
        mock_req.type = "events_api"
        mock_req.payload = {
            "event": {
                "type": "unknown_event_type",
                "some_field": "some_value"
            }
        }

        # Should handle without error
        socket_mode_agent._handle_socket_mode_request(mock_client, mock_req)

        # Should still ACK
        mock_client.send_socket_mode_response.assert_called_once()

    def test_get_connection_status_after_connection(self, socket_mode_agent):
        """Test connection status after successful connection"""
        socket_mode_agent._is_connected = True
        socket_mode_agent._workspace_id = "T123"
        socket_mode_agent._bot_user_id = "U123BOT"

        status = socket_mode_agent.get_connection_status()

        assert status["connected"] is True
        assert status["workspace_id"] == "T123"
        assert status["bot_user_id"] == "U123BOT"
