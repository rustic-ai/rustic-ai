"""Integration tests for Socket Mode functionality"""
import pytest


@pytest.mark.unit
class TestEventModels:
    """Unit tests for event models"""

    def test_slack_event_message_model(self):
        """Test SlackEventMessage model validation"""
        from rustic_ai.slack.models.events import SlackEventMessage

        event = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123WORKSPACE",
            user="U456USER",
            channel="C789CHANNEL",
            ts="1234567890.123456",
            text="<@U123BOT> hello",
            event_ts="1234567890.123456"
        )

        assert event.event_type == "app_mention"
        assert event.workspace_id == "T123WORKSPACE"
        assert event.user == "U456USER"
        assert event.text == "<@U123BOT> hello"

    def test_slack_event_message_with_thread(self):
        """Test SlackEventMessage with thread_ts"""
        from rustic_ai.slack.models.events import SlackEventMessage

        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123WORKSPACE",
            user="U456USER",
            channel="C789CHANNEL",
            ts="1234567890.123456",
            text="reply in thread",
            thread_ts="1234567890.000000",  # Parent message ts
            event_ts="1234567890.123456"
        )

        assert event.thread_ts == "1234567890.000000"
        assert event.ts == "1234567890.123456"


@pytest.mark.unit
class TestEventHandlerAgent:
    """Unit tests for event handler logic"""

    def test_clean_mention_text(self):
        """Test @mention cleaning"""
        from rustic_ai.slack.agents.event_handler_agent import SlackEventHandlerAgent

        agent = SlackEventHandlerAgent()

        # Test basic mention removal
        clean = agent._clean_mention_text("<@U123BOT> hello there")
        assert clean == "hello there"

        # Test mention in middle
        clean = agent._clean_mention_text("hey <@U123BOT> what's up")
        assert clean == "hey what's up"

        # Test multiple mentions
        clean = agent._clean_mention_text("<@U123BOT> <@U456USER> hello")
        assert clean == "hello"

        # Test no mentions
        clean = agent._clean_mention_text("just a regular message")
        assert clean == "just a regular message"
