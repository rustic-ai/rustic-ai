"""Uniko Memory Agent module for Rustic AI.

This module provides a comprehensive memory agent that leverages the uniko
cognitive memory system for episodic, semantic, and procedural memory.
"""

from .agent import MemoryAgent
from .config import MemoryAgentConfig
from .models import (  # Observation; Recall; Answer; Document ingestion; Goal management; Task management; Error
    AnswerRequest,
    AnswerResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
    CreateGoalRequest,
    CreateTaskRequest,
    GetGoalsRequest,
    GoalContext,
    GoalContextRequest,
    GoalsListResponse,
    GoalStatusResponse,
    GoalView,
    IngestDocumentRequest,
    IngestOutcome,
    MemoryAgentError,
    ObserveResult,
    ObserveTurnRequest,
    RecallItem,
    RecallRequest,
    RecallResponse,
    TaskStatusResponse,
    TaskView,
    UpdateGoalRequest,
    UpdateTaskRequest,
)
from .resolver import UnikoResolver

__all__ = [
    # Main agent and config
    "MemoryAgent",
    "MemoryAgentConfig",
    "UnikoResolver",
    # Observation payloads
    "ObserveTurnRequest",
    "ObserveResult",
    # Recall payloads
    "RecallRequest",
    "RecallResponse",
    "RecallItem",
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
