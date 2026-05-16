"""Slack event models for Socket Mode"""

from typing import Optional

from pydantic import BaseModel, Field


class SlackEventMessage(BaseModel):
    """Base model for all Slack events received via Socket Mode"""

    event_type: str = Field(..., description="Type of Slack event (app_mention, message, etc.)")
    workspace_id: str = Field(..., description="Slack workspace/team ID")
    user: str = Field(..., description="User ID who triggered the event")
    channel: str = Field(..., description="Channel ID where event occurred")
    ts: str = Field(..., description="Message timestamp")
    text: str = Field(..., description="Message text content")
    thread_ts: Optional[str] = Field(None, description="Thread timestamp if in thread")
    event_ts: str = Field(..., description="Event timestamp")

    # Metadata
    bot_id: Optional[str] = Field(None, description="Bot ID if message is from a bot")
    edited: Optional[bool] = Field(None, description="Whether message was edited")

    # Original envelope for ACK (internal use)
    envelope_id: Optional[str] = Field(None, description="Socket Mode envelope ID")


class SlackAppMentionEvent(SlackEventMessage):
    """Bot was mentioned with @bot"""

    event_type: str = "app_mention"


class SlackMessageEvent(SlackEventMessage):
    """Regular message in channel or DM"""

    event_type: str = "message"
    channel_type: str = Field(default="channel", description="im, channel, group, mpim")


class SlackReactionEvent(BaseModel):
    """Reaction added or removed"""

    event_type: str = Field(..., description="reaction_added or reaction_removed")
    workspace_id: str = Field(..., description="Slack workspace/team ID")
    user: str = Field(..., description="User who added/removed reaction")
    item_user: str = Field(..., description="User who posted original message")
    reaction: str = Field(..., description="Emoji name without colons (e.g., thumbsup)")
    item: dict = Field(..., description="Item that was reacted to")
    event_ts: str = Field(..., description="Event timestamp")
    envelope_id: Optional[str] = None
