from datetime import datetime

from claude_agent_sdk import AssistantMessage as ClaudeAssistantMessage
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, TextBlock

from rustic_ai.core import Agent
from rustic_ai.core.agents.commons import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    FinishReason,
)
from rustic_ai.core.guild.dsl import BaseAgentProps


class ClaudeCodeAgentProps(BaseAgentProps):
    """Properties for the ClaudeCodeAgent."""

    allowed_tools: list[str] = ["Bash", "Edit", "Read", "Write", "Glob", "Grep"]
    permission_mode: str = "acceptEdits"  # or "ask"
    session_id: str = "default"


class ClaudeCodeAgent(Agent[ClaudeCodeAgentProps]):
    """
    Agent validation for Claude Code integration.
    """

    def __init__(self):
        self.options = ClaudeAgentOptions(
            allowed_tools=self.config.allowed_tools, permission_mode=self.config.permission_mode
        )
        self.claude_client = ClaudeSDKClient(options=self.options)
        self._is_connected = False

    async def _ensure_connected(self):
        if not self._is_connected:
            await self.claude_client.connect()
            self._is_connected = True

    @agent.processor(ChatCompletionRequest)
    async def on_message(self, ctx: agent.ProcessContext[ChatCompletionRequest]):
        """
        Handles incoming messages and forwards them to Claude.
        """
        try:
            await self._ensure_connected()

            # Extract text from message payload
            prompt = ""
            if ctx.payload.messages:
                # Use the last message content as prompt (simplification)
                # Ideally we should construct the full history if supported by SDK in this way
                prompt = ctx.payload.messages[-1].content

            if not prompt:
                ctx.send_error(
                    payload=ErrorMessage(
                        agent_type="ClaudeCodeAgent",
                        error_type="InputError",
                        error_message="No prompt found in request",
                    )
                )
                return

            # Send query to Claude
            await self.claude_client.query(prompt, session_id=self.config.session_id)

            # Stream response back
            response_text = ""
            async for message in self.claude_client.receive_response():
                if isinstance(message, ClaudeAssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text

            # Create ChatCompletionResponse
            response_id = f"chatcmpl-{ctx.message.id}"

            ccr = ChatCompletionResponse(
                id=response_id,
                choices=[
                    Choice(index=0, message=AssistantMessage(content=response_text), finish_reason=FinishReason.stop)
                ],
                model="claude-code",  # or derived from somewhere
                created=int(datetime.now().timestamp()),
            )

            # Send result back
            ctx.send(ccr)

        except Exception as e:
            self.logger.error(f"Error in ClaudeCodeAgent: {e}")
            ctx.send_error(
                payload=ErrorMessage(agent_type="ClaudeCodeAgent", error_type="ProcessingError", error_message=str(e))
            )

    async def shutdown(self):
        """Cleanup connection."""
        if self._is_connected:
            await self.claude_client.disconnect()
            self._is_connected = False
