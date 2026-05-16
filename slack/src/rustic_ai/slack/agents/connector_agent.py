"""Main Slack connector agent for all Slack API operations."""

import logging

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.slack.client.api_client import SlackAPIClient
from rustic_ai.slack.models.channels import (
    SlackChannelsResponse,
    SlackCreateChannelRequest,
    SlackInviteToChannelRequest,
    SlackJoinChannelRequest,
    SlackListChannelsRequest,
)
from rustic_ai.slack.models.files import (
    SlackDeleteFileRequest,
    SlackFileUploadResponse,
    SlackGetFileInfoRequest,
    SlackUploadFileRequest,
)
from rustic_ai.slack.models.messages import (
    SlackDeleteMessageRequest,
    SlackGetMessagesRequest,
    SlackGetThreadRepliesRequest,
    SlackMessagesResponse,
    SlackSendMessageRequest,
    SlackSendMessageResponse,
    SlackUpdateMessageRequest,
)
from rustic_ai.slack.models.reactions import (
    SlackAddReactionRequest,
    SlackGetReactionsRequest,
    SlackReactionsResponse,
)
from rustic_ai.slack.models.users import (
    SlackGetUserInfoRequest,
    SlackListUsersRequest,
    SlackUsersResponse,
)


class SlackConnectorAgent(Agent):
    """
    Main Slack connector agent for bidirectional Slack communication.

    Handles:
    - Sending/updating/deleting messages
    - Channel management (list, create, join, invite)
    - File operations (upload, info, delete)
    - User information retrieval
    - Reactions
    """

    def __init__(self):
        self._clients: dict[str, SlackAPIClient] = {}  # workspace_id -> client
        self._token: str | None = None

    async def _get_client(self, workspace_id: str) -> SlackAPIClient:
        """Get or create API client for workspace."""
        if workspace_id in self._clients:
            return self._clients[workspace_id]

        # Get token from environment variable
        if not self._token:
            import os
            self._token = os.getenv("SLACK_BOT_TOKEN")

            if not self._token:
                logging.error("SLACK_BOT_TOKEN environment variable not found")
                raise ValueError(
                    "No Slack bot token found. Please set the SLACK_BOT_TOKEN environment variable."
                )

        logging.info(f"Creating Slack API client for workspace: {workspace_id}")

        # Create API client
        client = SlackAPIClient(
            token=self._token,
            rate_limit_buffer=0.9,
            max_retries=3,
            enable_caching=True,
            cache_ttl=300,
        )

        self._clients[workspace_id] = client
        return client

    # Message Operations

    @processor(clz=SlackSendMessageRequest)
    async def send_message(self, ctx: ProcessContext[SlackSendMessageRequest]):
        """Send a message to a Slack channel."""
        try:
            request = ctx.payload

            logging.info(f"📨 Connector received send_message request: channel={request.channel}, "
                         f"workspace={request.workspace_id}, thread={request.thread_ts}, text_preview={request.text[:50]}...")

            # Check if this is a response to a Slack event
            # Use metadata from session state to determine thread/channel context
            slack_context = ctx.message.session_state.get("slack_context", {})

            # Override channel/thread from context if not explicitly set
            if slack_context.get("channel") and not request.channel:
                request.channel = slack_context["channel"]

            if slack_context.get("thread_ts") and not request.thread_ts:
                request.thread_ts = slack_context["thread_ts"]

            if slack_context.get("workspace_id") and not request.workspace_id:
                request.workspace_id = slack_context["workspace_id"]

            client = await self._get_client(request.workspace_id)

            response = await client.send_message(
                channel=request.channel,
                text=request.text,
                thread_ts=request.thread_ts,
                blocks=request.blocks,
                reply_broadcast=request.reply_broadcast,
                username=request.username,
                icon_url=request.icon_url,
                icon_emoji=request.icon_emoji,
            )

            # Add channel to message object since Slack API doesn't include it
            message_data = response["message"].copy()
            message_data["channel"] = response["channel"]

            ctx.send(
                SlackSendMessageResponse(
                    channel=response["channel"],
                    ts=response["ts"],
                    message=message_data,
                )
            )

        except ValueError as e:
            # Configuration error (e.g., missing token)
            logging.error(f"Configuration error sending message: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_CONFIGURATION_ERROR",
                    error_message=f"Configuration error: {str(e)}",
                )
            )
        except Exception as e:
            logging.error(f"Error sending message: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_SEND_ERROR",
                    error_message=f"Failed to send message: {str(e)}",
                )
            )

    @processor(clz=SlackUpdateMessageRequest)
    async def update_message(self, ctx: ProcessContext[SlackUpdateMessageRequest]):
        """Update an existing message."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.update_message(
                channel=request.channel,
                ts=request.ts,
                text=request.text,
                blocks=request.blocks,
            )

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error updating message: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_UPDATE_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackDeleteMessageRequest)
    async def delete_message(self, ctx: ProcessContext[SlackDeleteMessageRequest]):
        """Delete a message."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.delete_message(
                channel=request.channel,
                ts=request.ts,
            )

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error deleting message: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_DELETE_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackGetMessagesRequest)
    async def get_messages(self, ctx: ProcessContext[SlackGetMessagesRequest]):
        """Fetch message history from a channel."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.get_conversation_history(
                channel=request.channel,
                limit=request.limit,
                cursor=request.cursor,
                oldest=request.oldest,
                newest=request.newest,
                inclusive=request.inclusive,
            )

            ctx.send(
                SlackMessagesResponse(
                    channel=request.channel,
                    messages=response["messages"],
                    has_more=response.get("has_more", False),
                    next_cursor=response.get("response_metadata", {}).get("next_cursor"),
                )
            )

        except Exception as e:
            logging.error(f"Error fetching messages: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_FETCH_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackGetThreadRepliesRequest)
    async def get_thread_replies(self, ctx: ProcessContext[SlackGetThreadRepliesRequest]):
        """Fetch replies in a thread."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.get_thread_replies(
                channel=request.channel,
                thread_ts=request.thread_ts,
                cursor=request.cursor,
                limit=request.limit,
            )

            ctx.send(
                SlackMessagesResponse(
                    channel=request.channel,
                    messages=response["messages"],
                    has_more=response.get("has_more", False),
                    next_cursor=response.get("response_metadata", {}).get("next_cursor"),
                )
            )

        except Exception as e:
            logging.error(f"Error fetching thread: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_THREAD_ERROR",
                    error_message=str(e),
                )
            )

    # Channel Operations

    @processor(clz=SlackListChannelsRequest)
    async def list_channels(self, ctx: ProcessContext[SlackListChannelsRequest]):
        """List all channels."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.list_conversations(
                types=request.types,
                exclude_archived=request.exclude_archived,
                limit=request.limit,
                cursor=request.cursor,
            )

            ctx.send(
                SlackChannelsResponse(
                    channels=response["channels"],
                    has_more=response.get("has_more", False),
                    next_cursor=response.get("response_metadata", {}).get("next_cursor"),
                )
            )

        except ValueError as e:
            # Configuration error (e.g., missing token)
            logging.error(f"Configuration error listing channels: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_CONFIGURATION_ERROR",
                    error_message=f"Configuration error: {str(e)}",
                )
            )
        except Exception as e:
            logging.error(f"Error listing channels: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_LIST_ERROR",
                    error_message=f"Failed to list channels: {str(e)}",
                )
            )

    @processor(clz=SlackCreateChannelRequest)
    async def create_channel(self, ctx: ProcessContext[SlackCreateChannelRequest]):
        """Create a new channel."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.create_channel(name=request.name, is_private=request.is_private)

            ctx.send({"success": True, "channel": response["channel"]})

        except Exception as e:
            logging.error(f"Error creating channel: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_CREATE_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackJoinChannelRequest)
    async def join_channel(self, ctx: ProcessContext[SlackJoinChannelRequest]):
        """Join a channel."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.join_channel(channel=request.channel)

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error joining channel: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_JOIN_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackInviteToChannelRequest)
    async def invite_to_channel(self, ctx: ProcessContext[SlackInviteToChannelRequest]):
        """Invite users to a channel."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.invite_to_channel(channel=request.channel, users=request.users)

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error inviting to channel: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_INVITE_ERROR",
                    error_message=str(e),
                )
            )

    # User Operations

    @processor(clz=SlackListUsersRequest)
    async def list_users(self, ctx: ProcessContext[SlackListUsersRequest]):
        """List all users in workspace."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.list_users(limit=request.limit, cursor=request.cursor)

            ctx.send(
                SlackUsersResponse(
                    users=response["members"],
                    has_more=response.get("has_more", False),
                    next_cursor=response.get("response_metadata", {}).get("next_cursor"),
                )
            )

        except Exception as e:
            logging.error(f"Error listing users: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_USERS_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackGetUserInfoRequest)
    async def get_user_info(self, ctx: ProcessContext[SlackGetUserInfoRequest]):
        """Get information about a user."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.get_user_info(user_id=request.user_id)

            ctx.send({"success": True, "user": response["user"]})

        except Exception as e:
            logging.error(f"Error getting user info: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_USER_INFO_ERROR",
                    error_message=str(e),
                )
            )

    # Reaction Operations

    @processor(clz=SlackAddReactionRequest)
    async def add_reaction(self, ctx: ProcessContext[SlackAddReactionRequest]):
        """Add a reaction to a message."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.add_reaction(channel=request.channel, timestamp=request.timestamp, name=request.name)

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error adding reaction: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_REACTION_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackGetReactionsRequest)
    async def get_reactions(self, ctx: ProcessContext[SlackGetReactionsRequest]):
        """Get reactions for a message."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.get_reactions(channel=request.channel, timestamp=request.timestamp)

            ctx.send(
                SlackReactionsResponse(
                    channel=request.channel,
                    timestamp=request.timestamp,
                    reactions=response.get("message", {}).get("reactions", []),
                )
            )

        except Exception as e:
            logging.error(f"Error getting reactions: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_REACTION_ERROR",
                    error_message=str(e),
                )
            )

    # File Operations

    @processor(clz=SlackUploadFileRequest)
    async def upload_file(self, ctx: ProcessContext[SlackUploadFileRequest]):
        """Upload a file to Slack."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.upload_file(
                channels=request.channels, content=request.content, filename=request.filename, title=request.title
            )

            ctx.send(SlackFileUploadResponse(file=response["file"]))

        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_FILE_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackGetFileInfoRequest)
    async def get_file_info(self, ctx: ProcessContext[SlackGetFileInfoRequest]):
        """Get information about a file."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            response = await client.get_file_info(file_id=request.file_id)

            ctx.send({"success": True, "file": response["file"]})

        except Exception as e:
            logging.error(f"Error getting file info: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_FILE_ERROR",
                    error_message=str(e),
                )
            )

    @processor(clz=SlackDeleteFileRequest)
    async def delete_file(self, ctx: ProcessContext[SlackDeleteFileRequest]):
        """Delete a file."""
        try:
            request = ctx.payload
            client = await self._get_client(request.workspace_id)

            await client.delete_file(file_id=request.file_id)

            ctx.send({"success": True})

        except Exception as e:
            logging.error(f"Error deleting file: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SLACK_FILE_ERROR",
                    error_message=str(e),
                )
            )
