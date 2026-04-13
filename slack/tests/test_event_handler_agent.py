"""Unit tests for SlackEventHandlerAgent"""

from unittest.mock import MagicMock, patch

import pytest

from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.slack.agents.event_handler_agent import SlackEventHandlerAgent
from rustic_ai.slack.models.events import SlackEventMessage


@pytest.fixture
def event_handler_agent():
    """Create a SlackEventHandlerAgent instance for testing"""
    # Create a minimal instance without full initialization
    # We'll test methods directly without needing full Agent setup
    agent = object.__new__(SlackEventHandlerAgent)
    agent._bot_user_id = None
    # Add required Agent attributes that are normally set during initialization
    agent._agent_tag = MagicMock()
    agent._send_to_self = MagicMock()
    agent.send_error = MagicMock()
    agent.agent_spec = MagicMock()
    agent.agent_spec.name = "TestEventHandler"
    return agent


@pytest.fixture
def sample_event():
    """Create a sample Slack event"""
    return SlackEventMessage(
        event_type="app_mention",
        workspace_id="T123WORKSPACE",
        user="U456USER",
        channel="C789CHANNEL",
        ts="1234567890.123456",
        text="<@U123BOT> hello there",
        event_ts="1234567890.123456"
    )


@pytest.fixture
def gemstone_generator():
    """Create a GemstoneGenerator for message IDs"""
    return GemstoneGenerator(machine_id=1)


class TestEventHandlerAgentBasics:
    """Basic tests for EventHandlerAgent"""

    def test_agent_creation(self, event_handler_agent):
        """Test that agent can be created"""
        assert event_handler_agent is not None
        assert isinstance(event_handler_agent, SlackEventHandlerAgent)
        assert event_handler_agent._bot_user_id is None

    def test_agent_has_processor(self, event_handler_agent):
        """Test that agent has the event processor"""
        assert hasattr(event_handler_agent, 'handle_slack_event')
        assert callable(event_handler_agent.handle_slack_event)


