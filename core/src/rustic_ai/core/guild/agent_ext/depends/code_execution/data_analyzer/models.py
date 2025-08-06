from enum import Enum
import time
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.utils.json_utils import JsonDict

# ---------------------------
# I. TRANSFORMATION MODELS
# ---------------------------


class BaseTransformation(BaseModel):
    """Base model for all dataset transformations.

    All transformation types inherit from this base class.
    """

    op: str


class FilterTransformation(BaseTransformation):
    """Filter rows in a dataset based on a boolean expression.

    Attributes:
        expr: Boolean expression used to filter rows (e.g., "age > 30")
    """

    op: Literal["filter"] = "filter"
    expr: str


class DropColumnsTransformation(BaseTransformation):
    """Drop specified columns from a dataset.

    Attributes:
        columns: List of column names to drop
    """

    op: Literal["drop_columns"] = "drop_columns"
    columns: List[str]


class RenameColumnsTransformation(BaseTransformation):
    """Rename multiple columns in a dataset.

    Attributes:
        columns: Dictionary mapping old column names to new column names
    """

    op: Literal["rename_columns"] = "rename_columns"
    columns: Dict[str, str]


class RenameColumnTransformation(BaseTransformation):
    """Rename a single column in a dataset.

    Attributes:
        old_name: Current name of the column
        new_name: New name for the column
    """

    op: Literal["rename_column"] = "rename_column"
    old_name: str
    new_name: str


class FFillTransformation(BaseTransformation):
    """Forward-fill missing values in specified columns.

    Attributes:
        columns: List of column names to forward-fill, or "all" for all columns
    """

    op: Literal["ffill"] = "ffill"
    columns: Union[List[str], Literal["all"]]


class ToDatetimeTransformation(BaseTransformation):
    """Convert columns to datetime type.

    Attributes:
        columns: List of column names to convert to datetime
        format: Optional datetime format string (e.g., "%Y-%m-%d")
    """

    op: Literal["to_datetime"] = "to_datetime"
    columns: List[str]
    format: Optional[str] = None


class ToNumericTransformation(BaseTransformation):
    """Convert columns to numeric type.

    Attributes:
        columns: List of column names to convert to numeric
        errors: How to handle errors ('raise', 'coerce', or 'ignore')
    """

    op: Literal["to_numeric"] = "to_numeric"
    columns: List[str]
    errors: Literal["raise", "coerce", "ignore"] = "coerce"


class UniqueValuesTransformation(BaseTransformation):
    """Extract unique values from specified columns.

    Attributes:
        columns: List of column names to extract unique values from
        limit: Optional maximum number of unique values to return
    """

    op: Literal["unique_values"] = "unique_values"
    columns: List[str]
    limit: Optional[int] = 1000


class ValueCountsTransformation(BaseTransformation):
    """Get value counts for specified columns.

    Attributes:
        columns: List of column names to get value counts for
        normalize: If True, return proportions instead of counts
        max_unique_values: Maximum number of unique values to return
    """

    op: Literal["value_counts"] = "value_counts"
    columns: List[str]
    normalize: bool = False
    max_unique_values: int = 50


# Type for any transformation
TransformationType = Union[
    FilterTransformation,
    DropColumnsTransformation,
    RenameColumnsTransformation,
    RenameColumnTransformation,
    FFillTransformation,
    ToDatetimeTransformation,
    ToNumericTransformation,
    UniqueValuesTransformation,
    ValueCountsTransformation,
    str,
    JsonDict,
]

# ---------------------------
# I. REQUEST MODELS
# ---------------------------


class LoadDatasetRequest(BaseModel):
    """Request to load a dataset from a given source.

    Attributes:
        name: Name to assign the dataset in memory.
        source: MediaLink object representing the source of the dataset.
        format: Optional file format ('csv', 'json', 'parquet', etc.).
        options: Format-specific read options (e.g., {'delimiter': ';'}).
        transformations: Optional list of transformations to apply immediately after loading.
        custom_name: Optional custom name override for the dataset.
        additional_info: Optional additional information to return with dataset summary.
    """

    name: str
    source: MediaLink
    options: Optional[Dict[str, Any]] = None
    transformations: Optional[List[TransformationType]] = None
    custom_name: Optional[str] = None
    additional_info: Optional[Dict[str, List[TransformationType]]] = None

    def get_dataset_name(self) -> str:
        """Get the name to use for the dataset."""
        if self.custom_name:
            return self.custom_name
        return self.name


