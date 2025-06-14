"""
Multiprocess Execution Engine

This module provides a multiprocess execution engine that runs agents in separate
processes to escape the Python GIL and achieve true parallelism.

Features:
- True parallelism by escaping the GIL
- Process isolation for robustness
- Shared memory tracking for agent management
- Graceful shutdown handling
- Support for distributed messaging backends

Classes:
    MultiProcessExecutionEngine: Main execution engine class
    MultiProcessAgentWrapper: Wrapper for running agents in processes
    MultiProcessAgentTracker: Tracker for managing agent processes
"""

from .agent_tracker import MultiProcessAgentTracker
from .multiprocess_agent_wrapper import MultiProcessAgentWrapper
from .multiprocess_exec_engine import MultiProcessExecutionEngine

__all__ = ["MultiProcessExecutionEngine", "MultiProcessAgentWrapper", "MultiProcessAgentTracker"]
