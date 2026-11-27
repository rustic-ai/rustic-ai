"""Payload models for MemoryAgent requests and responses."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    model_validator,
)

from rustic_ai.core.agents.commons.media import MediaLink


class MemoryRecordKind(StrEnum):
    """Application-level provenance assigned before content enters memory."""

    UNKNOWN = "unknown"
    USER_ASSERTION = "user_assertion"
    EXTERNAL_EVIDENCE = "external_evidence"
    DETERMINISTIC_OBSERVATION = "deterministic_observation"
    MODEL_INTERPRETATION = "model_interpretation"
    EXECUTED_RESULT = "executed_result"
    ASSISTANT_RESPONSE = "assistant_response"
    CONVERSATION_TURN = "conversation_turn"


class MemoryViewer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str = Field(min_length=1, max_length=256)
    teams: List[str] = Field(default_factory=list, max_length=32)
    orgs: List[str] = Field(default_factory=list, max_length=32)


class MemoryProvenance(BaseModel):
    """Native metadata; record kind remains assigned by the trusted producer."""

    model_config = ConfigDict(extra="forbid")

    category: Optional[str] = Field(default=None, min_length=1, max_length=256)
    source_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    revision_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    visibility: Optional[str] = Field(default=None, min_length=1, max_length=256)


class MemoryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: Optional[str] = Field(default=None, min_length=1, max_length=256)

    @field_serializer(
        "started_at", "ended_at", "timestamp", "temporal_anchor", "observed_at", "deadline", check_fields=False
    )
    def wire_timestamp(self, value):
        return value.isoformat() if value is not None else None


class MemoryCommandResult(BaseModel):
    operation_id: Optional[str] = None
    actor_id: Optional[str] = None
    was_replay: bool = False


class ToolCallSpec(MemoryProvenance):
    tool_name: str = Field(min_length=1, max_length=256)
    call_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    arguments: Optional[JsonValue] = None
    output_kind: Optional[Literal["text", "json", "bytes"]] = None
    text_output: Optional[str] = None
    json_output: Optional[JsonValue] = None
    base64_output: Optional[str] = None
    mime_type: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=256)
    error: Optional[str] = Field(default=None, max_length=16000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    triggered_by: Optional[str] = Field(default=None, max_length=256)
    after: Optional[str] = Field(default=None, max_length=256)

    @field_serializer("started_at", "ended_at")
    def wire_timestamp(self, value):
        return value.isoformat() if value is not None else None

    @model_validator(mode="after")
    def supported_output(self):
        if self.output_kind is None:
            if self.text_output is not None:
                self.output_kind = "text"
            elif self.base64_output is not None:
                self.output_kind = "bytes"
            elif self.json_output is not None or (
                "json_output" in self.model_fields_set
                and not {"text_output", "base64_output"}.intersection(self.model_fields_set)
            ):
                self.output_kind = "json"
        selected = sum(value is not None for value in (self.text_output, self.json_output, self.base64_output))
        if self.output_kind == "json" and self.json_output is None:
            selected += 1
        if selected > 1:
            raise ValueError("Choose one tool output representation")
        if self.output_kind == "text" and self.text_output is None:
            raise ValueError("Text output requires text_output")
        if self.output_kind == "bytes" and self.base64_output is None:
            raise ValueError("Byte output requires base64_output")
        if self.base64_output is not None and not self.mime_type:
            raise ValueError("Byte output requires MIME")
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            raise ValueError("Tool end precedes start")
        if self.category in set(MemoryRecordKind) and self.category != MemoryRecordKind.EXECUTED_RESULT:
            raise ValueError("Tool category cannot override executed-result provenance")
        return self


class ToolCallOutcome(BaseModel):
    call_id: str
    action_node: int
    artifact_id: Optional[str] = None
    artifact_node: Optional[int] = None
    was_replay: bool = False


class MemorySource(MemoryProvenance):
    """Exactly one bounded source. Files are read only through the guild filesystem."""

    model_config = ConfigDict(extra="forbid")
    text: Optional[str] = None
    base64_data: Optional[str] = None
    media_link: Optional[MediaLink] = None
    mime_type: Optional[str] = Field(default=None, min_length=1, max_length=128)
    path_hint: Optional[str] = Field(default=None, max_length=512)
    id: Optional[str] = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def single_source(self):
        if sum(value is not None for value in (self.text, self.base64_data, self.media_link)) != 1:
            raise ValueError("Choose exactly one of text, base64_data or media_link")
        if self.media_link is not None and not self.media_link.on_filesystem:
            raise ValueError("Remote URLs and host paths are not ingestion sources")
        if self.visibility is not None:
            raise ValueError("Uniko 0.6.0 does not expose document visibility")
        if self.category in set(MemoryRecordKind) and self.category != MemoryRecordKind.EXTERNAL_EVIDENCE:
            raise ValueError("Document category cannot override external-evidence provenance")
        return self


class MemoryScope(BaseModel):
    """Explicit dimensional scope for a memory operation."""

    model_config = ConfigDict(extra="forbid")

    sessions: Optional[List[str]] = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Explicit sessions, or null to search this agent's private store without a session filter.",
    )
    participants: List[str] = Field(default_factory=list, max_length=32)
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    categories: List[str] = Field(default_factory=list, max_length=32)
    sources: List[str] = Field(default_factory=list, max_length=32)
    include_superseded: bool = False
    viewer: Optional[MemoryViewer] = None

    @model_validator(mode="after")
    def ordered_time(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError("since must precede until")
        return self


class RecordMemoryRequest(MemoryProvenance):
    """Write one bounded, idempotently identified memory record."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    sender_id: str = Field(min_length=1, max_length=256)
    kind: MemoryRecordKind
    content: str = Field(min_length=1, max_length=16000)
    content_type: str = Field(default="text/plain", min_length=1, max_length=128)

    @model_validator(mode="after")
    def assigned_kind(self):
        if self.category in set(MemoryRecordKind) and self.category != self.kind:
            raise ValueError("Category cannot override producer-assigned record kind")
        return self