class LoadDatasetsRequest(BaseModel):
    """Request to load multiple datasets from a list of sources.

    Attributes:
        datasets: List of dataset loading requests.
    """

    datasets: List[LoadDatasetRequest]


class ListDatasetsRequest(BaseModel):
    """Request to list all currently loaded datasets.

    Attributes:
        command: Command to execute (e.g., 'list_datasets').
    """

    command: str = "list_datasets"


class UnloadDatasetRequest(BaseModel):
    """Request to unload a dataset from memory.

    Attributes:
        name: Name of the dataset to unload.
    """

    name: str


class ResetStateRequest(BaseModel):
    """Request to clear all loaded datasets and reset the analyzer's internal state.

    Attributes:
        command: Command to execute (e.g., 'reset_state').
    """

    command: str = "reset_state"


class GetStateMetadataRequest(BaseModel):
    """Request to retrieve metadata about all loaded datasets.

    Attributes:
        command: Command to execute (e.g., 'get_state_metadata').
    """

    command: str = "get_state_metadata"


class GetSchemaRequest(BaseModel):
    """Request to get schema for a dataset.

    Attributes:
        name: Name of the dataset to get schema for.
    """

    name: str


class GetAllSchemasRequest(BaseModel):
    """Request to get schemas for all loaded datasets.

    Attributes:
        command: Command to execute (e.g., 'get_all_schemas').
    """

    command: str = "get_all_schemas"


class PreviewDatasetRequest(BaseModel):
    """Request to preview rows from a dataset.

    Attributes:
        name: Name of the dataset to preview.
        num_rows: Number of rows to preview.
        include_schema: If True, include schema in the response.
    """

    name: str
    num_rows: int = 5
    include_schema: bool = False


class GetDatasetSummaryRequest(BaseModel):
    """Request to get summary of a dataset.

    Attributes:
        name: Name of the dataset to summarize.
    """

    name: str


class GetDescriptiveStatisticsRequest(BaseModel):
    """Request to get descriptive statistics for a dataset.

    Attributes:
        name: Name of the dataset.
        columns: Optional list of specific columns to summarize.
        include_categoricals: If True, include categorical variables in the summary.
    """

    name: str
    columns: Optional[List[str]] = None
    include_categoricals: bool = True


class ValueCountsRequest(BaseModel):
    """Request to get value counts for a specific column in a dataset.

    Attributes:
        name: Name of the dataset.
        column: Column name to get value counts for.
        normalize: If True, return proportions instead of counts.
    """

    name: str
    column: str
    normalize: bool = False
    max_unique_values: int = 50


class CorrelationMatrixRequest(BaseModel):
    """Request to get correlation matrix for a dataset.

    Attributes:
        name: Name of the dataset.
        method: Correlation method ('pearson', 'kendall', 'spearman').
        min_periods: Minimum number of observations required for each pair of columns.
    """

    name: str
    method: str = "pearson"
    min_periods: int = 1
    columns: Optional[List[str]] = None


class TransformDatasetRequest(BaseModel):
    """Request to apply a series of transformations to a dataset.

    Attributes:
        name: The name of the dataset to transform.
        xformed_name: Optional custom name for the transformed dataset.
        transformations: List of transformation commands.
    """

    name: str
    xformed_name: Optional[str] = None
    transformations: List[TransformationType]

    def get_xformed_name(self) -> str:
        """Get the name of the transformed dataset."""
        if self.xformed_name:
            return self.xformed_name
        return f"{self.name}_transformed_{time.time()}"


class JoinDatasetsRequest(BaseModel):
    """Request to join two datasets.

    Attributes:
        left_name: Name of the left dataset.
        right_name: Name of the right dataset.
        on: The column name to join on.
        how: Type of join ('inner', 'left', 'right', 'outer').
        joined_name: Optional custom name for the joined dataset.
    """

    left_name: str
    right_name: str
    on: str
    how: str = "inner"
    joined_name: Optional[str] = None

    def get_joined_name(self) -> str:
        """Get the name of the joined dataset."""
        if self.joined_name:
            return self.joined_name
        return f"{self.left_name}_{self.right_name}_joined_{time.time()}"


class CleanDatasetRequest(BaseModel):
    """Request to clean a dataset.

    Attributes:
        name: Name of the dataset to clean.
        strategy: Dictionary of cleaning operations (e.g., {'dropna': True}).
        cleaned_name: Optional custom name for the cleaned dataset.
    """

    name: str
    strategy: Dict[str, Any]
    cleaned_name: Optional[str] = None

    def get_cleaned_name(self) -> str:
        """Get the name of the cleaned dataset."""
        if self.cleaned_name:
            return self.cleaned_name
        return f"{self.name}_cleaned_{time.time()}"


