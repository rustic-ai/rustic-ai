"""Processes incoming Slack events and routes them appropriately"""

import logging
import re
from typing import Optional

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    UserMessage,
)
from rustic_ai.slack.models.events import SlackEventMessage
from rustic_ai.slack.models.messages import SlackSendMessageRequest


class SlackEventHandlerAgent(Agent):
    """
    Processes incoming Slack events from Socket Mode.

    Subscribes to SLACK_INBOUND topic and:
    - Cleans up @mentions
    - Routes to appropriate handlers (LLM, custom processors)
    - Maintains context (channel, thread) for responses
    - Handles errors gracefully

    This agent acts as a bridge between raw Slack events and the guild's
    processing pipeline, ensuring proper context is maintained for responses.
    """

    def __init__(self):
        self._bot_user_id: Optional[str] = None

    @processor(clz=SlackEventMessage)
    async def handle_slack_event(self, ctx: ProcessContext[SlackEventMessage]):
        """Main event handler - routes events to specific processors"""
        event = ctx.payload

        logging.info(
            f"Processing Slack event: type={event.event_type} "
            f"channel={event.channel} user={event.user}"
        )

        ctx.send(payload=ctx.payload)  # Echo the event to the guild so route can use it

        # Route based on event type
        if event.event_type == "app_mention":
            await self._handle_mention(ctx, event)
        elif event.event_type == "message":
            await self._handle_direct_message(ctx, event)
        else:
            logging.debug(f"Unhandled event type: {event.event_type}")

    async def _handle_mention(self, ctx: ProcessContext, event: SlackEventMessage):
        """Handle @bot mentions - forward to LLM for processing"""
        try:
            # Clean up the text (remove @bot mention)
            clean_text = self._clean_mention_text(event.text)

            if not clean_text:
                # Empty message after cleanup - send friendly response
                ctx.send(
                    SlackSendMessageRequest(
                        workspace_id=event.workspace_id,
                        channel=event.channel,
                        text="Hi! How can I help you?",
                        thread_ts=event.thread_ts or event.ts,
                    )
                )
                return

            # Store Slack context in session state for downstream agents
            # This MUST be done before sending so it propagates to child messages
            slack_context = {
                "channel": event.channel,
                "user": event.user,
                "ts": event.ts,
                "thread_ts": event.thread_ts or event.ts,
                "workspace_id": event.workspace_id,
                "event_type": event.event_type,
            }

            ctx.update_context({"slack_context": slack_context})

            # Forward to LLM agent with Slack context in BOTH metadata AND ensure session_state propagates
            ctx.send(
                ChatCompletionRequest(
                    messages=[UserMessage(content=clean_text)],
                    metadata={
                        "slack_channel": event.channel,
                        "slack_user": event.user,
                        "slack_ts": event.ts,
                        "slack_thread_ts": event.thread_ts or event.ts,
                        "workspace_id": event.workspace_id,
                        "event_type": event.event_type,
                    }
                )
            )

            logging.info(f"✅ Forwarded mention to LLM: '{clean_text}'")

        except Exception as e:
            logging.error(f"Error handling mention: {e}", exc_info=True)
            # Send error message back to Slack
            ctx.send(
                SlackSendMessageRequest(
                    workspace_id=event.workspace_id,
                    channel=event.channel,
                    text=f"Sorry, I encountered an error: {str(e)}",
                    thread_ts=event.thread_ts or event.ts,
                )
            )

    async def _handle_direct_message(self, ctx: ProcessContext, event: SlackEventMessage):
        """Handle direct messages (DMs)"""
        # DMs work similarly to mentions but in private context
        await self._handle_mention(ctx, event)

    def _clean_mention_text(self, text: str) -> str:
        """
        Remove @bot mentions from text.

        Example:
            Input: "<@U123BOT> hello there"
            Output: "hello there"

            Input: "hey <@U123BOT> what's up"
            Output: "hey what's up"
        """
        # Remove all @mentions (format: <@U123ABC>)
        clean = re.sub(r'<@[A-Z0-9]+>', '', text)

        # Remove extra whitespace
        clean = ' '.join(clean.split())

        return clean.strip()
