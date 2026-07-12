"""Configuration for MemoryAgent."""

from typing import Optional

from pydantic import Field

from rustic_ai.core.guild.dsl import BaseAgentProps


class MemoryAgentConfig(BaseAgentProps):
    """Configuration for MemoryAgent.

    Attributes:
        default_session_id: Default session ID for observations (defaults to guild_id if not set)
        recall_max_tokens: Maximum tokens for recall context bundles (default: 2000)
        recall_phase1_only: Restrict recall to phase 1 (facts/procedures) only (default: False)
        answer_max_tokens: Maximum tokens for generated answers (default: 500)
        auto_flush: Auto-flush observations after each turn (default: True)
    """

    default_session_id: Optional[str] = Field(
        default=None,
        description="Default session ID for observations (defaults to guild_id)"
    )

    recall_max_tokens: int = Field(
        default=2000,
        ge=100,
        le=10000,
        description="Max tokens for recall context bundles"
    )

    recall_phase1_only: bool = Field(
        default=False,
        description="Restrict recall to phase 1 (facts/procedures) only"
    )

    answer_max_tokens: int = Field(
        default=500,
        ge=50,
        le=5000,
        description="Max tokens for generated answers"
    )

    auto_flush: bool = Field(
        default=True,
        description="Auto-flush observations after each turn"
    )
