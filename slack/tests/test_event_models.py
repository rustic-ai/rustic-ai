"""Unit tests for Slack event models"""

from pydantic import ValidationError
import pytest

from rustic_ai.slack.models.events import (
    SlackAppMentionEvent,
    SlackEventMessage,
    SlackMessageEvent,
    SlackReactionEvent,
)


class TestSlackEventMessage:
    """Tests for SlackEventMessage base model"""

    def test_valid_event_message(self):
        """Test creating a valid event message"""
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
        assert event.channel == "C789CHANNEL"
        assert event.ts == "1234567890.123456"
        assert event.text == "<@U123BOT> hello"
        assert event.event_ts == "1234567890.123456"
        assert event.thread_ts is None
        assert event.bot_id is None
        assert event.edited is None
        assert event.envelope_id is None

    def test_event_message_with_thread(self):
        """Test event message in a thread"""
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="reply in thread",
            thread_ts="1234567890.000000",
            event_ts="1234567890.123456"
        )

        assert event.thread_ts == "1234567890.000000"
        assert event.ts == "1234567890.123456"

    def test_event_message_with_optional_fields(self):
        """Test event message with all optional fields"""
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="test",
            thread_ts="1234567890.000000",
            event_ts="1234567890.123456",
            bot_id="B123BOT",
            edited=True,
            envelope_id="env-123"
        )

        assert event.bot_id == "B123BOT"
        assert event.edited is True
        assert event.envelope_id == "env-123"

    def test_event_message_missing_required_fields(self):
        """Test that missing required fields raise ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            SlackEventMessage(
                event_type="message",
                workspace_id="T123"
                # Missing: user, channel, ts, text, event_ts
            )

        errors = exc_info.value.errors()
        required_fields = {'user', 'channel', 'ts', 'text', 'event_ts'}
        missing_fields = {err['loc'][0] for err in errors}
        assert required_fields.issubset(missing_fields)

    def test_event_message_serialization(self):
        """Test that event message can be serialized and deserialized"""
        original = SlackEventMessage(
            event_type="app_mention",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="hello",
            event_ts="1234567890.123456"
        )

        # Serialize to dict
        data = original.model_dump()
        assert isinstance(data, dict)
        assert data['event_type'] == "app_mention"

        # Deserialize from dict
        restored = SlackEventMessage.model_validate(data)
        assert restored.event_type == original.event_type
        assert restored.user == original.user
        assert restored.channel == original.channel


class TestSlackAppMentionEvent:
    """Tests for SlackAppMentionEvent"""

    def test_app_mention_event_type(self):
        """Test that app mention has correct event type"""
        event = SlackAppMentionEvent(
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="<@U123BOT> hello",
            event_ts="1234567890.123456"
        )

        assert event.event_type == "app_mention"

    def test_app_mention_inheritance(self):
        """Test that app mention inherits from base event"""
        event = SlackAppMentionEvent(
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="<@U123BOT> hello",
            event_ts="1234567890.123456"
        )

        assert isinstance(event, SlackEventMessage)


class TestSlackMessageEvent:
    """Tests for SlackMessageEvent"""

    def test_message_event_default_channel_type(self):
        """Test message event with default channel type"""
        event = SlackMessageEvent(
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="hello",
            event_ts="1234567890.123456"
        )

        assert event.event_type == "message"
        assert event.channel_type == "channel"

    def test_message_event_dm_channel_type(self):
        """Test message event in DM"""
        event = SlackMessageEvent(
            workspace_id="T123",
            user="U456",
            channel="D123DM",
            ts="1234567890.123456",
            text="private message",
            event_ts="1234567890.123456",
            channel_type="im"
        )

        assert event.channel_type == "im"

    def test_message_event_group_channel_type(self):
        """Test message event in group channel"""
        event = SlackMessageEvent(
            workspace_id="T123",
            user="U456",
            channel="G123GROUP",
            ts="1234567890.123456",
            text="group message",
            event_ts="1234567890.123456",
            channel_type="group"
        )

        assert event.channel_type == "group"


class TestSlackReactionEvent:
    """Tests for SlackReactionEvent"""

    def test_valid_reaction_event(self):
        """Test creating a valid reaction event"""
        event = SlackReactionEvent(
            event_type="reaction_added",
            workspace_id="T123",
            user="U456",
            item_user="U789",
            reaction="thumbsup",
            item={
                "type": "message",
                "channel": "C123",
                "ts": "1234567890.123456"
            },
            event_ts="1234567890.123456"
        )

        assert event.event_type == "reaction_added"
        assert event.user == "U456"
        assert event.item_user == "U789"
        assert event.reaction == "thumbsup"
        assert event.item["type"] == "message"
        assert event.item["channel"] == "C123"

    def test_reaction_removed_event(self):
        """Test reaction removed event"""
        event = SlackReactionEvent(
            event_type="reaction_removed",
            workspace_id="T123",
            user="U456",
            item_user="U789",
            reaction="thumbsdown",
            item={"type": "message", "channel": "C123", "ts": "123.456"},
            event_ts="1234567890.123456"
        )

        assert event.event_type == "reaction_removed"
        assert event.reaction == "thumbsdown"

    def test_reaction_event_missing_required_fields(self):
        """Test that missing required fields raise ValidationError"""
        with pytest.raises(ValidationError):
            SlackReactionEvent(
                event_type="reaction_added",
                workspace_id="T123",
                user="U456"
                # Missing: item_user, reaction, item, event_ts
            )


class TestEventModelEdgeCases:
    """Test edge cases and validation"""

    def test_empty_text_allowed(self):
        """Test that empty text is allowed"""
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="",  # Empty text
            event_ts="1234567890.123456"
        )

        assert event.text == ""

    def test_very_long_text(self):
        """Test event with very long text"""
        long_text = "x" * 10000
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text=long_text,
            event_ts="1234567890.123456"
        )

        assert len(event.text) == 10000

    def test_special_characters_in_text(self):
        """Test event with special characters"""
        special_text = "<@U123> :emoji: *bold* _italic_ `code` https://example.com"
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text=special_text,
            event_ts="1234567890.123456"
        )

        assert event.text == special_text

    def test_model_dump_excludes_none(self):
        """Test that model dump excludes None values when configured"""
        event = SlackEventMessage(
            event_type="message",
            workspace_id="T123",
            user="U456",
            channel="C789",
            ts="1234567890.123456",
            text="test",
            event_ts="1234567890.123456"
        )

        data = event.model_dump(exclude_none=True)
        assert "thread_ts" not in data
        assert "bot_id" not in data
        assert "edited" not in data
        assert "envelope_id" not in data

    def test_model_json_schema(self):
        """Test that model generates valid JSON schema"""
        schema = SlackEventMessage.model_json_schema()

        assert "properties" in schema
        assert "required" in schema
        assert "event_type" in schema["properties"]
        assert "workspace_id" in schema["properties"]
        assert "user" in schema["properties"]

        # Check required fields
        required = schema["required"]
        assert "event_type" in required
        assert "workspace_id" in required
        assert "user" in required
        assert "channel" in required
        assert "ts" in required
        assert "text" in required
        assert "event_ts" in required