class RecordMemoryResult(BaseModel):
    """Acknowledgement for an idempotent memory record write."""

    record_id: str
    session_id: str
    kind: MemoryRecordKind
    stored: bool = True


class FinalizeMemorySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class FinalizeMemorySessionResult(BaseModel):
    session_id: str
    rebuilt: bool
    transcript_chunks: int = 0
    observation_chunks: int = 0


class ForgetMemoryRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    kind: MemoryRecordKind


class DeleteMemorySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ForgetMemoryParticipantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str = Field(min_length=1, max_length=256)


class MemoryDeletionResult(BaseModel):
    nodes_redacted: int = 0
    nodes_deleted: int = 0
    edges_deleted: int = 0
    facts_invalidated: int = 0
    root_existed: bool = False


# ========== Observation Payloads ==========


class ObserveTurnRequest(MemoryProvenance):
    """Request to observe a conversation turn.

    Attributes:
        session_id: Session ID (defaults to agent's default_session_id)
        sender_id: ID of the message sender (participant)
        content: Message content text
        message_id: Optional unique message ID
        content_type: Content type (default: "text")
        timestamp: Message timestamp (defaults to current time)
        addressed_to: List of recipient IDs
        metadata: Additional key-value metadata
        attachments: List of attachments (IngestSource specs)
    """

    session_id: Optional[str] = Field(
        default=None, min_length=1, max_length=256, description="Session ID (defaults to agent's default_session_id)"
    )
    sender_id: str = Field(min_length=1, max_length=256, description="ID of the message sender")
    content: str = Field(min_length=1, max_length=16000, description="Message content text")
    message_id: Optional[str] = Field(
        default=None, min_length=1, max_length=256, description="Optional unique message ID"
    )
    content_type: Optional[str] = Field(default="text", description="Content type (text, markdown, html, etc.)")
    timestamp: Optional[datetime] = Field(default=None, description="Message timestamp (defaults to current time)")
    addressed_to: Optional[List[str]] = Field(default=None, description="List of recipient IDs")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional key-value metadata")
    attachments: Optional[List[MemorySource]] = Field(
        default=None, max_length=32, description="Bounded typed attachment sources"
    )

    tool_calls: List[ToolCallSpec] = Field(default_factory=list, max_length=32)

    @field_serializer("timestamp")
    def wire_timestamp(self, value):
        return value.isoformat() if value is not None else None

    @model_validator(mode="after")
    def assigned_category(self):
        if self.category not in {None, MemoryRecordKind.CONVERSATION_TURN.value}:
            raise ValueError("Ordinary observations have conversation_turn category")
        return self


