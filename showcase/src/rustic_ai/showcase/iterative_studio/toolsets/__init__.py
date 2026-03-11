"""Toolsets for the Iterative Studio guild.

This module provides specialized toolsets for different operational modes:
- ArxivToolset: Search academic papers on ArXiv
- AgenticToolset: File operations and web search for Agentic mode
- DeepthinkToolset: Strategic reasoning tools for Adaptive Deepthink mode
"""


def __getattr__(name: str):
    """Lazy import of toolsets to avoid circular imports."""
    if name == "ArxivToolset":
        from rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset import (
            ArxivToolset,
        )

        return ArxivToolset
    elif name == "AgenticToolset":
        from rustic_ai.showcase.iterative_studio.toolsets.agentic_toolset import (
            AgenticToolset,
        )

        return AgenticToolset
    elif name == "DeepthinkToolset":
        from rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset import (
            DeepthinkToolset,
        )

        return DeepthinkToolset
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ArxivToolset", "AgenticToolset", "DeepthinkToolset"]
