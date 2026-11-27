"""Typed document coordination contracts, separate from native memory operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rustic_ai.core.guild.dsl import BaseAgentProps

from .models import IngestOutcome, MemorySource, RecallResponse

IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


class DocumentCoordinatorConfig(BaseAgentProps):
    corpus_session_id: str = Field(min_length=1, max_length=256, pattern=IDENTIFIER)
    memory_agent_id: str = Field(min_length=1, max_length=256)
    deadline_seconds: float = Field(default=120, gt=0, le=3600)
    max_source_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_workflow_bytes: int = Field(default=32 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_active_workflows: int = Field(default=32, ge=1, le=128)
    completed_request_limit: int = Field(default=1024, ge=1, le=4096)
    recall_item_limit: int = Field(default=10, ge=1, le=50)
    recall_max_characters: int = Field(default=6000, ge=1, le=32000)
    recall_token_budget: int = Field(default=2000, ge=1, le=10000)


class DocumentWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=256, pattern=IDENTIFIER)
    sources: list[MemorySource] = Field(default_factory=list, max_length=32)
    query: str | None = Field(default=None, min_length=1, max_length=4000)
    allow_partial: bool = False
    require_evidence: bool = True

    @model_validator(mode="after")
    def has_work(self):
        if self.query is not None:
            self.query = self.query.strip()
            if not self.query:
                raise ValueError("Query cannot be blank")
        if not self.sources and self.query is None:
            raise ValueError("Supply sources or a query")
        return self


class DocumentSourceOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, le=31)
    source_id: str | None = None
    revision_id: str | None = None
    record_id: str | None = None
    name: str | None = None
    mime_type: str | None = None
    source_uri: str | None = None
    encoding: str | None = None
    status: Literal["pending", "ingested", "failed", "unknown"] = "pending"
    outcome: IngestOutcome | None = None
    error: str | None = None


class DocumentWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    query: str | None = None
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)
    recall: RecallResponse | None = None
    partial: bool = False


class DocumentWorkflowError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    error: str
    message: str
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)


class DocumentWorkflowDeadline(BaseModel):
    """Internal self-inbox control message; never a public workflow input."""

    request_id: str
    attempt_id: str
