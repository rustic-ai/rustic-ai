"""
Tool definitions for the data analyst agent.
"""

from typing import List

from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import (
    Toolset,
    ToolsManager,
    ToolSpec,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

from .models import (
    CleanDatasetRequest,
    CorrelationMatrixRequest,
    GetDatasetSummaryRequest,
    GetDescriptiveStatisticsRequest,
    GetSchemaRequest,
    JoinDatasetsRequest,
    ListDatasetsRequest,
    PreviewDatasetRequest,
    QueryExecutionRequest,
    TransformDatasetRequest,
    ValueCountsRequest,
)

# Function names as constants for consistency
FUNC_PREVIEW_DATASET = "preview_dataset"
FUNC_SUMMARIZE_DATASET = "summarize_dataset"
FUNC_QUERY_DATASET = "query_dataset"
FUNC_TRANSFORM_DATASET = "transform_dataset"
FUNC_DESCRIBE_DATASET = "describe_dataset"
FUNC_JOIN_DATASETS = "join_datasets"
FUNC_LIST_DATASETS = "list_datasets"
FUNC_GET_SCHEMA = "get_schema"
FUNC_CLEAN_DATASET = "clean_dataset"
FUNC_VALUE_COUNTS = "value_counts"
FUNC_CORRELATION_MATRIX = "correlation_matrix"
FUNC_ASK_USER = "ask_user"


class AskUserRequest(BaseModel):
    """Simple class for user confirmation questions."""

    question: str


class DataAnalystToolset(Toolset):

    def toolsmanager(self) -> ToolsManager:
        """
        Returns the ToolsManager instance for this tool set.
        """
        return self.create_tools_manager()

    def get_data_analyst_tools(self) -> List[ToolSpec]:
        """
        Return ToolSpec objects that map natural-language requests
        to the right data-analysis function.
        """
        return [
            ToolSpec(
                name=FUNC_PREVIEW_DATASET,
                description="Preview the first N rows of a dataset when the user asks to ‘peek’, ‘sample rows’, or similar.",
                parameter_class=PreviewDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_SUMMARIZE_DATASET,
                description="Return a quick profile—row/column counts and basic stats—when the user wants a dataset ‘summary’ or ‘overview’.",
                parameter_class=GetDatasetSummaryRequest,
            ),
            ToolSpec(
                name=FUNC_QUERY_DATASET,
                description="Run an SQL query to filter, aggregate, or compute metrics such as ‘total sales’ or ‘average by month’.",
                parameter_class=QueryExecutionRequest,
            ),
            ToolSpec(
                name=FUNC_TRANSFORM_DATASET,
                description="Apply structural or type transformations (filter rows, drop/rename columns, convert data types, forward-fill, etc.).",
                parameter_class=TransformDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_DESCRIBE_DATASET,
                description="Produce descriptive statistics (count, mean, quartiles) for numeric—and optionally categorical—columns.",
                parameter_class=GetDescriptiveStatisticsRequest,
            ),
            ToolSpec(
                name=FUNC_JOIN_DATASETS,
                description="SQL-style join of two datasets on a key when the user wants to ‘merge’ or ‘combine’ data.",
                parameter_class=JoinDatasetsRequest,
            ),
            ToolSpec(
                name=FUNC_LIST_DATASETS,
                description="Return the list of all datasets currently loaded in memory.",
                parameter_class=ListDatasetsRequest,
            ),
            ToolSpec(
                name=FUNC_GET_SCHEMA,
                description="Return the column names and data types for a dataset.",
                parameter_class=GetSchemaRequest,
            ),
            ToolSpec(
                name=FUNC_CLEAN_DATASET,
                description="Perform common cleaning steps (drop NAs, handle outliers, impute, etc.) according to a strategy dictionary.",
                parameter_class=CleanDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_VALUE_COUNTS,
                description="Return counts or proportions for each unique value in a column.",
                parameter_class=ValueCountsRequest,
            ),
            ToolSpec(
                name=FUNC_CORRELATION_MATRIX,
                description="Compute Pearson, Kendall, or Spearman correlations between numeric columns.",
                parameter_class=CorrelationMatrixRequest,
            ),
            ToolSpec(
                name=FUNC_ASK_USER,
                description="Pose one clarifying question if a required parameter is missing or ambiguous.",
                parameter_class=AskUserRequest,
            ),
        ]

    def create_tools_manager(self) -> ToolsManager:
        """
        Creates a ToolsManager with all data analyst tools.
        """
        return ToolsManager(self.get_data_analyst_tools())

    @classmethod
    def get_qualified_class_name(cls) -> str:
        """
        Returns the fully qualified class name of this toolset.
        """
        return get_qualified_class_name(cls)
