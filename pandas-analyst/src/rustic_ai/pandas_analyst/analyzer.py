import logging
import time
from typing import Any, Dict, Optional, Union

import duckdb
from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pandas as pd
from pandas.errors import UndefinedVariableError

from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer import (
    BaseTransformation,
    CleanDatasetRequest,
    ColumnNotFoundError,
    CorrelationMatrixResponse,
    DataAnalyzer,
    DataCleaningError,
    DatasetListResponse,
    DatasetNotFoundError,
    DatasetPreviewResponse,
    DatasetSchemaResponse,
    DatasetSummaryResponse,
    DescriptiveStatsResponse,
    DropColumnsTransformation,
    FFillTransformation,
    FileLoadError,
    FilterTransformation,
    InvalidQueryError,
    InvalidTransformationError,
    JoinDatasetsRequest,
    JoinError,
    LoadDatasetRequest,
    QueryExecutionRequest,
    QueryExecutionResponse,
    RenameColumnsTransformation,
    RenameColumnTransformation,
    StateMetadataResponse,
    StateResetResponse,
    ToDatetimeTransformation,
    ToNumericTransformation,
    TransformDatasetRequest,
    UniqueValuesTransformation,
    UnloadDatasetResponse,
    UnsupportedFormatError,
    ValueCountsResponse,
    ValueCountsTransformation,
)
from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful import (
    PythonExecExecutor,
)
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)


