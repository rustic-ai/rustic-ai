"""Configuration for MemoryAgent."""

from typing import Dict, List, Optional

from pydantic import Field, model_validator

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
        default=None, description="Default session ID for observations (defaults to guild_id)"
    )

    recall_max_tokens: Optional[int] = Field(
        default=None, ge=100, le=10000, description="Max tokens for recall context bundles"
    )

    recall_phase1_only: bool = Field(default=False, description="Restrict recall to phase 1 (facts/procedures) only")

    answer_max_tokens: Optional[int] = Field(
        default=None, ge=50, le=5000, description="Max tokens for generated answers"
    )

    auto_flush: bool = Field(default=True, description="Auto-flush observations after each turn")

    allowed_record_producers: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Optional record-kind to allowed sender-id map. Configured kinds fail closed for other senders.",
    )

    conversation_request_producers: List[str] = Field(default_factory=list)
    conversation_response_producers: List[str] = Field(default_factory=list)

    scope_producers: List[str] = Field(
        default_factory=list, description="When configured, only these trusted agents may select memory scopes"
    )
    viewer_producers: List[str] = Field(default_factory=list)

    max_source_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_attachments: int = Field(default=32, ge=1, le=32)
    max_batch_items: int = Field(default=128, ge=1, le=128)
    legacy_recall_limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def supported_controls(self):
        if self.recall_phase1_only:
            raise ValueError("Uniko 0.5.1 does not expose phase1-only recall")
        if self.answer_max_tokens is not None:
            raise ValueError("Configure generation limits on the Guild synthesis LLM agent")
        return self
