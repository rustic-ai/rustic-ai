"""
DatasetLoadedEmitter - ToolCallWrapper that emits events on dataset load.

This wrapper intercepts load_file tool calls and emits a DatasetLoadedEvent
message containing dataset metadata. The event is routed to the enrichment
LLMAgent via guild routing rules.
"""

import json
import logging
from typing import Optional, Union

from pydantic import BaseModel, Field
from rustic_ai.llm_agent.plugins.tool_call_wrapper import (
    ToolCallResult,
    ToolCallWrapper,
    ToolSkipResult,
)

from rustic_ai.core.guild.agent import Agent, ProcessContext

from .models import DatasetLoadedEvent

logger = logging.getLogger(__name__)


class DatasetLoadedEmitter(ToolCallWrapper):
    """
    Intercepts load_file tool calls and emits DatasetLoadedEvent.

    The event is routed to the enrichment LLMAgent via guild routes,
    where it is transformed into a ChatCompletionRequest for metadata
    generation.

    Configuration:
        sample_rows: Number of sample rows to include in the event (default: 5)
    """

    sample_rows: int = Field(default=5, description="Number of sample rows to include")

    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
    ) -> Union[BaseModel, ToolSkipResult]:
        """Pass through tool input unchanged."""
        return tool_input

    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext,
        tool_name: str,
        tool_input: BaseModel,
        tool_output: str,
    ) -> ToolCallResult:
        """
        After load_file executes, emit a DatasetLoadedEvent.

        The event contains dataset metadata that will be used by the
        enrichment LLMAgent to generate rich semantic descriptions.
        """
        # Only intercept load_file tool
        if tool_name != "load_file":
            return ToolCallResult(output=tool_output)

        # Check for error in output
        if "error" in tool_output.lower():
            return ToolCallResult(output=tool_output)

        try:
            event = self._build_event(agent, tool_input, tool_output)
            if event is None:
                return ToolCallResult(output=tool_output)

            logger.debug(f"Emitting DatasetLoadedEvent for dataset: {event.dataset_name}")
            return ToolCallResult(output=tool_output, messages=[event])

        except Exception as e:
            logger.warning(f"Failed to emit DatasetLoadedEvent: {e}")
            return ToolCallResult(output=tool_output)

    def _build_event(
        self,
        agent: Agent,
        tool_input: BaseModel,
        tool_output: str,
    ) -> Optional[DatasetLoadedEvent]:
        """
        Build a DatasetLoadedEvent from the tool execution context.

        Accesses the analyzer via agent's toolset to get dataset metadata.
        """
        # Access analyzer via agent's toolset
        toolset = getattr(agent.config, "toolset", None)
        if toolset is None:
            logger.debug("No toolset found on agent config")
            return None

        analyzer = getattr(toolset, "_analyzer", None)
        if analyzer is None:
            logger.debug("No analyzer found on toolset")
            return None

        # Get dataset name
        dataset_name = self._extract_dataset_name(tool_input, tool_output)
        if not dataset_name:
            logger.debug("Could not determine dataset name")
            return None

        try:
            # Get dataset info from analyzer
            summary = analyzer.get_dataset_summary(dataset_name)
            schema = analyzer.get_schema(dataset_name)
            preview = analyzer.preview_dataset(dataset_name, num_rows=self.sample_rows)

            # Convert list of lists to list of dicts for sample_data
            sample_data = [
                dict(zip(preview.columns, row)) for row in preview.data[: self.sample_rows]
            ]

            return DatasetLoadedEvent(
                dataset_name=dataset_name,
                row_count=summary.num_rows,
                column_count=summary.num_columns,
                columns=summary.column_names,
                column_schema=schema.dataschema,
                sample_data=sample_data,
                load_summary=tool_output,
            )

        except Exception as e:
            logger.warning(f"Failed to get dataset info: {e}")
            return None

    def _extract_dataset_name(self, tool_input: BaseModel, tool_output: str) -> Optional[str]:
        """
        Extract dataset name from tool input or output.

        Priority:
        1. dataset_name from tool_input
        2. Derived from filename in tool_input
        3. Parsed from tool_output JSON
        """
        # Try from input - dataset_name field
        if hasattr(tool_input, "dataset_name") and tool_input.dataset_name:
            return tool_input.dataset_name

        # Try from input - derive from filename
        if hasattr(tool_input, "filename") and tool_input.filename:
            # Extract name from path (e.g., "/tmp/sales.csv" -> "sales")
            filename = tool_input.filename.split("/")[-1]
            name = filename.rsplit(".", 1)[0]
            if name:
                return name

        # Try from output JSON
        try:
            output_data = json.loads(tool_output)
            if isinstance(output_data, dict):
                if "dataset_name" in output_data:
                    return output_data["dataset_name"]
                if "name" in output_data:
                    return output_data["name"]
        except (json.JSONDecodeError, TypeError):
            pass

        return None
