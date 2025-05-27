from abc import abstractmethod
from typing import List, Optional

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from ..stateful import CodeExecutor
from .models import (
    AllSchemasResponse,
    CleanDatasetRequest,
    CorrelationMatrixResponse,
    DatasetListResponse,
    DatasetPreviewResponse,
    DatasetSchemaResponse,
    DatasetSummariesResponse,
    DatasetSummaryResponse,
    DescriptiveStatsResponse,
    JoinDatasetsRequest,
    LoadDatasetRequest,
    QueryExecutionRequest,
    QueryExecutionResponse,
    StateMetadataResponse,
    StateResetResponse,
    TransformDatasetRequest,
    UnloadDatasetResponse,
    ValueCountsResponse,
)


class DataAnalyzer(CodeExecutor):
    """
    Abstract base class for LLM-friendly data analysis tools.

    Designed for structured and serializable interaction, this class defines a set of
    methods for inspecting, transforming, and querying tabular data using Pydantic
    request and response models. It is intended to support safe and predictable interaction
    between an execution engine and a Large Language Model (LLM)-driven agent.

    Each method adheres to a strict contract to enable discoverability, validation, and
    automatic generation of API schemas or tool descriptions.
    """

    # ----------------------------
    # I. DATA LOADING & STATE
    # ----------------------------

    @abstractmethod
    def load_dataset(self, request: LoadDatasetRequest, filesystem: FileSystem) -> DatasetSummaryResponse:
        """
        Load a dataset into memory using the specified parameters.

        Args:
            request (LoadDatasetRequest): Includes dataset name, source URI, format, and optional read options.

        Returns:
            DatasetSummaryResponse: Summary of the loaded dataset including rows, columns, and basic stats.
        """
        pass

    def load_datasets(
        self,
        requests: List[LoadDatasetRequest],
        filesystem: FileSystem,
    ) -> DatasetSummariesResponse:
        """
        Load multiple datasets into memory.

        Args:
            requests (List[LoadDatasetRequest]): List of dataset loading requests.
            filesystem (FileSystem): Filesystem object for file operations.

        Returns:
            DatasetSummariesResponse: Summary of each loaded dataset.
        """
        return DatasetSummariesResponse(summaries=[self.load_dataset(request, filesystem) for request in requests])

    @abstractmethod
    def list_datasets(self) -> DatasetListResponse:
        """
        List all currently loaded datasets.

        Returns:
            DatasetListResponse: Names of datasets currently in memory.
        """
        pass

    @abstractmethod
    def unload_dataset(self, name: str) -> UnloadDatasetResponse:
        """
        Remove a dataset from memory.

        Args:
            name (str): Name of the dataset to unload.

        Returns:
            UnloadDatasetResponse: Confirmation message.
        """
        pass

    @abstractmethod
    def reset_state(self) -> StateResetResponse:
        """
        Clear all loaded datasets and reset the analyzer's internal state.

        Returns:
            StateResetResponse: Confirmation message.
        """
        pass

    @abstractmethod
    def get_state_metadata(self) -> StateMetadataResponse:
        """
        Retrieve metadata about all loaded datasets.

        Returns:
            StateMetadataResponse: Metadata for each dataset.
        """
        pass

    # ----------------------------
    # II. INSPECTION & DISCOVERY
    # ----------------------------

    @abstractmethod
    def get_schema(self, name: str) -> DatasetSchemaResponse:
        """
        Retrieve the dataschema (column names and types) of the specified dataset.

        Args:
            name (str): Name of the dataset to inspect.

        Returns:
            DatasetSchemaResponse: Contains the `dataschema` dictionary mapping column names to types.
        """
        pass

    def get_all_schemas(self) -> AllSchemasResponse:
        """
        Retrieve schemas for all loaded datasets.

        Returns:
            AllSchemasResponse: Dictionary mapping dataset names to their schemas.
        """

        datasets = self.list_datasets().datasets
        schemas = {dataset: self.get_schema(dataset).dataschema for dataset in datasets}
        return AllSchemasResponse(schemas=schemas)

    @abstractmethod
    def preview_dataset(
        self,
        name: str,
        num_rows: int = 5,
        include_schema: bool = False,
    ) -> DatasetPreviewResponse:
        """
        Preview a few rows from a dataset, optionally including its dataschema.

        Args:
            name (str): Name of the dataset.
            num_rows (int): Number of rows to preview.
            include_schema (bool): Whether to include the dataset schema in the response.

        Returns:
            DatasetPreviewResponse: Includes `columns`, `data`, and optionally `dataschema`.
        """
        pass

    @abstractmethod
    def get_dataset_summary(self, name: str) -> DatasetSummaryResponse:
        """
        Get a high-level summary of the dataset, including dimensions and column info.

        Args:
            name (str): Dataset name.

        Returns:
            DatasetSummaryResponse: Summary details such as row/column count and memory usage.
        """
        pass

    # ----------------------------
    # III. ANALYSIS OPERATIONS
    # ----------------------------

    @abstractmethod
    def get_descriptive_statistics(
        self,
        name: str,
        columns: Optional[List[str]] = None,
        include_categoricals: bool = True,
    ) -> DescriptiveStatsResponse:
        """
        Generate descriptive statistics (e.g., count, mean, std) for numeric and/or categorical columns.

        Args:
            name (str): Dataset name.
            columns (List[str] | None): Subset of columns to include. If None, analyze all.
            include_categoricals (bool): Whether to include object/category column stats.

        Returns:
            DescriptiveStatsResponse: Statistics per column.
        """
        pass

    @abstractmethod
    def get_value_counts(
        self,
        name: str,
        column: str,
        normalize: bool = False,
        max_unique_values: int = 50,
    ) -> ValueCountsResponse:
        """
        Get the count (or percentage) of unique values in a specific column.

        Args:
            name (str): Dataset name.
            column (str): Column to analyze.
            normalize (bool): If True, return proportions instead of raw counts.
            max_unique_values (int): Limit number of returned values for large categories.

        Returns:
            ValueCountsResponse: Frequency distribution of values.
        """
        pass

    @abstractmethod
    def get_correlation(
        self,
        name: str,
        columns: Optional[List[str]] = None,
        method: str = "pearson",
    ) -> CorrelationMatrixResponse:
        """
        Compute a correlation matrix for numeric columns in the dataset.

        Args:
            name (str): Dataset name.
            columns (List[str] | None): Optional subset of columns to include.
            method (str): Correlation method to use ('pearson', 'spearman', 'kendall').

        Returns:
            CorrelationMatrixResponse: Nested dictionary representing the correlation matrix.
        """
        pass

    # ----------------------------
    # IV. TRANSFORMATION & CLEANING
    # ----------------------------

    @abstractmethod
    def transform_dataset(self, request: TransformDatasetRequest) -> DatasetSummaryResponse:
        """
        Apply a series of transformations to an existing dataset.

        Args:
            request (TransformDatasetRequest): Contains dataset name and transformation commands.

        Returns:
            DatasetSummaryResponse: Summary of the transformed dataset.
        """
        pass

    @abstractmethod
    def join_datasets(self, request: JoinDatasetsRequest) -> DatasetSummaryResponse:
        """
        Join two datasets on a specified column.

        Args:
            request (JoinDatasetsRequest): Contains left/right dataset names, join key, and method.

        Returns:
            DatasetSummaryResponse: Summary of the joined dataset.
        """
        pass

    @abstractmethod
    def clean_data(self, request: CleanDatasetRequest) -> DatasetSummaryResponse:
        """
        Apply cleaning operations to a dataset, such as filling missing values or dropping duplicates.

        Args:
            request (CleanDatasetRequest): Contains cleaning strategy.

        Returns:
            DatasetSummaryResponse: Summary of the cleaned dataset.
        """
        pass

    # ----------------------------
    # V. QUERYING
    # ----------------------------

    @abstractmethod
    def execute_query(self, request: QueryExecutionRequest) -> QueryExecutionResponse:
        """
        Execute a query (e.g., SQL or pandas-style) on one or more datasets.

        Args:
            request (QueryExecutionRequest): Query language, query string, input datasets, and optional result storage.

        Returns:
            QueryExecutionResponse: Query result preview and optional explanation.
        """
        pass
