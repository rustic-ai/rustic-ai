"""Uniko Memory Agent module for Rustic AI.

This module provides a comprehensive memory agent that leverages the uniko
cognitive memory system for episodic, semantic, and procedural memory.
"""

from .agent import MemoryAgent
from .config import MemoryAgentConfig
from .resolver import UnikoResolver
from .models import (
    # Observation
    ObserveTurnRequest,
    ObserveResult,
    # Recall
    RecallRequest,
    RecallResponse,
    RecallItem,
    # Answer
    AnswerRequest,
    AnswerResponse,
    # Document ingestion
    IngestDocumentRequest,
    IngestOutcome,
    BatchSubmitRequest,
    BatchSubmitResponse,
    # Goal management
    CreateGoalRequest,
    GoalView,
    UpdateGoalRequest,
    GoalStatusResponse,
    GetGoalsRequest,
    GoalsListResponse,
    # Task management
    CreateTaskRequest,
    TaskView,
    UpdateTaskRequest,
    TaskStatusResponse,
    GoalContextRequest,
    GoalContext,
    # Error
    MemoryAgentError,
)

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
