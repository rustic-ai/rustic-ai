"""Typed, bounded memory events emitted by the data analyst."""

from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)


def analysis_memory_identity(agent: Agent, ctx: ProcessContext) -> tuple[str, str, str]:
    """Resolve the explicit request session from the original User Proxy request."""
    context = ctx.get_context() or {}
    context_user = context.get("analysis_user")
    context_session = context.get("analysis_session")
    context_request = context.get("analysis_request_id")
    if context_user and context_session and context_request:
        digest = sha256(f"{agent.guild_id}\0{context_user}".encode()).hexdigest()
        return str(context_session), f"user-{digest}", str(context_request)
    raise ValueError("analysis_memory_identity_unavailable")


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
