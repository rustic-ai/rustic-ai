"""Slack Socket Mode listener agent - receives events from Slack via WebSocket"""

import logging
import os
import threading
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.messaging import Message, Priority
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.slack.models.events import SlackEventMessage


class SlackSocketModeAgent(Agent):
    """
    Listens for Slack events via Socket Mode (WebSocket connection).

    This agent:
    - Connects to Slack via WebSocket (no public endpoint needed)
    - Receives events (app_mention, message, reaction, etc.)
    - Publishes events to guild message bus on SLACK_INBOUND topic
    - Other agents can subscribe and respond

    Required Environment Variables:
    - SLACK_APP_TOKEN: App-level token (starts with xapp-)
    - SLACK_BOT_TOKEN: Bot token (starts with xoxb-)

    Socket Mode vs HTTP Webhooks:
    - No public endpoint needed
    - Works behind firewalls
    - Real-time bidirectional communication
    - Simpler development setup
    """

    def __init__(self):
        self._socket_client: Optional[SocketModeClient] = None
        self._socket_thread: Optional[threading.Thread] = None
        self._app_token: Optional[str] = None
        self._bot_token: Optional[str] = None
        self._workspace_id: Optional[str] = None
        self._bot_user_id: Optional[str] = None
        self._is_connected: bool = False

        logging.info("SlackSocketModeAgent ready, starting Socket Mode listener...")

        # Get tokens from environment
        self._app_token = os.getenv("SLACK_APP_TOKEN")
        self._bot_token = os.getenv("SLACK_BOT_TOKEN")

        if not self._app_token:
            logging.error(
                "SLACK_APP_TOKEN not found - Socket Mode requires app-level token (xapp-...)\n"
                "Get it from: https://api.slack.com/apps → Your App → Socket Mode"
            )
            return

        if not self._bot_token:
            logging.error("SLACK_BOT_TOKEN not found")
            return

        # Start Socket Mode in background thread
        self._start_socket_mode()

    def _start_socket_mode(self):
        """Initialize and start Socket Mode client in background thread"""
        try:
            # Create Socket Mode client
            self._socket_client = SocketModeClient(
                app_token=self._app_token,
                web_client=WebClient(token=self._bot_token)
            )

            # Register event handlers
            self._socket_client.socket_mode_request_listeners.append(
                self._handle_socket_mode_request  # type: ignore[arg-type]
            )

            # Start in background thread
            self._socket_thread = threading.Thread(
                target=self._run_socket_mode,
                daemon=True,
                name="slack-socket-mode"
            )
            self._socket_thread.start()

            logging.info("Socket Mode client started successfully")

        except Exception as e:
            logging.error(f"Failed to start Socket Mode: {e}", exc_info=True)

    def _run_socket_mode(self):
        """Run Socket Mode client (blocking) - runs in background thread"""
        try:

            # Get bot info before connecting
            web_client = WebClient(token=self._bot_token)
            auth_response = web_client.auth_test()
            self._workspace_id = auth_response["team_id"]
            self._bot_user_id = auth_response["user_id"]

            # Connect to Socket Mode (blocking call)
            self._socket_client.connect()
            self._is_connected = True
            logging.info("Socket Mode connected and listening for events!")

        except Exception as e:
            logging.error(f"Socket Mode connection failed: {e}", exc_info=True)
            self._is_connected = False

    def _handle_socket_mode_request(self, client: SocketModeClient, req: SocketModeRequest):
        """
        Handle incoming Socket Mode requests from Slack.
        This runs in the Socket Mode thread.
        """
        try:
            logging.info(f"🔔 Received Socket Mode request: type={req.type}, envelope_id={req.envelope_id}")

            # Acknowledge the request immediately (Slack expects ACK within 3 seconds)
            response = SocketModeResponse(envelope_id=req.envelope_id)
            client.send_socket_mode_response(response)

            # Process the event
            if req.type == "events_api":
                event = req.payload.get("event", {})
                event_type = event.get("type")

                # Route to appropriate handler
                if event_type == "app_mention":
                    self._handle_app_mention(event, req.envelope_id)
                elif event_type == "message":
                    self._handle_message(event, req.envelope_id)
                elif event_type in ["reaction_added", "reaction_removed"]:
                    self._handle_reaction(event, req.envelope_id)
                else:
                    logging.info(f"⚠️  Unhandled event type: {event_type}")
            else:
                logging.info(f"⚠️  Non-events_api request type: {req.type}")

        except Exception as e:
            logging.error(f"❌ Error handling Socket Mode request: {e}", exc_info=True)

    def _handle_app_mention(self, event: dict, envelope_id: str):
        """Handle @bot mentions"""
        try:

            # Skip bot's own messages
            if event.get("bot_id"):
                logging.info(f"⏭️  Skipping bot's own message (bot_id={event.get('bot_id')})")
                return

            # Create event message
            event_msg = SlackEventMessage(
                event_type="app_mention",
                workspace_id=self._workspace_id,
                user=event["user"],
                channel=event["channel"],
                ts=event["ts"],
                text=event["text"],
                thread_ts=event.get("thread_ts"),
                event_ts=event["event_ts"],
                envelope_id=envelope_id
            )

            logging.info(f"✉️  Created SlackEventMessage for app_mention: {event_msg}")

            # Publish to guild message bus
            self._publish_event_to_guild(event_msg)

        except Exception as e:
            logging.error(f"❌ Error handling app_mention: {e}", exc_info=True)

    def _handle_message(self, event: dict, envelope_id: str):
        """Handle regular messages in channels bot is in (DMs only - mentions are handled by app_mention)"""
        try:
            logging.info(f"💬 Processing message: user={event.get('user')}, channel={event.get('channel')}, "
                         f"bot_id={event.get('bot_id')}, subtype={event.get('subtype')}, "
                         f"channel_type={event.get('channel_type')}")

            # Skip if:
            # - Bot's own message
            # - Message has subtype (edits, deletes, etc.)
            if event.get("bot_id"):
                logging.info(f"⏭️  Skipping bot message (bot_id={event.get('bot_id')})")
                return

            if event.get("subtype"):
                logging.info(f"⏭️  Skipping message with subtype: {event.get('subtype')}")
                return

            # Only process DMs (channel_type == "im")
            # Channel mentions are already handled by app_mention event
            text = event.get("text", "")
            channel_type = event.get("channel_type", "channel")

            logging.info(f"📝 Message text: '{text}', channel_type: {channel_type}")

            if channel_type == "im":
                logging.info("✅ Message qualifies for processing (DM)")

                event_msg = SlackEventMessage(
                    event_type="message",
                    workspace_id=self._workspace_id,
                    user=event["user"],
                    channel=event["channel"],
                    ts=event["ts"],
                    text=text,
                    thread_ts=event.get("thread_ts"),
                    event_ts=event["event_ts"],
                    envelope_id=envelope_id
                )

                self._publish_event_to_guild(event_msg)
            else:
                logging.info("⏭️  Skipping channel message (not a DM, already handled by app_mention if bot was mentioned)")

        except Exception as e:
            logging.error(f"❌ Error handling message: {e}", exc_info=True)

    def _handle_reaction(self, event: dict, envelope_id: str):
        """Handle reaction added/removed"""
        # TODO: Implement reaction handling if needed
        logging.debug(f"Reaction event: {event.get('reaction')} by {event.get('user')}")

    def _publish_event_to_guild(self, event_msg: SlackEventMessage):
        """
        Publish Slack event to guild message bus.
        This runs in Socket Mode thread, so use thread-safe method.
        """
        try:
            # Create a Message and publish directly to SLACK_INBOUND topic
            # This is thread-safe as the messaging client handles synchronization
            msg_id = self._generate_id(Priority.NORMAL)
            topics = ["SLACK_INBOUND"]

            msg = Message(
                id_obj=msg_id,
                topics=topics,
                sender=self.get_agent_tag(),
                payload=event_msg.model_dump(),
                format=get_qualified_class_name(SlackEventMessage),
                message_history=[],
                routing_slip=self.guild_spec.routes,
            )

            self._client.publish(msg)

            logging.info(
                f"📤 Published {event_msg.event_type} event to SLACK_INBOUND topic: "
                f"user={event_msg.user} channel={event_msg.channel}"
            )

        except Exception as e:
            logging.error(f"❌ Error publishing event to guild: {e}", exc_info=True)

    async def _on_shutdown(self):
        """Cleanup when agent shuts down"""
        if self._socket_client:
            logging.info("Disconnecting Socket Mode client...")
            try:
                self._socket_client.close()
                self._is_connected = False
            except Exception as e:
                logging.error(f"Error closing Socket Mode: {e}")

    def get_connection_status(self) -> dict:
        """Get current connection status (useful for health checks)"""
        return {
            "connected": self._is_connected,
            "workspace_id": self._workspace_id,
            "bot_user_id": self._bot_user_id,
        }
