"""Typed G2 requests for supported native structured-memory operations."""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .models import (
    MemoryCommand,
    MemoryCommandResult,
    MemoryScope,
    ObserveResult,
    ObserveTurnRequest,
    ToolCallOutcome,
    ToolCallSpec,
)


class RecordToolCallRequest(ToolCallSpec, MemoryCommand):
    session_id: str = Field(min_length=1, max_length=256)


class ToolCallResponse(MemoryCommandResult):
    outcome: ToolCallOutcome


class RecordActionRequest(MemoryCommand):
    action_type: str = Field(min_length=1, max_length=256)
    action_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    input: Optional[JsonValue] = None
    output: Optional[JsonValue] = None
    status: Optional[str] = Field(default=None, max_length=256)
    error: Optional[str] = Field(default=None, max_length=16000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    triggered_by_message_id: Optional[str] = Field(default=None, max_length=256)
    session_id: Optional[str] = Field(default=None, max_length=256)
    previous_action_id: Optional[str] = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def ordered_time(self):
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            raise ValueError("Action end precedes start")
        return self


class ActionResponse(MemoryCommandResult):
    action_id: str
    action_node: int
    overflow_artifact: Optional[int] = None


class RecordEpisodeRequest(MemoryCommand):
    action_type: str = Field(min_length=1, max_length=256)
    episode_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    outcome: Optional[str] = Field(default=None, max_length=16000)
    state: Optional[JsonValue] = None
    delta: Optional[JsonValue] = None
    importance: Optional[float] = Field(default=None, ge=0, le=1)
    timestamp: Optional[datetime] = None
    triggered_by_message_id: Optional[str] = Field(default=None, max_length=256)
    involved_action_ids: List[str] = Field(default_factory=list, max_length=128)


class EpisodeResponse(MemoryCommandResult):
    episode_id: str
    node_id: int


class AddObservationRequest(MemoryCommand):
    message_id: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=16000)
    subject: str = Field(min_length=1, max_length=256)
    predicate: Optional[str] = Field(default=None, max_length=256)
    object: Optional[str] = Field(default=None, max_length=16000)
    temporal_phrase: Optional[str] = Field(default=None, max_length=256)
    temporal_anchor: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    visibility: Optional[str] = Field(default=None, max_length=256)
    scope: MemoryScope


class ObservationResponse(MemoryCommandResult):
    observation_id: str
    node_id: int


class AssertFactRequest(MemoryCommand):
    subject: str = Field(min_length=1, max_length=256)
    predicate: str = Field(min_length=1, max_length=256)
    object: Optional[str] = Field(default=None, max_length=16000)
    observed_at: Optional[datetime] = None
    supporting_observation_ids: List[str] = Field(default_factory=list, max_length=128)
    visibility: Optional[str] = Field(default=None, max_length=256)
    scope: MemoryScope


class FactResponse(MemoryCommandResult):
    fact_id: str
    node_id: int
    was_created: bool
    observation_count: int


class InvalidateFactRequest(MemoryCommand):
    fact_id: str = Field(min_length=1, max_length=256)
    replacement_fact_id: Optional[str] = Field(default=None, max_length=256)
    reason: Optional[str] = Field(default=None, max_length=16000)
    scope: MemoryScope


class FactInvalidationResponse(MemoryCommandResult):
    fact_id: str
    invalidated: bool


class ConsolidateMemoryRequest(MemoryCommand):
    pass


class ConsolidationResponse(MemoryCommandResult):
    cycle: Dict[str, JsonValue]
    procedures: Dict[str, JsonValue]
    topics: Dict[str, JsonValue]


class CommitMemoryUnitRequest(MemoryCommand):
    unit_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    turns: List[ObserveTurnRequest] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def one_session(self):
        if any(t.session_id not in (None, self.session_id) for t in self.turns):
            raise ValueError("Atomic unit turns must share the unit session")
        if sum(len(t.attachments or []) for t in self.turns) > 32:
            raise ValueError("Atomic unit exceeds 32 attachments")
        return self


class MemoryUnitResponse(MemoryCommandResult):
    unit_id: str
    session_id: str
    committed: bool
    turns: List[ObserveResult]


class MatchProceduresRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Dict[str, str] = Field(max_length=128)
    limit: int = Field(default=20, ge=1, le=100)


class ProcedureMatch(BaseModel):
    procedure_id: str
    name: str
    effectiveness: float


class ProceduresResponse(BaseModel):
    procedures: List[ProcedureMatch]
    truncated: bool = False
    scope: Literal["private_store"] = "private_store"


class RecordProcedureUseRequest(MemoryCommand):
    procedure_id: str = Field(min_length=1, max_length=256)
    succeeded: bool


class ProcedureUseResponse(MemoryCommandResult):
    procedure_id: str
    recorded: bool


class ListMemoryRulesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=100)
    max_characters: int = Field(default=6000, ge=1, le=32000)


class ExplainMemoryRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=256)
    max_characters: int = Field(default=6000, ge=1, le=32000)


class MemoryRuleView(BaseModel):
    name: str
    source_type: str
    status: str
    confidence: float
    source: Optional[str] = None
    natural_language: Optional[str] = None


class MemoryRulesResponse(BaseModel):
    rules: List[MemoryRuleView]
    truncated: bool = False


class ReadExperienceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["action", "episode", "observation", "fact", "goal", "task"]
    record_id: str = Field(min_length=1, max_length=256)
    owner_id: Optional[str] = Field(default=None, max_length=256)
    scope: MemoryScope
    max_characters: int = Field(default=6000, ge=1, le=32000)


class ExperienceResponse(BaseModel):
    available: bool
    kind: str
    record_id: str
    attributes: Dict[str, JsonValue] = Field(default_factory=dict)
    truncated: bool = False


class MemoryOperationStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(min_length=1, max_length=256)
    operation_id: str = Field(min_length=1, max_length=256)


class MemoryOperationStatus(BaseModel):
    operation: str
    operation_id: str
    actor_id: str
    state: Literal["not_found", "completed", "outcome_unknown"]
