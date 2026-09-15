"""Typed, bounded memory events emitted by the data analyst."""

from hashlib import sha256
import json
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    ChatCompletionResponse,
    TextContentPart,
    UserMessage,
)
from rustic_ai.uniko_agent import (
    FinalizeMemorySessionRequest,
    MemoryRecordKind,
    RecordMemoryRequest,
)


def analysis_memory_identity(agent: Agent, ctx: ProcessContext) -> tuple[str, str, str]:
    """Resolve a stable guild/user session from the original User Proxy request."""
    context = ctx.get_context() or {}
    context_user = context.get("analysis_user")
    context_session = context.get("analysis_session")
    context_request = context.get("analysis_request_id")
    if context_user and context_session and context_request:
        digest = sha256(f"{agent.guild_id}\0{context_user}".encode()).hexdigest()
        return str(context_session), f"user-{digest}", str(context_request)

    forward_header = getattr(ctx.message, "forward_header", None)
    sender = getattr(forward_header, "on_behalf_of", None) or getattr(ctx.message, "sender", None)
    sender_id = getattr(sender, "id", None)
    request_id = getattr(forward_header, "origin_message_id", None) or getattr(ctx.message, "id", None)
    if not sender_id or not str(sender_id).startswith("upa-") or request_id is None:
        raise ValueError("analysis_memory_identity_unavailable")
    digest = sha256(f"{agent.guild_id}\0{sender_id}".encode()).hexdigest()
    return f"analysis-user-{digest}", f"user-{digest}", str(request_id)


def _visible_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, ArrayOfContentParts):
        return "\n".join(
            part.text.strip() for part in content.root if isinstance(part, TextContentPart) and part.text.strip()
        )
    return ""


class DatasetProfile(BaseModel):
    """Deterministic, bounded facts computed from one loaded dataset."""

    model_config = ConfigDict(extra="forbid")

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    column_schema: dict[str, str]
    null_counts: dict[str, int]
    duplicate_rows: int = Field(ge=0)


class DatasetLoadedEvent(BaseModel):
    """A trusted dataset profile emitted only after a successful load."""

    model_config = ConfigDict(extra="forbid")

    dataset_name: str = Field(min_length=1, max_length=200)
    source_name: str = Field(min_length=1, max_length=255)
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile: DatasetProfile
    sample_data: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    record_id: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=1, max_length=300)


class AnalysisOutcomeRecord(BaseModel):
    """A bounded result from a tool that actually executed."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=1, max_length=300)
    tool_name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=6000)


class AnalysisConversationRecorder(LLMCallWrapper):
    """Emit visible successful turns to the guild MemoryAgent asynchronously."""

    max_characters: int = Field(default=16000, ge=256, le=16000)

    def preprocess(self, agent: Agent, ctx: ProcessContext, request: ChatCompletionRequest, llm: LLM):
        return request

    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        del final_prompt, llm
        session_id, user_id, request_id = analysis_memory_identity(agent, ctx)
        users = [_visible_text(message) for message in ctx.payload.messages if isinstance(message, UserMessage)]
        user_text = next((text for text in reversed(users) if text), "")
        if not user_text or len(llm_response.choices) != 1:
            return None
        choice = llm_response.choices[0]
        assistant_text = _visible_text(choice.message)
        if not assistant_text or choice.message.tool_calls:
            return None
        return [
            RecordMemoryRequest(
                record_id=f"{request_id}:user",
                session_id=session_id,
                sender_id=user_id,
                kind=MemoryRecordKind.USER_ASSERTION,
                content=user_text[: self.max_characters],
            ),
            RecordMemoryRequest(
                record_id=f"{request_id}:assistant",
                session_id=session_id,
                sender_id=agent.id,
                kind=MemoryRecordKind.ASSISTANT_RESPONSE,
                content=assistant_text[: self.max_characters],
            ),
            FinalizeMemorySessionRequest(session_id=session_id),
        ]


class AnalysisOutcomeEmitter(ToolCallWrapper):
    """Emit successful, executed tool results as attributed memory records."""

    max_characters: int = Field(default=6000, ge=256, le=6000)

    def preprocess(
        self, agent: Agent, ctx: ProcessContext, tool_name: str, tool_input: BaseModel
    ) -> BaseModel | ToolSkipResult:
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        if tool_name in {"load_file", "ask_user"} or '"_rustic_data_analyst_outcome":true' in tool_output:
            return ToolCallResult(output=tool_output)
        try:
            session_id, _, request_id = analysis_memory_identity(agent, ctx)
        except ValueError:
            return ToolCallResult(output=tool_output)
        args = json.dumps(tool_input.model_dump(mode="json"), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        digest = sha256(f"{tool_name}\0{args}\0{tool_output}".encode()).hexdigest()
        content = f"Executed tool: {tool_name}\nArguments: {args}\nVerified result:\n{tool_output}"[
            : self.max_characters
        ]
        return ToolCallResult(
            output=tool_output,
            messages=[
                AnalysisOutcomeRecord(
                    record_id=f"{request_id}:result:{digest}",
                    session_id=session_id,
                    tool_name=tool_name,
                    content=content,
                )
            ],
        )
