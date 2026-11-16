"""Uniko Memory Agent module for Rustic AI.

This module provides a comprehensive memory agent that leverages the uniko
cognitive memory system for episodic, semantic, and procedural memory.
"""

from .agent import MemoryAgent
from .config import MemoryAgentConfig
from .initializer import MemoryRequestInitializerAgent
from .memories import UnikoMemoriesStore
from .models import (  # Observation; Recall; Answer; Document ingestion; Goal management; Task management; Error
    AnswerRequest,
    AnswerResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
    CreateGoalRequest,
    CreateTaskRequest,
    DeleteMemorySessionRequest,
    FinalizeMemorySessionRequest,
    FinalizeMemorySessionResult,
    ForgetMemoryParticipantRequest,
    ForgetMemoryRecordRequest,
    GetGoalsRequest,
    GoalContext,
    GoalContextRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    MemoryDeletionResult,
    MemoryRecordKind,
    MemoryScope,
    ObserveResult,
    ObserveTurnRequest,
    RecallItem,
    RecallRequest,
    RecallResponse,
    RecallUserSessionsRequest,
    RecordMemoryRequest,
    RecordMemoryResult,
    TaskStatusResponse,
    TaskView,
    UpdateGoalRequest,
    UpdateTaskRequest,
)
from .resolver import UnikoResolver

__all__ = [
    # Main agent and config
    "MemoryAgent",
    "MemoryRequestInitializerAgent",
    "MemoryAgentConfig",
    "UnikoResolver",
    "UnikoMemoriesStore",
    # Observation payloads
    "ObserveTurnRequest",
    "ObserveResult",
    # Recall payloads
    "RecallRequest",
    "RecallUserSessionsRequest",
    "RecallResponse",
    "RecallItem",
    "MemoryScope",
    "MemoryRecordKind",
    "RecordMemoryRequest",
    "RecordMemoryResult",
    "FinalizeMemorySessionRequest",
    "FinalizeMemorySessionResult",
    "ForgetMemoryRecordRequest",
    "DeleteMemorySessionRequest",
    "ForgetMemoryParticipantRequest",
    "MemoryDeletionResult",
    # Answer payloads
    "AnswerRequest",
    "AnswerResponse",
    # Document ingestion payloads
    "IngestDocumentRequest",
    "IngestOutcome",
    "BatchSubmitRequest",
    "BatchSubmitResponse",
    # Goal management payloads
    "CreateGoalRequest",
    "GoalView",
    "UpdateGoalRequest",
    "GoalStatusResponse",
    "GetGoalsRequest",
    "GoalsListResponse",
    # Task management payloads
    "CreateTaskRequest",
    "TaskView",
    "UpdateTaskRequest",
    "TaskStatusResponse",
    "GoalContextRequest",
    "GoalContext",
    # Error payloads
    "MemoryAgentError",
]