class TestMentionTextCleaning:
    """Tests for mention text cleaning"""

    def test_clean_basic_mention(self, event_handler_agent):
        """Test cleaning a basic @mention"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT> hello there")
        assert clean == "hello there"

    def test_clean_mention_in_middle(self, event_handler_agent):
        """Test cleaning @mention in middle of text"""
        clean = event_handler_agent._clean_mention_text("hey <@U123BOT> what's up")
        assert clean == "hey what's up"

    def test_clean_multiple_mentions(self, event_handler_agent):
        """Test cleaning multiple @mentions"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT> <@U456USER> hello")
        assert clean == "hello"

    def test_clean_no_mentions(self, event_handler_agent):
        """Test text with no mentions"""
        clean = event_handler_agent._clean_mention_text("just a regular message")
        assert clean == "just a regular message"

    def test_clean_only_mention(self, event_handler_agent):
        """Test text with only a mention"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT>")
        assert clean == ""

    def test_clean_mention_with_extra_whitespace(self, event_handler_agent):
        """Test cleaning mentions with extra whitespace"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT>    hello    there   ")
        assert clean == "hello there"

    def test_clean_mention_case_sensitive(self, event_handler_agent):
        """Test that mention cleaning preserves case"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT> Hello World")
        assert clean == "Hello World"

    def test_clean_mention_with_special_chars(self, event_handler_agent):
        """Test cleaning with special characters"""
        clean = event_handler_agent._clean_mention_text("<@U123BOT> :emoji: *bold* _italic_")
        assert clean == ":emoji: *bold* _italic_"

    def test_clean_multiple_bot_ids(self, event_handler_agent):
        """Test cleaning different bot ID formats"""
        # Standard format
        assert event_handler_agent._clean_mention_text("<@U123ABC> hi") == "hi"
        # Longer ID
        assert event_handler_agent._clean_mention_text("<@U123ABC456DEF> hi") == "hi"
        # Multiple different IDs
        clean = event_handler_agent._clean_mention_text("<@U123> <@U456> <@U789> hi")
        assert clean == "hi"


class TestEventHandlerProcessing:
    """Tests for event processing"""

    @pytest.mark.asyncio
    async def test_handle_app_mention(self, event_handler_agent, sample_event):
        """Test handling an app_mention event"""
        # Track sent messages
        sent_messages = []

        def capture_send(payload, **kwargs):
            sent_messages.append(payload)

        # Mock the agent's send method
        event_handler_agent._send_to_self = MagicMock(side_effect=capture_send)

        # Create a mock context that passes through to the agent's send
        mock_context = MagicMock()
        mock_context.payload = sample_event
        mock_context.send = MagicMock(side_effect=capture_send)
        mock_context.update_context = MagicMock()

        # Bypass the processor decorator by calling the handler directly
        with patch.object(event_handler_agent, 'agent_spec') as mock_spec:
            mock_spec.name = "TestEventHandler"
            await event_handler_agent._handle_mention(mock_context, sample_event)

        # Should have sent a ChatCompletionRequest
        assert len(sent_messages) >= 1

        # Find the ChatCompletionRequest
        chat_request = None
        for msg in sent_messages:
            if hasattr(msg, 'messages'):  # ChatCompletionRequest
                chat_request = msg
                break

        assert chat_request is not None
        assert len(chat_request.messages) > 0
        assert chat_request.messages[0].content == "hello there"  # Mention cleaned

        # Verify session context was updated with Slack context
        mock_context.update_context.assert_called_once()
        update_call = mock_context.update_context.call_args[0][0]
        assert "slack_context" in update_call
        assert update_call["slack_context"]["channel"] == "C789CHANNEL"
        assert update_call["slack_context"]["user"] == "U456USER"

    @pytest.mark.asyncio
    async def test_handle_message_event(self, event_handler_agent):
        """Test handling a regular message event"""
        message_event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="D123DM",  # DM channel
            ts="1234567890.123456",
            text="hello bot",
            event_ts="1234567890.123456"
        )

        # Track sent messages
        sent_messages = []

        def capture_send(payload, **kwargs):
            sent_messages.append(payload)

        mock_context = MagicMock()
        mock_context.payload = message_event
        mock_context.send = MagicMock(side_effect=capture_send)
        mock_context.update_context = MagicMock()

        # Call handler directly
        await event_handler_agent._handle_direct_message(mock_context, message_event)

        # Should be handled (forwards to _handle_mention)
        assert len(sent_messages) >= 1

    @pytest.mark.asyncio
    async def test_handle_empty_message_after_cleaning(self, event_handler_agent):
        """Test handling event that becomes empty after cleaning"""
        empty_event = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="<@U123BOT>",  # Only mention, no text
            event_ts="1234567890.123456"
        )

        # Track sent messages
        sent_messages = []

        def capture_send(payload, **kwargs):
            sent_messages.append(payload)

        mock_context = MagicMock()
        mock_context.payload = empty_event
        mock_context.send = MagicMock(side_effect=capture_send)

        # Call handler directly
        await event_handler_agent._handle_mention(mock_context, empty_event)

        # Should send friendly response
        assert len(sent_messages) == 1
        response = sent_messages[0]

        # Should be SlackSendMessageRequest with friendly text
        assert "SlackSendMessageRequest" in str(type(response))
        assert "Hi!" in response.text or "How can I help" in response.text

    @pytest.mark.asyncio
    async def test_handle_threaded_message(self, event_handler_agent):
        """Test handling a message in a thread"""
        threaded_event = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.999999",
            text="<@U123BOT> follow up question",
            thread_ts="1234567890.000000",  # Parent thread
            event_ts="1234567890.999999"
        )

        # Track sent messages
        sent_messages = []

        def capture_send(payload, **kwargs):
            sent_messages.append(payload)

        mock_context = MagicMock()
        mock_context.payload = threaded_event
        mock_context.send = MagicMock(side_effect=capture_send)
        mock_context.update_context = MagicMock()

        # Call handler directly
        await event_handler_agent._handle_mention(mock_context, threaded_event)

        # Verify session context includes thread_ts
        mock_context.update_context.assert_called_once()
        update_call = mock_context.update_context.call_args[0][0]
        assert "slack_context" in update_call
        assert update_call["slack_context"]["thread_ts"] == "1234567890.000000"

    @pytest.mark.asyncio
    async def test_handle_unknown_event_type(self, event_handler_agent):
        """Test handling an unknown event type - should just log and not crash"""
        unknown_event = SlackEventMessage(
            event_type="unknown_type",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="test",
            event_ts="1234567890.123456"
        )

        # This test just verifies the event model accepts unknown types
        # The actual handling logic just logs debug for unknown types
        assert unknown_event.event_type == "unknown_type"

    @pytest.mark.asyncio
    async def test_error_handling(self, event_handler_agent, sample_event):
        """Test error handling when processing fails"""
        # Track send calls
        send_count = [0]
        sent_messages = []

        def mock_send(payload, **kwargs):
            send_count[0] += 1
            if send_count[0] == 1:
                # First send (ChatCompletionRequest) fails
                raise Exception("Test error")
            # Second send (error message) succeeds
            sent_messages.append(payload)

        mock_context = MagicMock()
        mock_context.payload = sample_event
        mock_context.send = MagicMock(side_effect=mock_send)
        mock_context.update_context = MagicMock()

        # Call handler directly - should catch exception
        await event_handler_agent._handle_mention(mock_context, sample_event)

        # Should have sent error response
        assert send_count[0] == 2
        assert len(sent_messages) == 1
        error_msg = sent_messages[0]
        assert "SlackSendMessageRequest" in str(type(error_msg))
        assert "error" in error_msg.text.lower()


class TestSessionStateManagement:
    """Tests for session state management"""

    @pytest.mark.asyncio
    async def test_session_state_includes_slack_context(self, event_handler_agent, sample_event):
        """Test that Slack context is stored in session state"""
        mock_context = MagicMock()
        mock_context.payload = sample_event
        mock_context.send = MagicMock()
        mock_context.update_context = MagicMock()

        # Call handler directly
        await event_handler_agent._handle_mention(mock_context, sample_event)

        # Verify update_context was called with slack_context
        mock_context.update_context.assert_called_once()
        context_update = mock_context.update_context.call_args[0][0]

        assert "slack_context" in context_update
        slack_ctx = context_update["slack_context"]
        assert slack_ctx["channel"] == "C789CHANNEL"
        assert slack_ctx["user"] == "U456USER"
        assert slack_ctx["ts"] == "1234567890.123456"
        assert slack_ctx["workspace_id"] == "T123WORKSPACE"
        assert slack_ctx["event_type"] == "app_mention"