class QueryLanguage(str, Enum):
    SQL = "sql"
    PANDAS_QUERY = "pandas_query"


class QueryExecutionRequest(BaseModel):
    """Request to execute a query on one or more datasets.

    Attributes:
        query_language: Language used for querying ('sql', 'pandas_query', etc.).
        query_string: The query to execute.
        input_datasets: Mapping from query table names to dataset names.
        output_dataset_name: Optional name to save the result as a new dataset.
        explain: If True, return an explanation or query plan.
    """

    query_language: QueryLanguage = Field(default=QueryLanguage.SQL)
    query_string: str
    input_datasets: Dict[str, str]
    output_dataset_name: Optional[str] = None
    explain: bool = False

    def get_output_dataset_name(self) -> Optional[str]:
        """Get the output dataset name if one is requested."""
        if not self.output_dataset_name:
            return None
        return self.output_dataset_name


# ---------------------------
# II. RESPONSE MODELS
# ---------------------------


class DatasetListResponse(BaseModel):
    """Response listing currently loaded datasets.

    Attributes:
        datasets: List of dataset names in memory.
    """

    datasets: List[str]


class UnloadDatasetResponse(BaseModel):
    """Response confirming a dataset was unloaded.

    Attributes:
        message: A message confirming successful unload.
    """

    message: str


class StateResetResponse(BaseModel):
    """Response confirming all datasets were cleared from memory.

    Attributes:
        message: A message confirming state reset.
    """

    message: str


class StateMetadataResponse(BaseModel):
    """Response providing metadata on all loaded datasets.

    Attributes:
        metadata: Dictionary of dataset-level metadata.
    """

    metadata: Dict[str, Any]


class DatasetSchemaResponse(BaseModel):
    """Response containing schema of a dataset.

    Attributes:
        dataschema: Mapping of column names to data types.
    """

    dataschema: Dict[str, str]


class AllSchemasResponse(BaseModel):
    """Response containing schemas of all loaded datasets.

    Attributes:
        schemas: Dictionary mapping dataset names to their schemas.
    """

    schemas: Dict[str, Dict[str, str]]


class DatasetPreviewResponse(BaseModel):
    """Response with a preview of the dataset.

    Attributes:
        columns: List of column names.
        data: Rows from the dataset (as lists of values).
        dataschema: Optional schema for the previewed dataset.
    """

    columns: List[str]
    data: List[List[Any]]
    dataschema: Optional[Dict[str, str]] = None


class DatasetSummaryResponse(BaseModel):
    """Response summarizing a dataset.

    Attributes:
        name: Name of the dataset.
        num_rows: Number of rows.
        num_columns: Number of columns.
        column_names: List of column names.
        memory_usage: Optional string representing memory used.
        basic_stats: Optional basic statistics (e.g., min, max, mean).
    """

    name: str
    num_rows: int
    num_columns: int
    column_names: List[str]
    dataschema: Dict[str, str]
    memory_usage: Optional[str] = None
    basic_stats: Optional[Dict[str, Any]] = None
    additional_info: Optional[Dict[str, Any]] = None


class DatasetSummariesResponse(BaseModel):
    """Response summarizing multiple datasets.

    Attributes:
        summaries: List of dataset summaries.
    """

    summaries: List[DatasetSummaryResponse]


class DescriptiveStatsResponse(BaseModel):
    """Response with detailed descriptive statistics.

    Attributes:
        stats: Dictionary with statistical measures like count, mean, std, etc.
    """

    stats: Dict[str, Any]


class ValueCountsResponse(BaseModel):
    """Response with value counts for a specific column.

    Attributes:
        counts: Mapping of unique values to their counts or proportions.
    """

    counts: Dict[Union[str, int, float], Union[int, float]]


class CorrelationMatrixResponse(BaseModel):
    """Response with pairwise correlation values.

    Attributes:
        correlation: Nested dictionary representing the correlation matrix.
    """

    correlation: Dict[str, Dict[str, float]]


class QueryExecutionResponse(BaseModel):
    """Response to a query execution.

    Attributes:
        output_dataset_name: Name of the resulting dataset if it was saved.
        columns: List of column names in the result.
        data: List of rows returned.
        explanation: Optional explanation or query plan.
    """

    output_dataset_name: Optional[str] = None
    columns: List[str]
    data: List[List[Any]]
    explanation: Optional[str] = None
