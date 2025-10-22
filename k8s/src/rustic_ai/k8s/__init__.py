"""Rustic AI Kubernetes Execution Engine.

This module provides a Kubernetes-native execution engine for Rustic AI
as an alternative to the Ray-based execution engine.
"""

from rustic_ai.k8s.engine import K8sExecutionEngine
from rustic_ai.k8s.placement import AgentPlacementService
from rustic_ai.k8s.registry import AgentLocationRegistry

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "K8sExecutionEngine",
    "AgentPlacementService",
    "AgentLocationRegistry",
]