class ObserveResult(MemoryCommandResult):
    """Response from observing a turn.

    Attributes:
        message_node_id: ID of created message node
        chunk_node_ids: IDs of created chunk nodes
        session_node_id: ID of session node
        sender_node_id: ID of sender participant node
        sender_id: Sender participant ID
        extracted_entities: List of (node_id, entity_text) tuples
        extracted_observations: List of observation node IDs
        attachment_count: Number of attachments processed
    """

    message_id: Optional[str] = None
    message_node_id: int
    chunk_node_ids: List[int]
    session_node_id: int
    sender_node_id: Optional[int] = None
    sender_id: Optional[str] = None
    extracted_entities: List[tuple[int, str]]
    extracted_observations: List[int]
    attachment_count: int
    attachments: List["IngestOutcome"] = Field(default_factory=list)
    tool_calls: List[ToolCallOutcome] = Field(default_factory=list)


# ========== Recall Payloads ==========


class RecallRequest(BaseModel):
    """Bounded recall request with an explicit session scope."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000, description="Query string for semantic search")
    scope: MemoryScope
    allowed_record_kinds: List[MemoryRecordKind] = Field(min_length=1, max_length=len(MemoryRecordKind))
    item_limit: int = Field(default=10, ge=1, le=50)
    max_characters: int = Field(default=6000, ge=1, le=32000)
    token_budget: Optional[int] = Field(default=None, ge=1, le=10000)
    min_score: Optional[float] = Field(default=None, ge=0, le=1)
    reranker: Optional[bool] = None
    reference_ts: Optional[datetime] = None


class RecallUserSessionsRequest(BaseModel):
    """Recall at most 32 finalized request sessions belonging to one user."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(pattern=r"^upa-.+", max_length=256)
    current_session_id: str = Field(pattern=r"^analysis-[0-9a-f]{64}$")
    allowed_record_kinds: List[MemoryRecordKind] = Field(min_length=1, max_length=len(MemoryRecordKind))
    item_limit: int = Field(default=10, ge=1, le=50)
    max_characters: int = Field(default=6000, ge=1, le=32000)
    token_budget: Optional[int] = Field(default=None, ge=1, le=10000)
    min_score: Optional[float] = Field(default=None, ge=0, le=1)
    reranker: Optional[bool] = None
    reference_ts: Optional[datetime] = None


class RecallItem(BaseModel):
    """Single recalled item from memory.

    Attributes:
        node_id: Node ID in the graph
        kind: Type of recall item (Fact, Observation, Chunk, etc.)
        score: Relevance score (0.0-1.0)
        content: Text content of the item
        sources: List of source items (provenance chain)
    """

    node_id: int
    kind: str
    record_kind: MemoryRecordKind
    score: float
    content: str
    sources: List[Dict[str, Any]]
    source_ids: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    source_id: Optional[str] = None
    revision_id: Optional[str] = None
    token_count: int = 0
    context: Optional[str] = None
    address: Optional[str] = None
    token_count_method: str = "native"
    legacy_metadata: bool = False


class RecallResponse(BaseModel):
    """Response with recalled knowledge.

    Attributes:
        items: List of recalled items ranked by relevance
        total_tokens: Total tokens in the context bundle
        phase1_only: Whether only phase 1 was executed
        phase2_only: Whether only phase 2 was executed
        coverage: Coverage score (0.0-1.0)
    """

    items: List[RecallItem]
    total_tokens: int
    phase1_only: bool
    phase2_only: bool
    coverage: float
    truncated: bool = False
    legacy_compatibility: bool = False
    legacy_limitations: List[str] = Field(default_factory=list)
    token_count_method: str = "native_or_cl100k_base"


