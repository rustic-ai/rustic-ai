"""Rustic AI Slack Integration Module.

Provides bidirectional Slack integration for Rustic AI guilds with:
- SlackConnectorAgent: Slack API operations (send, list, create)
- SlackSocketModeAgent: Real-time event listening via WebSocket
- SlackEventHandlerAgent: Process incoming Slack events
- Models for all Slack API operations and events

Setup:
    1. Get bot token from https://api.slack.com/apps
    2. Enable Socket Mode and get app token
    3. Set environment variables:
       export SLACK_BOT_TOKEN="xoxb-..."
       export SLACK_APP_TOKEN="xapp-..."
    4. Load guild: GuildBuilder.from_json_file("slack_guild.json").launch(org_id)

Example:
    >>> from rustic_ai.core.guild.builders import GuildBuilder
    >>> guild = GuildBuilder.from_json_file("slack_guild.json").launch("my_org")
    >>> # Socket Mode connects automatically in background
    >>> # Mention bot in Slack: "@mybot hello"
    >>> # Bot processes and responds
"""

__version__ = "0.0.1"

# Agents
from rustic_ai.slack.agents.connector_agent import SlackConnectorAgent
from rustic_ai.slack.agents.event_handler_agent import SlackEventHandlerAgent
from rustic_ai.slack.agents.socket_mode_agent import SlackSocketModeAgent

# Client
from rustic_ai.slack.client.api_client import SlackAPIClient

# Channel Models
from rustic_ai.slack.models.channels import (
    SlackChannel,
    SlackChannelsResponse,
    SlackCreateChannelRequest,
    SlackInviteToChannelRequest,
    SlackJoinChannelRequest,
    SlackListChannelsRequest,
)

# Event Models (Socket Mode)
from rustic_ai.slack.models.events import (
    SlackAppMentionEvent,
    SlackEventMessage,
    SlackMessageEvent,
    SlackReactionEvent,
)

# File Models
from rustic_ai.slack.models.files import (
    SlackDeleteFileRequest,
    SlackFileUploadResponse,
    SlackGetFileInfoRequest,
    SlackUploadFileRequest,
)

# Message Models
from rustic_ai.slack.models.messages import (
    SlackDeleteMessageRequest,
    SlackGetMessagesRequest,
    SlackGetThreadRepliesRequest,
    SlackMessage,
    SlackMessagesResponse,
    SlackSendMessageRequest,
    SlackSendMessageResponse,
    SlackUpdateMessageRequest,
)

# Reaction Models
from rustic_ai.slack.models.reactions import (
    SlackAddReactionRequest,
    SlackGetReactionsRequest,
    SlackReactionsResponse,
)

# User Models
from rustic_ai.slack.models.users import (
    SlackGetUserInfoRequest,
    SlackListUsersRequest,
    SlackUser,
    SlackUsersResponse,
)

__all__ = [
    "__version__",
    # Agents
    "SlackConnectorAgent",
    "SlackSocketModeAgent",
    "SlackEventHandlerAgent",
    # Client
    "SlackAPIClient",
    # Messages
    "SlackMessage",
    "SlackSendMessageRequest",
    "SlackSendMessageResponse",
    "SlackUpdateMessageRequest",
    "SlackDeleteMessageRequest",
    "SlackGetMessagesRequest",
    "SlackGetThreadRepliesRequest",
    "SlackMessagesResponse",
    # Channels
    "SlackChannel",
    "SlackChannelsResponse",
    "SlackCreateChannelRequest",
    "SlackListChannelsRequest",
    "SlackJoinChannelRequest",
    "SlackInviteToChannelRequest",
    # Events
    "SlackEventMessage",
    "SlackAppMentionEvent",
    "SlackMessageEvent",
    "SlackReactionEvent",
    # Users
    "SlackUser",
    "SlackUsersResponse",
    "SlackGetUserInfoRequest",
    "SlackListUsersRequest",
    # Reactions
    "SlackAddReactionRequest",
    "SlackGetReactionsRequest",
    "SlackReactionsResponse",
    # Files
    "SlackFileUploadResponse",
    "SlackUploadFileRequest",
    "SlackGetFileInfoRequest",
    "SlackDeleteFileRequest",
]