class PandasDataAnalyzer(PythonExecExecutor, DataAnalyzer):
    """
    A pandas-based implementation of the DataAnalyzer interface for LLM-assisted data analysis.

    This class provides a comprehensive interface for data analysis operations using pandas,
    allowing LLMs to perform complex data operations in a controlled environment. It supports
    operations such as loading datasets, data transformation, joining, cleaning, and querying.

    Features:
        - In-memory dataset management with named references
        - Support for multiple file formats (CSV, JSON, Parquet, Excel)
        - Data transformation operations (filtering, column operations)
        - Dataset joining and cleaning capabilities
        - Query execution using both pandas query syntax and SQL

    The Datasets are loaded to _local_vars["datasets"] dictionary, which is exposed in the code execution context.
    """

    def __init__(self) -> None:
        """
        Initialize the analyzer with an empty dataset dictionary.
        """
        super().__init__()
        self.datasets: Dict[str, pd.DataFrame] = {}
        self._local_vars["datasets"] = self.datasets  # expose datasets in code execution context

    def load_dataset(self, request: LoadDatasetRequest, filesystem: FileSystem) -> DatasetSummaryResponse:
        """
        Load a dataset from a file into memory.

        Supports multiple file formats including CSV, JSON, Parquet, and Excel.
        The format can be explicitly specified or inferred from the file extension.
        Optionally applies transformations after loading the dataset.

        Args:
            request (LoadDatasetRequest): A request object containing:
                - name: Name to assign to the dataset
                - source: File path or URL to load from
                - options: Optional dict of pandas read options
                - transformations: Optional list of transformations to apply after loading
                - additional_info: Optional additional information to return with dataset summary

        Returns:
            DatasetSummaryResponse: Summary statistics of the loaded dataset

        Raises:
            UnsupportedFormatError: If the file format is not supported
            FileLoadError: If the file fails to load for any reason
            InvalidTransformationError: If a transformation is invalid

        Example:
            response = analyzer.load_dataset(LoadDatasetRequest(
                name="sales_data",
                source="sales.csv",
                options={"index_col": 0},
                transformations=["filter:price > 100"]
            ))
        """
        logging.info(
            f"Loading dataset: {request.name} from {request.source} with mimetype={request.source.get_mimetype()}"
        )
        try:
            mimetype = request.source.get_mimetype()

            read_opts = request.options or {}

            if not request.source.on_filesystem:
                raise FileLoadError(f"File {request.source.id} is not on the filesystem")

            if mimetype == "text/csv":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_csv(f, **read_opts)
            elif mimetype == "text/tab-separated-values":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_csv(f, sep="\t", **read_opts)
            elif mimetype == "application/json":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_json(f, **read_opts)
            elif mimetype == "application/x-jsonl":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_json(f, lines=True, **read_opts)
            elif mimetype == "application/x-parquet":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_parquet(f, **read_opts)
            elif (
                mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                or mimetype == "application/vnd.ms-excel"
                or mimetype == "application/xlsx"
            ):
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_excel(f, **read_opts)
            elif mimetype == "application/x-hdf":
                with filesystem.open(request.source.url, "rb") as f:
                    df = pd.read_hdf(f, **read_opts)
            else:
                raise UnsupportedFormatError(f"Unsupported format '{mimetype}'.")

            # Apply transformations if provided
            if request.transformations:
                for transformation in request.transformations:
                    df = self._apply_transformation(df, transformation)

            # Handle additional summaries if specified
            additional_info = {}
            if request.additional_info:
                for info_key, xforms in request.additional_info.items():
                    temp_df = df.copy()
                    for xform in xforms:
                        temp_df = self._apply_transformation(temp_df, xform)
                    additional_info[info_key] = temp_df.to_dict(orient="records")

            # Use the new get_dataset_name method
            dataset_name = request.get_dataset_name()
            self.datasets[dataset_name] = df
            return self.get_dataset_summary(dataset_name, additional_info=additional_info)
        except UnsupportedFormatError:
            raise
        except InvalidTransformationError:
            raise
        except Exception as e:
            raise FileLoadError(f"Failed to load dataset: {e}")

    def list_datasets(self) -> DatasetListResponse:
        """
        List all currently loaded dataset names.

        Returns:
            DatasetListResponse: Object containing a list of dataset names.
        """
        return DatasetListResponse(datasets=list(self.datasets.keys()))

    def unload_dataset(self, name: str) -> UnloadDatasetResponse:
        """
        Unload a dataset from memory.

        Args:
            name (str): Name of the dataset to unload.

        Returns:
            UnloadDatasetResponse: Confirmation message.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        logging.info(f"Unloading dataset: {name}")
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        self.datasets.pop(name)
        return UnloadDatasetResponse(message=f"Dataset '{name}' unloaded.")

    def reset_state(self) -> StateResetResponse:
        """
        Reset the state by clearing all loaded datasets.

        Returns:
            StateResetResponse: Confirmation message.
        """
        logging.info("Resetting state: clearing all datasets")
        self.datasets.clear()
        return StateResetResponse(message="All datasets cleared.")

    def get_state_metadata(self) -> StateMetadataResponse:
        """
        Provide metadata for all loaded datasets (e.g., row and column counts).

        Returns:
            StateMetadataResponse: A dictionary with dataset names and their size info.
        """
        return StateMetadataResponse(
            metadata={k: {"rows": len(v), "columns": len(v.columns)} for k, v in self.datasets.items()}
        )

    def get_schema(self, name: str) -> DatasetSchemaResponse:
        """
        Get the column names and data types of a specific dataset.

        Args:
            name (str): The dataset name.

        Returns:
            DatasetSchemaResponse: A mapping of column names to string type representations.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        return DatasetSchemaResponse(dataschema={col: str(dtype) for col, dtype in df.dtypes.items()})

    def preview_dataset(self, name: str, num_rows: int = 5, include_schema: bool = False) -> DatasetPreviewResponse:
        """
        Preview the first few rows of a dataset.

        Args:
            name (str): The dataset name.
            num_rows (int): How many rows to preview.
            include_schema (bool): Whether to include schema info in the response.

        Returns:
            DatasetPreviewResponse: A preview of the dataset.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        data = df.head(num_rows).values.tolist()
        columns = df.columns.tolist()
        dataschema = {col: str(dtype) for col, dtype in df.dtypes.items()} if include_schema else None
        return DatasetPreviewResponse(columns=columns, data=data, dataschema=dataschema)

    def get_dataset_summary(
        self, name: str, additional_info: Optional[Dict[str, Any]] = None
    ) -> DatasetSummaryResponse:
        """
        Get a high-level summary of a dataset, including its size and memory usage.

        Args:
            name (str): Dataset name.
            additional_info (Optional[Dict[str, Any]]): Additional information to include in the summary.

        Returns:
            DatasetSummaryResponse: Summary statistics for the dataset.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        return DatasetSummaryResponse(
            name=name,
            num_rows=len(df),
            dataschema={col: str(dtype) for col, dtype in df.dtypes.items()},
            num_columns=len(df.columns),
            column_names=list(df.columns),
            memory_usage=str(df.memory_usage(deep=True).sum() / 1_048_576) + " MB",
            additional_info=additional_info if additional_info else None,
        )

    def get_descriptive_statistics(
        self, name: str, columns=None, include_categoricals=True
    ) -> DescriptiveStatsResponse:
        """
        Generate descriptive statistics for numeric and/or categorical columns.

        Args:
            name (str): Dataset name.
            columns (list[str] | None): Subset of columns to include.
            include_categoricals (bool): Whether to include non-numeric column stats.

        Returns:
            DescriptiveStatsResponse: A dictionary of descriptive statistics.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        describe_df = df[columns] if columns else df
        stats = describe_df.describe(include="all" if include_categoricals else ["number"]).to_dict()
        return DescriptiveStatsResponse(stats=stats)

    def get_value_counts(self, name: str, column: str, normalize=False, max_unique_values=50) -> ValueCountsResponse:
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        if column not in df.columns:
            raise ColumnNotFoundError(f"Column '{column}' not found in dataset '{name}'.")
        counts = df[column].value_counts(normalize=normalize).head(max_unique_values).to_dict()
        return ValueCountsResponse(counts=counts)

    def get_correlation(self, name: str, columns=None, method: str = "pearson") -> CorrelationMatrixResponse:
        """
        Compute a correlation matrix for numeric columns in a dataset.

        Args:
            name (str): Dataset name.
            columns (list[str] | None): Optional subset of numeric columns.
            method (str): Correlation method ('pearson', 'spearman', 'kendall').

        Returns:
            CorrelationMatrixResponse: A matrix of pairwise correlation values.

        Raises:
            DatasetNotFoundError: If the dataset does not exist.
        """
        if name not in self.datasets:
            raise DatasetNotFoundError(f"Dataset '{name}' not found. Available datasets: {list(self.datasets.keys())}")
        df = self.datasets[name]
        corr = df[columns] if columns else df.select_dtypes(include="number")
        return CorrelationMatrixResponse(correlation=corr.corr(method=method).to_dict())

    def transform_dataset(self, request: TransformDatasetRequest) -> DatasetSummaryResponse:
        """
        Apply a series of transformations to a dataset.

        This method supports multiple transformation operations that can be chained
        together in a single request. Each transformation is applied sequentially.

        Args:
            request (TransformDatasetRequest): A request object containing:
                - name: Name of the dataset to transform
                - transformations: List of transformations, each either a dictionary or string.
                  String format: "operation:params" where operation is one of:
                    - filter:expression
                    - drop_columns:col1,col2
                    - rename_columns:old1=new1,old2=new2
                    - rename_column:old_name=new_name
                    - ffill:col1,col2 (or ffill:all for all columns)
                    - to_datetime:col1,col2
                    - to_numeric:col1,col2

        Supported transformations:
            filter: Filter rows based on a boolean expression
                {"op": "filter", "expr": "column > 5"}
                or "filter:column > 5"

            drop_columns: Remove specified columns
                {"op": "drop_columns", "columns": ["col1", "col2"]}
                or "drop_columns:col1,col2"

            rename_columns: Rename columns using a mapping
                {"op": "rename_columns", "columns": {"old_name": "new_name"}}
                or "rename_columns:old_name=new_name,other=renamed"

            rename_column: Rename a single column
                {"op": "rename_column", "old_name": "old_col", "new_name": "new_col"}
                or "rename_column:old_col=new_col"

            ffill: Forward fill missing values in specified columns
                {"op": "ffill", "columns": ["col1", "col2"]} (or "columns": "all" for all columns)
                or "ffill:col1,col2" (or "ffill:all" for all columns)

            to_datetime: Convert columns to datetime type
                {"op": "to_datetime", "columns": ["col1", "col2"], "format": "optional_format"}
                or "to_datetime:col1,col2" (format is auto-detected)

            to_numeric: Convert columns to numeric type
                {"op": "to_numeric", "columns": ["col1", "col2"], "errors": "raise|coerce|ignore"}
                or "to_numeric:col1,col2" (errors="coerce" by default)

        Returns:
            DatasetSummaryResponse: Summary of the transformed dataset

        Raises:
            DatasetNotFoundError: If the specified dataset doesn't exist
            InvalidTransformationError: If a transformation is invalid
        """
        logging.info(f"Transforming dataset: {request.name} with {len(request.transformations)} steps")
        if request.name not in self.datasets:
            raise DatasetNotFoundError(
                f"Dataset '{request.name}' not found. Available datasets: {list(self.datasets.keys())}"
            )

        df = self.datasets[request.name]
        for transformation in request.transformations:
            df = self._apply_transformation(df, transformation)

        # Update the transformed dataset
        transformed_name = request.get_xformed_name()
        self.datasets[transformed_name] = df

        return DatasetSummaryResponse(
            name=transformed_name,
            num_rows=len(df),
            num_columns=len(df.columns),
            column_names=list(df.columns),
            dataschema={col: str(dtype) for col, dtype in df.dtypes.items()},
            memory_usage=f"{df.memory_usage(deep=True).sum() / 1024 / 1024:.4f} MB",
        )

    def join_datasets(self, request: JoinDatasetsRequest) -> DatasetSummaryResponse:
        """
        Join two datasets on a specified column using the requested join method.

        Args:
            request (JoinDatasetsRequest): Contains the names of the datasets to join,
                the column to join on, and the join strategy.

        Returns:
            DatasetSummaryResponse: Summary of the resulting joined dataset.

        Raises:
            DatasetNotFoundError: If one or both datasets are not found
            JoinError: If the join operation fails
        """
        logging.info(
            f"Joining datasets: {request.left_name} + {request.right_name} on {request.on} with {request.how} join"
        )
        if request.left_name not in self.datasets or request.right_name not in self.datasets:
            raise DatasetNotFoundError("One or both datasets not found for join operation.")
        left = self.datasets[request.left_name]
        right = self.datasets[request.right_name]
        try:
            joined = left.merge(right, on=request.on, how=request.how)
        except Exception as e:
            raise JoinError(f"Failed to join datasets: {e}")
        name = request.get_joined_name()
        self.datasets[name] = joined
        return self.get_dataset_summary(name)

    def clean_data(self, request: CleanDatasetRequest) -> DatasetSummaryResponse:
        """
        Clean a dataset using common pandas-based strategies.
        The cleaning behavior is controlled by ``request.strategy`` and may include:
            - Dropping rows with missing values (``dropna`` key).
            - Filling missing values with a provided value (``fillna`` key).
            - Dropping duplicate rows (``drop_duplicates`` key).

        The cleaned dataset is stored in ``self.datasets`` under the name returned by
        ``request.get_cleaned_name()``, and a summary of the cleaned dataset is returned.

        Args:
            request (CleanDatasetRequest): Cleaning instructions, including the target
                dataset name and the cleaning strategy to apply.

        Returns:
            DatasetSummaryResponse: Summary of the cleaned dataset.

        Raises:
            DatasetNotFoundError: If the specified dataset does not exist.
            DataCleaningError: If any cleaning operation fails.
        """
        logging.info(f"Cleaning dataset: {request.name} using strategy keys: {list(request.strategy.keys())}")
        if request.name not in self.datasets:
            raise DatasetNotFoundError(
                f"Dataset '{request.name}' not found. Available datasets: {list(self.datasets.keys())}"
            )
        df = self.datasets[request.name]
        strategy = request.strategy
        try:
            if strategy.get("dropna"):
                df = df.dropna()
            if "fillna" in strategy:
                df = df.fillna(strategy["fillna"])
            if strategy.get("drop_duplicates"):
                df = df.drop_duplicates()
        except Exception as e:
            raise DataCleaningError(f"Failed to clean data: {e}")

        # Use the new get_cleaned_name method for consistent naming
        cleaned_name = request.get_cleaned_name()
        self.datasets[cleaned_name] = df
        return self.get_dataset_summary(cleaned_name)

    def execute_query(self, request: QueryExecutionRequest) -> QueryExecutionResponse:
        logging.info(f"Executing query: language={request.query_language}, expr={request.query_string}")
        if request.query_language == "pandas_query":
            if len(request.input_datasets) != 1:
                raise InvalidQueryError("pandas_query supports only one input dataset.")

            alias, dataset_name = next(iter(request.input_datasets.items()))
            if dataset_name not in self.datasets:
                raise DatasetNotFoundError(
                    f"Dataset '{dataset_name}' not found. Available datasets: {list(self.datasets.keys())}"
                )
            df = self.datasets[dataset_name]

            try:
                result = df.query(request.query_string)
            except Exception as e:
                raise InvalidQueryError(f"Failed to evaluate pandas query: {e}")
        elif request.query_language == "sql":
            con = duckdb.connect()
            for alias, dataset_name in request.input_datasets.items():
                if dataset_name not in self.datasets:
                    raise DatasetNotFoundError(
                        f"Dataset '{dataset_name}' not found. Available datasets: {list(self.datasets.keys())}"
                    )
                con.register(alias, self.datasets[dataset_name])

            try:
                result = con.execute(request.query_string).df()
            except Exception as e:
                raise InvalidQueryError(f"Failed to execute SQL query: {e}")
            finally:
                con.close()
        else:
            raise UnsupportedFormatError(f"Unsupported query_language: {request.query_language}")

        # Use the new get_output_dataset_name method when available,
        # otherwise generate a unique name
        name = request.get_output_dataset_name() or f"query_result_{time.time()}"
        self.datasets[name] = result

        return QueryExecutionResponse(
            output_dataset_name=name,
            columns=result.columns.tolist(),
            data=result.head(20).values.tolist(),
            explanation=f"{request.query_language} executed successfully.",
        )

    def _apply_transformation(
        self, df: pd.DataFrame, transformation: Union[dict, str, "BaseTransformation"]
    ) -> pd.DataFrame:
        """
        Apply a single transformation to a dataframe.
        Uses pattern matching to determine transformation type and delegate to appropriate handler.

        Args:
            df: The dataframe to transform
            transformation: A transformation specification, either:
                - A BaseTransformation instance (FilterTransformation, etc.)
                - A dictionary with transformation details
                - A string in "operation:params" format

        Returns:
            The transformed dataframe

        Raises:
            InvalidTransformationError: If the transformation is invalid
        """
        # Use pattern matching to determine transformation type
        match transformation:
            # Handle BaseTransformation model instances
            case transformation if isinstance(transformation, BaseTransformation):
                df = self._apply_transform_from_model(df, transformation)

            # Handle dictionary format
            case transformation if isinstance(transformation, dict):
                df = self._apply_transformation_from_dict(df, transformation)

            # Handle string format
            case transformation if isinstance(transformation, str):
                try:
                    df = self._apply_transformation_from_string(df, transformation)
                except ValueError as e:
                    raise InvalidTransformationError(
                        f"Invalid transformation format: {transformation}. Expected 'operation:params'. {e}"
                    )
                except UndefinedVariableError as e:
                    raise InvalidTransformationError(f"Undefined variable in query: {e}")

            # Handle unsupported formats
            case _:
                raise InvalidTransformationError(
                    "Each transformation must be either a dictionary, a string in 'operation:params' format, "
                    "or a BaseTransformation instance."
                )

        return df

    def _apply_transformation_from_string(self, df, transformation):
        """
        Parse string transformation into a Pydantic model and call _apply_transform_from_model directly.
        Uses pattern matching with match-case for cleaner code structure.

        Format: "operation:params" where operation is the transformation type and
        params contains operation-specific parameters.

        Args:
            df: The dataframe to transform
            transformation: A string in "operation:params" format

        Returns:
            The transformed dataframe

        Raises:
            InvalidTransformationError: If the transformation string format is invalid
        """
        try:
            # Use pattern matching to extract operation and parameters
            match transformation.split(":", 1):
                case [op, params]:
                    # Model to be built based on the operation type
                    model: Optional[BaseTransformation] = None

                    # Convert string format directly to the appropriate Pydantic model using pattern matching
                    match op:
                        case "filter":
                            model = FilterTransformation(op=op, expr=params)

                        case "drop_columns":
                            # Parse and validate comma-separated column names
                            match params.strip():
                                case "" | " ":
                                    raise ValueError("No columns specified for drop_columns")
                                case column_str:
                                    columns = [c.strip() for c in column_str.split(",")]
                                    model = DropColumnsTransformation(op=op, columns=columns)

                        case "rename_columns":
                            # Parse and validate column mappings with nested pattern matching
                            try:
                                col_pairs = [pair.split("=") for pair in params.split(",")]
                                col_map = {}
                                for pair in col_pairs:
                                    match pair:
                                        case [old, new]:
                                            col_map[old.strip()] = new.strip()
                                        case _:
                                            raise ValueError(f"Invalid column mapping: {pair}")
                                model = RenameColumnsTransformation(op=op, columns=col_map)
                            except Exception as e:
                                raise ValueError(f"Invalid rename_columns format: {e}")

                        case "rename_column":
                            # Parse and validate old/new column names with pattern matching
                            match params.split("=", 1):
                                case [old_name, new_name]:
                                    model = RenameColumnTransformation(
                                        op=op, old_name=old_name.strip(), new_name=new_name.strip()
                                    )
                                case _:
                                    raise ValueError("Invalid format for rename_column, expected old_name=new_name")

                        case "ffill":
                            # Parse and validate ffill columns with pattern matching
                            match params.strip():
                                case "all":
                                    model = FFillTransformation(op=op, columns="all")
                                case "":
                                    raise ValueError("No columns specified for ffill")
                                case column_str:
                                    columns = [c.strip() for c in column_str.split(",")]
                                    model = FFillTransformation(op=op, columns=columns)

                        case "to_datetime":
                            # Parse columns for datetime conversion
                            match params.strip().split(","):
                                case []:
                                    raise ValueError("No columns specified for to_datetime")
                                case columns if all(columns):
                                    cleaned_columns = [c.strip() for c in columns]
                                    model = ToDatetimeTransformation(op=op, columns=cleaned_columns)
                                case _:
                                    raise ValueError("Invalid column format for to_datetime")

                        case "to_numeric":
                            # Parse columns for numeric conversion
                            match params.strip().split(","):
                                case []:
                                    raise ValueError("No columns specified for to_numeric")
                                case columns if all(columns):
                                    cleaned_columns = [c.strip() for c in columns]
                                    model = ToNumericTransformation(op=op, columns=cleaned_columns, errors="coerce")
                                case _:
                                    raise ValueError("Invalid column format for to_numeric")

                        case "unique_values":
                            # Parse columns for unique values extraction
                            match params.strip().split(","):
                                case []:
                                    raise ValueError("No columns specified for unique_values")
                                case columns if all(columns):
                                    cleaned_columns = [c.strip() for c in columns]
                                    model = UniqueValuesTransformation(op=op, columns=cleaned_columns)
                                    if "limit" in params:
                                        try:
                                            limit = int(params.split("limit=")[1].strip())
                                            model.limit = limit
                                        except (IndexError, ValueError):
                                            raise ValueError("Invalid limit value for unique_values")

                        case "value_counts":
                            # Parse columns for value counts extraction
                            match params.strip().split(","):
                                case []:
                                    raise ValueError("No columns specified for value_counts")
                                case columns if all(columns):
                                    cleaned_columns = [c.strip() for c in columns]
                                    model = ValueCountsTransformation(op=op, columns=cleaned_columns)
                                    if "max_unique_values" in params:
                                        try:
                                            max_unique_values = int(params.split("max_unique_values=")[1].strip())
                                            model.max_unique_values = max_unique_values
                                        except (IndexError, ValueError):
                                            raise ValueError("Invalid max_unique_values value for value_counts")
                                    if "normalize=true" in params.lower():
                                        model.normalize = True

                        case _:
                            raise InvalidTransformationError(f"Unsupported transformation op: {op}")

                    # Apply the transformation using the model directly
                    return self._apply_transform_from_model(df, model)

                case _:
                    raise ValueError("Transformation must be in format 'operation:params'")

        except ValueError as e:
            raise InvalidTransformationError(
                f"Invalid transformation format: {transformation}. Expected 'operation:params'. {e}"
            )
        except UndefinedVariableError as e:
            raise InvalidTransformationError(f"Undefined variable in query: {e}")

    def _apply_transformation_from_dict(self, df, transformation):
        """
        Convert a dictionary transformation to a Pydantic model and invoke _apply_transform_from_model.
        Uses pattern matching with match-case for cleaner code structure.

        Args:
            df: The dataframe to transform
            transformation: A dictionary specifying the transformation details

        Returns:
            The transformed dataframe

        Raises:
            InvalidTransformationError: If the transformation is invalid or cannot be parsed
        """
        # Extract operation type from the dictionary
        op = transformation.get("op")
        if not op:
            raise InvalidTransformationError("Missing 'op' in transformation dict")

        try:
            # Using nested pattern matching for parameter extraction and validation
            model: Optional[BaseTransformation] = None

            # Match on operation type with nested pattern matching for parameters
            match op:
                case "filter":
                    match transformation:
                        case {"op": "filter", "expr": expr} if expr:
                            model = FilterTransformation(op=op, expr=expr)
                        case _:
                            raise InvalidTransformationError("Missing 'expr' in filter operation.")

                case "drop_columns":
                    match transformation:
                        case {"op": "drop_columns", "columns": cols} if isinstance(cols, list):
                            model = DropColumnsTransformation(op=op, columns=cols)
                        case _:
                            raise InvalidTransformationError("'columns' must be a list for drop_columns.")

                case "rename_columns":
                    match transformation:
                        case {"op": "rename_columns", "columns": col_map} if isinstance(col_map, dict):
                            model = RenameColumnsTransformation(op=op, columns=col_map)
                        case _:
                            raise InvalidTransformationError("'columns' must be a dict for rename_columns.")

                case "rename_column":
                    match transformation:
                        case {"op": "rename_column", "old_name": old_name, "new_name": new_name} if (
                            old_name and new_name
                        ):
                            model = RenameColumnTransformation(op=op, old_name=old_name, new_name=new_name)
                        case _:
                            raise InvalidTransformationError(
                                "Both 'old_name' and 'new_name' are required for rename_column."
                            )

                case "ffill":
                    match transformation:
                        case {"op": "ffill", "columns": "all"}:
                            model = FFillTransformation(op=op, columns="all")
                        case {"op": "ffill", "columns": cols} if isinstance(cols, list):
                            model = FFillTransformation(op=op, columns=cols)
                        case _:
                            raise InvalidTransformationError("'columns' must be a list or 'all' for ffill.")

                case "to_datetime":
                    match transformation:
                        case {"op": "to_datetime", "columns": cols, "format": format_str} if isinstance(cols, list):
                            model = ToDatetimeTransformation(op=op, columns=cols, format=format_str)
                        case {"op": "to_datetime", "columns": cols} if isinstance(cols, list):
                            model = ToDatetimeTransformation(op=op, columns=cols)  # format will default to None
                        case _:
                            raise InvalidTransformationError("'columns' must be a list for to_datetime.")

                case "to_numeric":
                    match transformation:
                        case {"op": "to_numeric", "columns": cols, "errors": errors} if isinstance(cols, list):
                            model = ToNumericTransformation(op=op, columns=cols, errors=errors)
                        case {"op": "to_numeric", "columns": cols} if isinstance(cols, list):
                            model = ToNumericTransformation(op=op, columns=cols)  # errors will default to "coerce"
                        case _:
                            raise InvalidTransformationError("'columns' must be a list for to_numeric.")

                case "unique_values":
                    match transformation:
                        case {"op": "unique_values", "columns": cols} if isinstance(cols, list):
                            model = UniqueValuesTransformation(op=op, columns=cols)
                            if "limit" in transformation:
                                model.limit = transformation["limit"]
                        case _:
                            raise InvalidTransformationError("'columns' must be a list for unique_values.")

                case "value_counts":
                    match transformation:
                        case {"op": "value_counts", "columns": cols} if isinstance(cols, list):
                            model = ValueCountsTransformation(op=op, columns=cols)
                            if "max_unique_values" in transformation:
                                model.max_unique_values = transformation["max_unique_values"]
                            if "normalize" in transformation:
                                model.normalize = transformation["normalize"]
                        case _:
                            raise InvalidTransformationError("'columns' must be a list for value_counts.")
                case _:
                    raise InvalidTransformationError(f"Unsupported transformation op: {op}")

            # Apply the transformation using the model
            return self._apply_transform_from_model(df, model)

        except Exception as e:
            if isinstance(e, InvalidTransformationError):
                raise
            raise InvalidTransformationError(f"Failed to parse transformation dict: {e}")

    def _apply_transform_from_model(self, df, transformation):  # noqa: C901
        """
        Apply a transformation to a dataframe using a Pydantic model.
        Uses pattern matching with match-case for cleaner code structure.

        Args:
            df: The dataframe to transform
            transformation: A BaseTransformation instance (e.g., FilterTransformation)

        Returns:
            The transformed dataframe

        Raises:
            InvalidTransformationError: If the transformation is invalid or unsupported
        """
        # Use pattern matching to handle different transformation types
        match transformation:
            case FilterTransformation(expr=expr):
                try:
                    df = df.query(expr)
                except Exception as e:
                    raise InvalidTransformationError(f"Invalid filter expression: {e}")

            case DropColumnsTransformation(columns=columns):
                df = df.drop(columns=columns, errors="ignore")

            case RenameColumnsTransformation(columns=columns):
                df = df.rename(columns=columns)

            case RenameColumnTransformation(old_name=old_name, new_name=new_name):
                if old_name not in df.columns:
                    raise ColumnNotFoundError(f"Column '{old_name}' not found for rename_column operation.")
                df = df.rename(columns={old_name: new_name})

            case FFillTransformation(columns=columns):
                match columns:
                    case "all":
                        df = df.ffill()
                    case columns if isinstance(columns, list):
                        # Only fill specified columns
                        for col in columns:
                            if col in df.columns:
                                df[col] = df[col].ffill()

            case ToDatetimeTransformation(columns=columns, format=format):
                try:
                    for col in columns:
                        if col in df.columns:
                            df[col] = pd.to_datetime(df[col], format=format)
                except Exception as e:
                    raise InvalidTransformationError(f"Failed to convert to datetime: {e}")

            case ToNumericTransformation(columns=columns, errors=errors):
                match errors:
                    case "raise":
                        # For errors='raise', we need to handle differently to ensure the error is properly caught
                        for col in columns:
                            if col in df.columns:
                                try:
                                    df[col] = pd.to_numeric(df[col], errors="raise")
                                except Exception as e:
                                    raise InvalidTransformationError(f"Failed to convert '{col}' to numeric: {e}")
                    case "coerce" | "ignore" as error_mode:
                        # For 'ignore' and 'coerce' modes
                        for col in columns:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors=error_mode)

            case UniqueValuesTransformation(columns=columns, limit=limit):
                # Transform DataFrame to contain unique values as rows
                result_data = {}
                for col in columns:
                    if col in df.columns:
                        unique_values = df[col].unique().tolist()
                        if limit is not None:
                            unique_values = unique_values[:limit]
                        result_data[col] = unique_values
                df = pd.DataFrame(result_data)

            case ValueCountsTransformation(columns=columns, normalize=normalize, max_unique_values=max_unique_values):
                # Transform DataFrame to contain counts of unique values in specified columns
                result_data = {}
                for col in columns:
                    if col in df.columns:
                        counts = df[col].value_counts(normalize=normalize).head(max_unique_values).to_dict()
                        result_data[col] = counts
                df = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in result_data.items()]))

            case _:
                raise InvalidTransformationError(f"Unsupported transformation op: {transformation.op}")

        return df


class PandasDataAnalyzerResolver(DependencyResolver[DataAnalyzer]):
    """Dependency resolver for PandasDataAnalyzer."""

    def __init__(self):
        super().__init__()

    memoize_resolution = True

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> DataAnalyzer:
        """
        Create a new PandasDataAnalyzer instance for the given guild/agent.
        The instance will be cached and reused for subsequent calls from the
        same agent, but different agents get different instances.

        Args:
            guild_id: The ID of the guild.
            agent_id: The ID of the agent.

        Returns:
            An instance of PandasDataAnalyzer.
        """
        return PandasDataAnalyzer()
