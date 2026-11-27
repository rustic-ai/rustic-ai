"""Public PaperBanana workflow contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.uniko_agent import DocumentSourceOutcome
from rustic_ai.uniko_agent.document_models import IDENTIFIER


class PaperBananaConfig(BaseAgentProps):
    corpus_session_id: str = Field(
        default="corpus:paperbanana:references", min_length=1, max_length=256, pattern=IDENTIFIER
    )
    document_agent_id: str = "document_coordinator"
    memory_agent_id: str = "memory_agent"
    planner_agent_id: str = "planner_agent"
    stylist_agent_id: str = "stylist_agent"
    visualizer_agent_id: str = "visualizer_agent"
    critic_agent_id: str = "critic_agent"
    deadline_seconds: float = Field(default=600, gt=0, le=3600)
    max_source_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_workflow_bytes: int = Field(default=32 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_active_requests: int = Field(default=32, ge=1, le=128)
    completed_request_limit: int = Field(default=1024, ge=1, le=4096)
    max_refinements: int = Field(default=2, ge=0, le=2)
    recall_item_limit: int = Field(default=3, ge=1, le=50)
    recall_max_characters: int = Field(default=6000, ge=1, le=32000)
    recall_token_budget: int = Field(default=2000, ge=1, le=10000)


class PaperBananaCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["approve", "reject"]
    feedback: str = Field(min_length=1, max_length=4000)


class PaperBananaResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    kind: Literal["upload_summary", "illustration"]
    instruction: str | None = None
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)
    image: MediaLink | None = None
    critique: PaperBananaCritique | None = None

    @model_validator(mode="after")
    def approved_image(self):
        if self.kind == "illustration" and (
            self.image is None or self.critique is None or self.critique.verdict != "approve"
        ):
            raise ValueError("An illustration requires an approved image")
        if self.kind == "upload_summary" and (self.image is not None or self.critique is not None):
            raise ValueError("Upload summaries cannot contain an illustration")
        return self


class PaperBananaError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    error: str
    message: str
    sources: list[DocumentSourceOutcome] = Field(default_factory=list, max_length=32)