# ========== Answer Payloads ==========


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Request to answer a question using memory + LLM.

    Attributes:
        question: Question to answer
        max_tokens: Legacy field; non-null values are rejected by Uniko 0.6.0 integration
        scope: Optional scope specification for recall
    """

    question: str = Field(description="Question to answer")
    max_tokens: Optional[int] = Field(
        default=None, description="Unsupported legacy generation control; use the Guild synthesis LLM limit"
    )
    scope: Optional[Dict[str, Any]] = Field(default=None, description="Scope specification for recall")


class AnswerResponse(BaseModel):
    """Response with generated answer.

    Attributes:
        text: Generated answer text
        model: LLM model used
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        recorded_episode: Episode node ID if recorded
        context: Recall context used for generation
        citations: List of citation sources
    """

    text: str
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    recorded_episode: Optional[int] = None
    context: RecallResponse
    citations: List[Dict[str, Any]]


# ========== Document Ingestion Payloads ==========


class IngestDocumentRequest(MemoryProvenance):
    """Ingest a document already stored in the injected guild filesystem."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    media_link: Optional[MediaLink] = Field(default=None, description="Guild-filesystem MediaLink")
    source: Optional[MemorySource] = None

    @model_validator(mode="after")
    def single_document(self):
        if (self.media_link is None) == (self.source is None):
            raise ValueError("Choose exactly one of media_link or source")
        if self.visibility is not None:
            raise ValueError("Uniko 0.6.0 does not expose document visibility")
        if self.category in set(MemoryRecordKind) and self.category != MemoryRecordKind.EXTERNAL_EVIDENCE:
            raise ValueError("Document category cannot override external-evidence provenance")
        return self


class IngestOutcome(BaseModel):
    """Response from document ingestion.

    Attributes:
        artifact_node_id: ID of created artifact node
        chunk_count: Number of chunks extracted
        page_count: Number of pages (for PDFs)
        extracted_entities: List of entity node IDs
        success: Whether ingestion succeeded
        error_message: Error message if failed
    """

    artifact_node_id: Optional[int] = None
    chunk_count: int = 0
    page_count: int = 0
    extracted_entities: List[int] = Field(default_factory=list)
    artifact_id: Optional[str] = None
    chunk_node_ids: List[int] = Field(default_factory=list)
    page_node_ids: List[int] = Field(default_factory=list)
    block_node_ids: List[int] = Field(default_factory=list)
    was_deduplicated: bool = False
    extraction_failed: Optional[bool] = None
    extraction_error: Optional[str] = None
    stored: bool = False
    tool_calls: List[ToolCallOutcome] = Field(default_factory=list)
    searchable: bool = False
    success: bool = True
    record_id: Optional[str] = None


class BatchSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    """Request to submit multiple turns in batch (streaming mode).

    Attributes:
        session_id: Session ID (defaults to agent's default_session_id)
        turns: List of turn specifications
        flush_after: Whether to flush after all turns
    """

    session_id: Optional[str] = Field(
        default=None, min_length=1, max_length=256, description="Session ID (defaults to agent's default_session_id)"
    )
    batch_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    turns: List[Dict[str, Any]] = Field(
        max_length=128, description="List of turn specs (sender_id, content, metadata, etc.)"
    )
    flush_after: bool = Field(default=True, description="Whether to flush after all turns")


class BatchSubmitResponse(BaseModel):
    """Response from batch submission.

    Attributes:
        submitted_count: Number of turns submitted
        flushed: Whether flush was performed
        session_id: Session ID used
    """

    outcomes: List["BatchItemOutcome"] = Field(default_factory=list)
    terminal: bool = True
    error: Optional[str] = None
    submitted_count: int = Field(description="Items known to have been stored")
    uncertain_count: int = 0
    flushed: bool
    session_id: str


class BatchItemOutcome(BaseModel):
    stored: Optional[bool] = Field(
        default=False, description="True/False for known storage outcomes; null when the effect is uncertain"
    )
    operation: Optional[str] = None
    operation_id: Optional[str] = None
    tool_calls: List[ToolCallOutcome] = Field(default_factory=list)
    attachments: List[IngestOutcome] = Field(default_factory=list)
    index: int
    message_id: Optional[str] = None
    success: bool
    error: Optional[str] = None


class EffectiveConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityRequest(EffectiveConfigRequest):
    pass


class MemoryHealthRequest(EffectiveConfigRequest):
    pass


