from datetime import datetime
import os

from claude_agent_sdk import AssistantMessage as ClaudeAssistantMessage
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, TextBlock
from pydantic import BaseModel

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

    allowed_tools: list[str] = ["Edit", "Read", "Write", "Glob", "Grep", "Skill"]
    permission_mode: str = "acceptEdits"  # or "ask"
    session_id: str = "default"
    setting_sources: list[str] = ["project"]


class AddClaudeAgentRequest(BaseModel):
    name: str
    config: str


class AddClaudeSkillRequest(BaseModel):
    name: str
    skill: str


class ClaudeCodeAgent(Agent[ClaudeCodeAgentProps]):
    """
    Agent validation for Claude Code integration.

    # The SDK will automatically detect subagents in .claude/agents/
    # and skills in .claude/skills/ based on the configuration above (setting_source = 'project').
    # You can now prompt Claude to use them.
    """

    def __init__(self):
        self.options = ClaudeAgentOptions(
            allowed_tools=self.config.allowed_tools,
            permission_mode=self.config.permission_mode,
            setting_sources=self.config.setting_sources,
        )
        self.claude_client = ClaudeSDKClient(options=self.options)
        self._is_connected = False

    async def _ensure_connected(self):
        if not self._is_connected:
            await self.claude_client.connect()
            self._is_connected = True

    async def refresh(self):
        """
        Refreshes the Claude SDK client to pick up new agents and skills.
        """
        if self._is_connected:
            await self.claude_client.disconnect()
            self._is_connected = False

        # Re-initialize the client
        self.claude_client = ClaudeSDKClient(options=self.options)

    @agent.processor(AddClaudeAgentRequest)
    def add_agent(self, ctx: agent.ProcessContext[AddClaudeAgentRequest]):
        """
        Adds a new agent configuration at runtime.

        Args:
            name: The name of the agent (file name without extension).
            config: The content of the agent configuration (Markdown).
        """

        payload = ctx.payload
        agents_dir = "./.claude/agents"
        os.makedirs(agents_dir, exist_ok=True)

        file_path = os.path.join(agents_dir, f"{payload.name}.md")
        with open(file_path, "w") as f:
            f.write(payload.config)

        self.refresh()

    @agent.processor(AddClaudeSkillRequest)
    def add_skill(self, ctx: agent.ProcessContext[AddClaudeSkillRequest]):
        """
        Adds a new skill at runtime.

        Args:
            name: The name of the skill (file name without extension).
            skill: The content of the skill (Markdown).
        """
        payload = ctx.payload
        skills_dir = "./.claude/skills"
        os.makedirs(skills_dir, exist_ok=True)

        file_path = os.path.join(skills_dir, f"{payload.name}.md")
        with open(file_path, "w") as f:
            f.write(payload.skill)

        self.refresh()

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
