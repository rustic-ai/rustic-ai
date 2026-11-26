"""Public outcomes and bounds for the Semantic Memory Assistant."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.uniko_agent import DocumentSourceOutcome


class SemanticMemoryAssistantConfig(BaseAgentProps):
    corpus_session_id: str = "corpus:semantic-assistant:references"
    assistant_agent_id: str = "memory_assistant"
    scraper_agent_id: str = "playwright_agent"
    document_coordinator_id: str = "document_coordinator"
    deadline_seconds: float = Field(default=600, gt=0, le=3600)
    commit_timeout_seconds: float = Field(default=15, gt=0, le=60)
    max_active_requests: int = Field(default=32, ge=1, le=128)
    completed_request_limit: int = Field(default=1024, ge=1, le=4096)
    max_source_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_workflow_bytes: int = Field(default=32 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)


class SemanticMemoryAssistantResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    answer: str
    memory_status: Literal["saved", "unconfirmed"]
    warning: str | None = None
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)


class SemanticMemoryAssistantError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    error: str
    message: str
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)
