"""Payload models for MemoryAgent requests and responses."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from rustic_ai.core.agents.commons.media import MediaLink


class MemoryRecordKind(StrEnum):
    """Application-level provenance assigned before content enters memory."""

    USER_ASSERTION = "user_assertion"
    EXTERNAL_EVIDENCE = "external_evidence"
    DETERMINISTIC_OBSERVATION = "deterministic_observation"
    MODEL_INTERPRETATION = "model_interpretation"
    EXECUTED_RESULT = "executed_result"
    ASSISTANT_RESPONSE = "assistant_response"


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


class RecordMemoryRequest(BaseModel):
    """Write one bounded, idempotently identified memory record."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    sender_id: str = Field(min_length=1, max_length=256)
    kind: MemoryRecordKind
    content: str = Field(min_length=1, max_length=16000)
    content_type: str = Field(default="text/plain", min_length=1, max_length=128)


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


class ObserveTurnRequest(BaseModel):
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

    session_id: Optional[str] = Field(default=None, description="Session ID (defaults to agent's default_session_id)")
    sender_id: str = Field(description="ID of the message sender")
    content: str = Field(description="Message content text")
    message_id: Optional[str] = Field(default=None, description="Optional unique message ID")
    content_type: Optional[str] = Field(default="text", description="Content type (text, markdown, html, etc.)")
    timestamp: Optional[datetime] = Field(default=None, description="Message timestamp (defaults to current time)")
    addressed_to: Optional[List[str]] = Field(default=None, description="List of recipient IDs")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional key-value metadata")
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="List of attachment specs (path, url, mime_type)"
    )


class ObserveResult(BaseModel):
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

    message_node_id: int
    chunk_node_ids: List[int]
    session_node_id: int
    sender_node_id: Optional[int] = None
    sender_id: Optional[str] = None
    extracted_entities: List[tuple[int, str]]
    extracted_observations: List[int]
    attachment_count: int


# ========== Recall Payloads ==========


class RecallRequest(BaseModel):
    """Bounded recall request with an explicit session scope."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000, description="Query string for semantic search")
    scope: MemoryScope
    allowed_record_kinds: List[MemoryRecordKind] = Field(min_length=1, max_length=len(MemoryRecordKind))
    item_limit: int = Field(default=10, ge=1, le=50)
    max_characters: int = Field(default=6000, ge=1, le=32000)


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


# ========== Answer Payloads ==========


class AnswerRequest(BaseModel):
    """Request to answer a question using memory + LLM.

    Attributes:
        question: Question to answer
        max_tokens: Maximum tokens for answer generation (overrides config)
        scope: Optional scope specification for recall
    """

    question: str = Field(description="Question to answer")
    max_tokens: Optional[int] = Field(
        default=None, description="Maximum tokens for answer generation (overrides config)"
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


class IngestDocumentRequest(BaseModel):
    """Ingest a document already stored in the injected guild filesystem."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    session_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    media_link: MediaLink = Field(description="Guild-filesystem MediaLink (on_filesystem=True)")


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
    extracted_entities: List[int] = []
    success: bool = True
    record_id: Optional[str] = None


class BatchSubmitRequest(BaseModel):
    """Request to submit multiple turns in batch (streaming mode).

    Attributes:
        session_id: Session ID (defaults to agent's default_session_id)
        turns: List of turn specifications
        flush_after: Whether to flush after all turns
    """

    session_id: Optional[str] = Field(default=None, description="Session ID (defaults to agent's default_session_id)")
    turns: List[Dict[str, Any]] = Field(description="List of turn specs (sender_id, content, metadata, etc.)")
    flush_after: bool = Field(default=True, description="Whether to flush after all turns")


class BatchSubmitResponse(BaseModel):
    """Response from batch submission.

    Attributes:
        submitted_count: Number of turns submitted
        flushed: Whether flush was performed
        session_id: Session ID used
    """

    submitted_count: int
    flushed: bool
    session_id: str


# ========== Goal Management Payloads ==========


class CreateGoalRequest(BaseModel):
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


class GoalView(BaseModel):
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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    guardrails: Optional[List[str]] = None
    deadline: Optional[datetime] = None


class UpdateGoalRequest(BaseModel):
    """Request to update a goal's status.

    Attributes:
        goal_id: Goal ID to update
        action: Action to perform (start, complete, abandon, pause, resume)
        outcome: Optional outcome description
        metadata: Optional additional metadata
    """

    goal_id: str = Field(description="Goal ID to update")
    action: str = Field(description="Action: start, complete, abandon, pause, resume")
    outcome: Optional[str] = Field(default=None, description="Outcome description")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class GoalStatusResponse(BaseModel):
    """Response from goal update.

    Attributes:
        goal_id: Goal ID
        status: New status
        updated: Whether update succeeded
    """

    goal_id: str
    status: str
    updated: bool


class GetGoalsRequest(BaseModel):
    """Request to get goals.

    Attributes:
        phase: Filter by phase (all, active, completed, abandoned)
        parent_goal_id: Filter by parent goal
        limit: Maximum number of goals to return
    """

    phase: str = Field(default="all", description="Phase filter: all, active, completed, abandoned")
    parent_goal_id: Optional[str] = Field(default=None, description="Filter by parent goal ID")
    limit: Optional[int] = Field(default=None, description="Maximum number of goals")


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


class CreateTaskRequest(BaseModel):
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
    priority: int = Field(default=3, ge=1, le=5, description="Task priority (1-5)")
    depends_on: Optional[List[str]] = Field(default=None, description="Task IDs this depends on")


class TaskView(BaseModel):
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
    goal_id: str
    title: str
    description: Optional[str] = None
    status: str
    priority: int
    created_at: Optional[datetime] = None


class UpdateTaskRequest(BaseModel):
    """Request to update a task's status.

    Attributes:
        task_id: Task ID to update
        action: Action to perform (start, complete, abandon, block, unblock)
        outcome: Optional outcome description
    """

    task_id: str = Field(description="Task ID to update")
    action: str = Field(description="Action: start, complete, abandon, block, unblock")
    outcome: Optional[str] = Field(default=None, description="Outcome description")


class TaskStatusResponse(BaseModel):
    """Response from task update.

    Attributes:
        task_id: Task ID
        status: New status
        updated: Whether update succeeded
    """

    task_id: str
    status: str
    updated: bool


class GoalContextRequest(BaseModel):
    """Request to get goal working memory context.

    Attributes:
        goal_id: Goal ID
        include_tasks: Include related tasks
        include_episodes: Include related episodes
    """

    goal_id: str = Field(description="Goal ID")
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

    model_config = ConfigDict(extra="forbid")

    model_config = ConfigDict(extra="forbid")

    model_config = ConfigDict(extra="forbid")
