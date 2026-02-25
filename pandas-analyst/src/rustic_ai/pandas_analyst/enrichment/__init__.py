"""
Codex Enrichment System for Pandas Analyst Guild.

This package provides automatic dataset enrichment capabilities:
- DatasetLoadedEmitter: ToolCallWrapper that emits events when datasets are loaded
- EnrichmentContextPreprocessor: RequestPreprocessor that injects enrichment context
- DatasetEnrichmentMetadata: Pydantic model for rich dataset metadata
- DatasetLoadedEvent: Event emitted to trigger enrichment

Usage:
    In guild configuration, add the emitter and preprocessor to the ReActAgent:

    {
        "request_preprocessors": [
            {"kind": "rustic_ai.pandas_analyst.enrichment.EnrichmentContextPreprocessor"}
        ],
        "tool_wrappers": [
            {"kind": "rustic_ai.pandas_analyst.enrichment.DatasetLoadedEmitter"}
        ]
    }

    Add routing rules to transform DatasetLoadedEvent to ChatCompletionRequest
    and store the response in guild state.
"""

from .emitter import DatasetLoadedEmitter
from .models import ColumnSemantics, DatasetEnrichmentMetadata, DatasetLoadedEvent
from .preprocessor import EnrichmentContextPreprocessor

__all__ = [
    "ColumnSemantics",
    "DatasetEnrichmentMetadata",
    "DatasetLoadedEvent",
    "DatasetLoadedEmitter",
    "EnrichmentContextPreprocessor",
]