class MemoryDiagnostics(BaseModel):
    configured: Dict[str, Any] = Field(default_factory=dict)
    observed: Dict[str, Any] = Field(default_factory=dict)
    unknown: List[str] = Field(default_factory=list)


class SourceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    scope: MemoryScope
    limit: int = Field(default=10, ge=1, le=50)
    max_characters: int = Field(default=6000, ge=1, le=32000)


class SourceReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_kind: Literal["message", "artifact"]
    source_id: str = Field(min_length=1, max_length=256)
    scope: MemoryScope
    operation: Literal["read", "outline", "original"] = "read"
    address: Optional[str] = Field(default=None, max_length=512)
    bytes: Optional[tuple[int, int]] = None
    lines: Optional[tuple[int, int]] = None
    chunks: Optional[tuple[int, int]] = None
    max_tokens: int = Field(default=2000, ge=1, le=10000)
    depth: int = Field(default=2, ge=1, le=8)
    max_entries: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def single_address(self):
        if sum(x is not None for x in (self.address, self.bytes, self.lines, self.chunks)) > 1:
            raise ValueError("Choose one source address")
        for bounds in (self.bytes, self.lines, self.chunks):
            if bounds and (bounds[0] < 0 or bounds[1] <= bounds[0]):
                raise ValueError("Invalid source range")
        if self.operation == "original" and self.source_kind != "artifact":
            raise ValueError("Original bytes require an artifact")
        return self


class SourceResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    base64_data: Optional[str] = None
    available: bool = True
    truncated: bool = False


# ========== Goal Management Payloads ==========


class CreateGoalRequest(MemoryCommand):
    """Request to create a new goal.

    Attributes:
        title: Goal title
        goal_id: Optional unique goal ID
        description: Optional goal description
        status: Initial status (default: "active")
        metrics: Optional success metrics
        guardrails: Optional constraints/rules
        deadline: Optional deadline
        parent_goal_id: Optional parent goal ID for sub-goals
    """

    title: str = Field(description="Goal title")
    goal_id: Optional[str] = Field(default=None, description="Optional unique goal ID")
    description: Optional[str] = Field(default=None, description="Goal description")
    status: str = Field(default="active", description="Initial status (active, completed, abandoned)")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="Success metrics")
    guardrails: Optional[List[str]] = Field(default=None, description="Constraints/rules")
    deadline: Optional[datetime] = Field(default=None, description="Optional deadline")
    parent_goal_id: Optional[str] = Field(default=None, description="Parent goal ID for sub-goals")


class GoalView(MemoryCommandResult):
    """View of a goal.

    Attributes:
        goal_id: Goal ID
        node_id: Graph node ID
        title: Goal title
        description: Goal description
        status: Current status
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metrics: Success metrics
        guardrails: Constraints
        deadline: Optional deadline
    """

    goal_id: str
    node_id: Optional[int] = None  # Not available in uniko GoalView
    title: str
    description: Optional[str] = None
    status: str
    phase: Optional[str] = None
    completed_at: Optional[datetime] = None
    parent_goal_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    guardrails: Optional[List[str]] = None
    deadline: Optional[datetime] = None

    @field_serializer("created_at", "updated_at", "completed_at", "deadline")
    def wire_timestamp(self, value):
        return value.isoformat() if value is not None else None


class UpdateGoalRequest(MemoryCommand):
    """Request to update a goal's status.

    Attributes:
        goal_id: Goal ID to update
        action: Action to perform (start, complete, abandon)
        outcome: Optional outcome description
        metadata: Optional additional metadata
    """

    goal_id: str = Field(description="Goal ID to update")
    action: Literal["start", "complete", "abandon"]
    outcome: Optional[str] = Field(default=None, description="Outcome description")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class GoalStatusResponse(MemoryCommandResult):
    """Response from goal update.

    Attributes:
        goal_id: Goal ID
        status: New status
        updated: Whether update succeeded
    """

    goal_id: str
    status: Optional[str] = None
    updated: bool


