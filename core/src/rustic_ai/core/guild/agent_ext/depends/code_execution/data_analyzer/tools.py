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

    @property
    def toolsmanager(self) -> ToolsManager:
        """
        Returns the ToolsManager instance for this tool set.
        """
        return self.create_tools_manager()

    def get_data_analyst_tools(self) -> List[ToolSpec]:
        """
        Returns a list of tool specifications for the data analyst.
        """
        return [
            ToolSpec(
                name=FUNC_PREVIEW_DATASET,
                description="Preview the first few rows of a dataset to understand its structure",
                parameter_class=PreviewDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_SUMMARIZE_DATASET,
                description="Get a summary of a dataset including row/column count and basic stats",
                parameter_class=GetDatasetSummaryRequest,
            ),
            ToolSpec(
                name=FUNC_QUERY_DATASET,
                description="""Execute a query (SQL or pandas-style) on one or more datasets.
                Always prefer SQL queries if possible. SQL queries are run using DuckDB.""",
                parameter_class=QueryExecutionRequest,
            ),
            ToolSpec(
                name=FUNC_TRANSFORM_DATASET,
                description="Apply transformations to a dataset (filter, select, etc.)",
                parameter_class=TransformDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_DESCRIBE_DATASET,
                description="Get descriptive statistics for numeric columns in a dataset",
                parameter_class=GetDescriptiveStatisticsRequest,
            ),
            ToolSpec(
                name=FUNC_JOIN_DATASETS,
                description="Join two datasets on common columns",
                parameter_class=JoinDatasetsRequest,
            ),
            ToolSpec(
                name=FUNC_LIST_DATASETS,
                description="List all available datasets",
                parameter_class=ListDatasetsRequest,
            ),
            ToolSpec(
                name=FUNC_GET_SCHEMA,
                description="Get the schema of a dataset (column names and types)",
                parameter_class=GetSchemaRequest,
            ),
            ToolSpec(
                name=FUNC_CLEAN_DATASET,
                description="Clean a dataset by handling missing values, outliers, etc.",
                parameter_class=CleanDatasetRequest,
            ),
            ToolSpec(
                name=FUNC_VALUE_COUNTS,
                description="Get the frequency distribution of values in a column",
                parameter_class=ValueCountsRequest,
            ),
            ToolSpec(
                name=FUNC_CORRELATION_MATRIX,
                description="Calculate correlation matrix for numeric columns in a dataset",
                parameter_class=CorrelationMatrixRequest,
            ),
            ToolSpec(
                name=FUNC_ASK_USER,
                description="Pose a single clarifying question to the user and wait for the answer",
                parameter_class=AskUserRequest,
            ),
        ]

    def create_tools_manager(self) -> ToolsManager:
        """
        Creates a ToolsManager with all data analyst tools.
        """
        return ToolsManager(self.get_data_analyst_tools())
