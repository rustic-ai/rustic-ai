"""
ReAct (Reasoning and Acting) Agent Module.

This module provides a loop-based implementation of the ReAct pattern,
where an agent iteratively reasons about a problem and takes actions
(tool calls) until it arrives at a final answer.

Key Components:
- ReActAgent: The agent that runs the ReAct loop
- ReActAgentConfig: Configuration for the ReActAgent
- ReActToolset: Abstract base class for defining tools with execution logic
- CompositeToolset: Combines multiple toolsets into one
- ReActRequest: Input message format for the agent
- ReActResponse: Output message format with answer and trace
- ReActStep: Single step in the reasoning trace

Example Usage:
    from rustic_ai.llm_agent.react import (
        ReActAgent,
        ReActAgentConfig,
        ReActToolset,
        ReActRequest,
    )

    # Define a custom toolset
    class MyToolset(ReActToolset):
        def get_toolspecs(self):
            return [...]

        def execute(self, tool_name, args):
            ...

    # Create agent config
    config = ReActAgentConfig(
        model="gpt-4",
        max_iterations=10,
        toolset=MyToolset()
    )

    # Build agent spec
    agent_spec = (
        AgentBuilder(ReActAgent)
        .set_name("react-agent")
        .set_config(config)
        .build_spec()
    )
"""

from .models import ReActRequest, ReActResponse, ReActStep
from .react_agent import DEFAULT_REACT_SYSTEM_PROMPT, ReActAgent, ReActAgentConfig
from .toolset import CompositeToolset, ReActToolset

__all__ = [
    # Agent
    "ReActAgent",
    "ReActAgentConfig",
    "DEFAULT_REACT_SYSTEM_PROMPT",
    # Toolset
    "ReActToolset",
    "CompositeToolset",
    # Models
    "ReActRequest",
    "ReActResponse",
    "ReActStep",
]