class GetGoalsRequest(BaseModel):
    """Request to get goals.

    Attributes:
        phase: Filter by phase (all, active, completed, abandoned)
        parent_goal_id: Filter by parent goal
        limit: Maximum number of goals to return
    """

    owner_id: Optional[str] = Field(default=None, max_length=256)
    phase: Literal["all", "planned", "active", "completed", "abandoned"] = "all"
    parent_goal_id: Optional[str] = Field(default=None, description="Filter by parent goal ID")
    limit: Optional[int] = Field(default=20, ge=1, le=100, description="Maximum number of goals")


class GoalsListResponse(BaseModel):
    """Response with list of goals.

    Attributes:
        goals: List of goal views
        total_count: Total number of goals
        phase: Phase filter used
    """

    goals: List[GoalView]
    total_count: int
    phase: str


# ========== Task Management Payloads ==========


class CreateTaskRequest(MemoryCommand):
    """Request to create a task for a goal.

    Attributes:
        goal_id: Parent goal ID
        title: Task title
        task_id: Optional unique task ID
        description: Optional task description
        priority: Task priority (1-5, default 3)
        depends_on: Optional list of task IDs this depends on
    """

    goal_id: str = Field(description="Parent goal ID")
    title: str = Field(description="Task title")
    task_id: Optional[str] = Field(default=None, description="Optional unique task ID")
    description: Optional[str] = Field(default=None, description="Task description")
    priority: Optional[int] = Field(
        default=None, ge=1, le=5, description="Legacy priority (1-5); defaults to 3 when native_priority is absent"
    )
    depends_on: Optional[List[str]] = Field(
        default=None, max_length=1, description="The native SDK supports one dependency"
    )
    subtask_of_task_id: Optional[str] = Field(default=None, max_length=256)
    native_priority: Optional[float] = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def single_priority(self):
        if self.native_priority is not None and self.priority is not None:
            raise ValueError("Choose legacy priority or native_priority")
        if self.native_priority is None and self.priority is None:
            self.priority = 3
        return self


class TaskView(MemoryCommandResult):
    """View of a task.

    Attributes:
        task_id: Task ID
        node_id: Graph node ID
        goal_id: Parent goal ID
        title: Task title
        description: Task description
        status: Current status
        priority: Task priority
        created_at: Creation timestamp
    """

    task_id: str
    node_id: Optional[int] = None  # Not available in uniko TaskView
    goal_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: Optional[float] = None
    phase: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @field_serializer("created_at", "completed_at")
    def wire_timestamp(self, value):
        return value.isoformat() if value is not None else None


class UpdateTaskRequest(MemoryCommand):
    """Request to update a task's status.

    Attributes:
        task_id: Task ID to update
        action: Action to perform (start, complete, abandon, block, unblock)
        outcome: Optional outcome description
    """

    task_id: str = Field(description="Task ID to update")
    action: Literal["start", "complete", "abandon", "block", "unblock"]
    outcome: Optional[str] = Field(default=None, description="Outcome description")


class TaskStatusResponse(MemoryCommandResult):
    """Response from task update.

    Attributes:
        task_id: Task ID
        status: New status
        updated: Whether update succeeded
    """

    task_id: str
    status: Optional[str] = None
    updated: bool


class GoalContextRequest(BaseModel):
    """Request to get goal working memory context.

    Attributes:
        goal_id: Goal ID
        include_tasks: Include related tasks
        include_episodes: Include related episodes
    """

    goal_id: str = Field(description="Goal ID")
    owner_id: Optional[str] = Field(default=None, max_length=256)
    include_tasks: bool = Field(default=True, description="Include related tasks")
    include_episodes: bool = Field(default=True, description="Include related episodes")


class GoalContext(BaseModel):
    """Goal working memory context.

    Attributes:
        goal: Goal view
        tasks: Related tasks
        episodes: Related episode summaries
        progress: Progress metrics
    """

    goal: GoalView
    tasks: List[TaskView]
    episodes: List[Dict[str, Any]]
    progress: Dict[str, Any]
    sessions: List[str] = Field(default_factory=list)
    recent_messages: List[str] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    episodes_available: bool = False


# ========== Error Payload ==========


class MemoryAgentError(BaseModel):
    """Error response from MemoryAgent.

    Attributes:
        error: Error type/category
        message: Human-readable error message
        details: Additional error details
    """

    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(extra="forbid")


ObserveResult.model_rebuild()
BatchSubmitResponse.model_rebuild()
