"""
EnrichmentContextPreprocessor - Injects Codex enrichment context into prompts.

This preprocessor reads enrichment metadata from guild state and adds a
system message with dataset context, enabling the ReActAgent to make
more informed decisions about data analysis.
"""

import logging
from typing import List, Optional

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    SystemMessage,
)
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor

from .models import DatasetEnrichmentMetadata

logger = logging.getLogger(__name__)


class EnrichmentContextPreprocessor(RequestPreprocessor):
    """
    Injects Codex enrichment metadata into prompts.

    Reads enrichment metadata from guild state (codex_enrichment.datasets)
    and adds a system message with dataset context. This enables the
    ReActAgent to understand dataset semantics and make better analysis
    decisions.

    Guild state structure expected:
        {
            "codex_enrichment": {
                "datasets": {
                    "dataset_name": { ...DatasetEnrichmentMetadata... }
                }
            }
        }
    """

    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        """
        Inject enrichment context into the request.

        Reads enrichment metadata from guild state and adds a system
        message with dataset context.
        """
        enrichments = self._get_enrichments_from_state(agent)
        logger.debug(f"Found {len(enrichments)} enrichments in guild state.")

        if not enrichments:
            return request

        context_message = self._build_enrichment_context(enrichments)
        if not context_message:
            return request

        # Insert after existing system messages
        new_messages = list(request.messages)
        insert_pos = 0
        for i, msg in enumerate(new_messages):
            if isinstance(msg, SystemMessage):
                insert_pos = i + 1

        new_messages.insert(insert_pos, SystemMessage(content=context_message))

        return ChatCompletionRequest(
            messages=new_messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tool_choice=request.tool_choice,
        )

    def _get_enrichments_from_state(self, agent: Agent) -> List[DatasetEnrichmentMetadata]:
        """
        Read enrichment metadata from agent._guild_state.

        Returns a list of valid DatasetEnrichmentMetadata objects.
        Invalid entries are skipped with a debug log.
        """
        enrichments: List[DatasetEnrichmentMetadata] = []
        try:
            guild_state = agent.get_guild_state()
            logger.debug(f"Guild state retrieved for enrichment: {guild_state}")
            if guild_state is None:
                return enrichments

            codex_enrichment = guild_state.get("codex_enrichment", {})
            datasets = codex_enrichment.get("datasets", {})

            for name, data in datasets.items():
                try:
                    enrichment = DatasetEnrichmentMetadata.model_validate(data)
                    enrichments.append(enrichment)
                except Exception as e:
                    logger.debug(f"Invalid enrichment data for {name}: {e}")

        except Exception as e:
            logger.warning(f"Could not read enrichments from guild state: {e}")

        return enrichments

    def _build_enrichment_context(self, enrichments: List[DatasetEnrichmentMetadata]) -> Optional[str]:
        """
        Build a context message from enrichment metadata.

        Returns a formatted string with dataset context for the LLM,
        or None if no enrichments are available.
        """
        if not enrichments:
            return None

        parts = ["## Available Datasets with Codex Enrichment\n"]

        for enrichment in enrichments:
            parts.append(f"### Dataset: {enrichment.dataset_name}")
            parts.append(f"**Purpose:** {enrichment.table_purpose}")
            parts.append(
                f"**Grain:** {enrichment.grain_description} "
                f"({enrichment.row_count:,} rows, {enrichment.column_count} columns)"
            )

            if enrichment.primary_key_candidates:
                parts.append(f"**Primary Key Candidates:** {', '.join(enrichment.primary_key_candidates)}")

            # Column descriptions (limit to first 10)
            if enrichment.columns:
                parts.append("\n**Columns:**")
                for col in enrichment.columns[:10]:
                    pk_marker = " [PK candidate]" if col.is_primary_key_candidate else ""
                    parts.append(f"- `{col.name}` ({col.semantic_type}): {col.description}{pk_marker}")
                if len(enrichment.columns) > 10:
                    parts.append(f"  ... and {len(enrichment.columns) - 10} more columns")

            # Usage recommendations
            if enrichment.recommended_usage:
                parts.append("\n**Recommended Usage:**")
                for usage in enrichment.recommended_usage[:3]:
                    parts.append(f"- {usage}")

            if enrichment.when_to_use:
                parts.append(f"\n**When to Use:** {enrichment.when_to_use}")

            if enrichment.limitations:
                parts.append(f"\n**Limitations:** {', '.join(enrichment.limitations[:3])}")

            parts.append("")  # Blank line between datasets

        parts.append("\nUse this context to better understand the data when answering user questions.")

        return "\n".join(parts)
