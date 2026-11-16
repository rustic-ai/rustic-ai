import json
import mimetypes
from pathlib import PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, List, Optional
from urllib.parse import unquote, urlsplit

from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from pydantic import BaseModel, Field, PrivateAttr

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer import (
    DataAnalyzer,
    DataAnalyzerError,
    DatasetNotFoundError,
    FileLoadError,
    InvalidQueryError,
    InvalidTransformationError,
    LoadDatasetRequest,
    UnsupportedFormatError,
)
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer.models import (
    CorrelationMatrixRequest,
    GetDatasetSummaryRequest,
    GetDescriptiveStatisticsRequest,
    GetSchemaRequest,
    PreviewDatasetRequest,
    ValueCountsRequest,
)
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer.tools import (
    AskUserRequest,
    DataAnalystToolset,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import (
    ReActToolOutcome,
    ReActToolset,
    ToolOutcomeDisposition,
)

from .analyzer import PandasDataAnalyzer

if TYPE_CHECKING:
    from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
    from rustic_ai.llm_agent.plugins.tool_call_wrapper import ToolCallWrapper


class LoadFileRequest(BaseModel):
    """Request to load a file as a dataset."""

    filename: str = Field(description="Path to the file to load.")
    dataset_name: Optional[str] = Field(default=None, description="Name to give the dataset. Defaults to filename.")


class DataAnalystReActToolset(ReActToolset):
    """
    A ReActToolset that wraps a DataAnalyzer to provide data analysis tools
    compatible with the ReActAgent loop.

    The owning DataAnalystAgent injects Forge-resolved dependencies. The toolset
    never constructs paths outside that scoped filesystem.
    """

    _analyzer: Optional[DataAnalyzer] = PrivateAttr(default=None)
    _filesystem: Optional[FileSystem] = PrivateAttr(default=None)

    @property
    def analyzer(self) -> DataAnalyzer:
        """Lazily initialize the analyzer."""
        if self._analyzer is None:
            self._analyzer = PandasDataAnalyzer()
        return self._analyzer

    @property
    def filesystem(self) -> FileSystem:
        """Return the injected guild-scoped filesystem."""
        if self._filesystem is None:
            raise RuntimeError("The guild filesystem dependency is unavailable.")
        return self._filesystem

    def bind_filesystem(self, filesystem: FileSystem) -> None:
        """Bind Forge's guild filesystem for the synchronous data analyzer."""
        if isinstance(filesystem.fs, AsyncFileSystemWrapper):
            filesystem = FileSystem(
                path=filesystem.path,
                fs=filesystem.fs.sync_fs,
                asynchronous=False,
            )
        self._filesystem = filesystem

    def validate_plugins(
        self,
        request_preprocessors: List["RequestPreprocessor"],
        tool_wrappers: List["ToolCallWrapper"],
    ) -> None:
        """
        Validate that required plugins are configured for this toolset.

        DataAnalystReActToolset requires FileUrlExtractorPreprocessor to be
        configured because:
        - The load_file tool expects filenames (e.g., 'sales.csv'), not full paths
        - When users upload files via the UI, they arrive as FileContentParts
          with full filesystem paths
        - FileUrlExtractorPreprocessor extracts filenames from FileContentParts
          and adds a system message informing the LLM about available files

        Without this preprocessor, the LLM won't know about uploaded files
        and cannot use the load_file tool correctly.

        Args:
            request_preprocessors: The configured request preprocessors.
            tool_wrappers: The configured tool wrappers.

        Raises:
            ValueError: If FileUrlExtractorPreprocessor is not configured.
        """
        from .file_url_preprocessor import FileUrlExtractorPreprocessor

        has_file_url_preprocessor = any(isinstance(p, FileUrlExtractorPreprocessor) for p in request_preprocessors)

        if not has_file_url_preprocessor:
            raise ValueError(
                f"{self.__class__.__name__} requires FileUrlExtractorPreprocessor to be configured.\n\n"
                "The load_file tool expects filenames (e.g., 'sales.csv'), but uploaded files "
                "arrive as FileContentParts with full paths. FileUrlExtractorPreprocessor "
                "extracts these filenames and informs the LLM about available files.\n\n"
                "Add FileUrlExtractorPreprocessor to request_preprocessors in your agent configuration:\n\n"
                '    "request_preprocessors": [\n'
                '        {"kind": "rustic_ai.pandas_analyst.file_url_preprocessor.FileUrlExtractorPreprocessor"}\n'
                "    ]"
            )

    def get_toolspecs(self) -> List[ToolSpec]:
        """
        Return the list of tool specifications.
        We reuse the tool specifications from DataAnalystToolset and add load_file.
        """
        base_tools = DataAnalystToolset().get_data_analyst_tools()

        load_tool = ToolSpec(
            name="load_file",
            description="Load a file from the filesystem as a dataset for analysis.",
            parameter_class=LoadFileRequest,
        )

        return base_tools + [load_tool]

    def _load_file(self, args: LoadFileRequest) -> str:
        """Helper method to load a file as a dataset."""
        filename = self._safe_relative_path(args.filename)
        name = args.dataset_name if args.dataset_name else filename.split("/")[-1].split(".")[0]

        # Guess mimetype
        mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            if filename.endswith(".csv"):
                mimetype = "text/csv"
            elif filename.endswith(".json"):
                mimetype = "application/json"
            elif filename.endswith(".parquet"):
                mimetype = "application/x-parquet"

        media_link = MediaLink(url=filename, name=filename, mimetype=mimetype, on_filesystem=True)

        request = LoadDatasetRequest(name=name, source=media_link)
        result = self.analyzer.load_dataset(request, self.filesystem)
        return self._format_result(result)

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by name with the given arguments.
        Delegates to the underlying DataAnalyzer instance.
        """
        try:
            if tool_name == "load_file":
                load_args = args if isinstance(args, LoadFileRequest) else LoadFileRequest.model_validate(args)
                return self._load_file(load_args)

            # Map tool names to analyzer methods
            if tool_name == "preview_dataset":
                preview_args = (
                    args if isinstance(args, PreviewDatasetRequest) else PreviewDatasetRequest.model_validate(args)
                )
                result = self.analyzer.preview_dataset(
                    name=preview_args.name, num_rows=preview_args.num_rows, include_schema=preview_args.include_schema
                )
                return self._format_result(result)

            elif tool_name == "summarize_dataset":
                summary_args = (
                    args
                    if isinstance(args, GetDatasetSummaryRequest)
                    else GetDatasetSummaryRequest.model_validate(
                        args.model_dump() if hasattr(args, "model_dump") else args
                    )
                )
                result = self.analyzer.get_dataset_summary(name=summary_args.name)
                return self._format_result(result)

            elif tool_name == "query_dataset":
                result = self.analyzer.execute_query(args)
                return self._format_result(result)

            elif tool_name == "transform_dataset":
                result = self.analyzer.transform_dataset(args)
                return self._format_result(result)

            elif tool_name == "describe_dataset":
                describe_args = (
                    args
                    if isinstance(args, GetDescriptiveStatisticsRequest)
                    else GetDescriptiveStatisticsRequest.model_validate(args)
                )
                result = self.analyzer.get_descriptive_statistics(
                    name=describe_args.name,
                    columns=describe_args.columns,
                    include_categoricals=describe_args.include_categoricals,
                )
                return self._format_result(result)

            elif tool_name == "join_datasets":
                result = self.analyzer.join_datasets(args)
                return self._format_result(result)

            elif tool_name == "list_datasets":
                result = self.analyzer.list_datasets()
                return self._format_result(result)

            elif tool_name == "get_schema":
                schema_args = args if isinstance(args, GetSchemaRequest) else GetSchemaRequest.model_validate(args)
                result = self.analyzer.get_schema(schema_args.name)
                return self._format_result(result)

            elif tool_name == "clean_dataset":
                result = self.analyzer.clean_data(args)
                return self._format_result(result)

            elif tool_name == "value_counts":
                vc_args = args if isinstance(args, ValueCountsRequest) else ValueCountsRequest.model_validate(args)
                result = self.analyzer.get_value_counts(
                    name=vc_args.name,
                    column=vc_args.column,
                    normalize=vc_args.normalize,
                    max_unique_values=vc_args.max_unique_values,
                )
                return self._format_result(result)

            elif tool_name == "correlation_matrix":
                corr_args = (
                    args
                    if isinstance(args, CorrelationMatrixRequest)
                    else CorrelationMatrixRequest.model_validate(args)
                )
                result = self.analyzer.get_correlation(
                    name=corr_args.name, columns=corr_args.columns, method=corr_args.method
                )
                return self._format_result(result)

            elif tool_name == "ask_user":
                ask_args = args if isinstance(args, AskUserRequest) else AskUserRequest.model_validate(args)
                question = " ".join(ask_args.question.split())[:500]
                return self._outcome_result(
                    ToolOutcomeDisposition.CLARIFICATION_REQUIRED,
                    "clarification_required",
                    question or "Please clarify the data-analysis request.",
                )

            else:
                raise ValueError(f"Unknown tool: {tool_name}")

        except Exception as error:
            return self._failure_result(error)

    def _failure_result(self, error: Exception) -> str:
        """Map tool failures to bounded outcomes without exposing exception text."""
        if isinstance(error, UnsafeGuildPathError):
            return self._outcome_result(
                ToolOutcomeDisposition.TERMINAL_ERROR,
                "unsafe_file_path",
                "The requested file path is outside the guild filesystem.",
            )
        if isinstance(error, DatasetNotFoundError):
            available = ", ".join(sorted(self.analyzer.datasets)) or "none"
            return self._outcome_result(
                ToolOutcomeDisposition.RETRYABLE_ERROR,
                "dataset_not_found",
                f"The dataset was not found. Available datasets: {available}.",
            )
        if isinstance(error, InvalidQueryError):
            return self._outcome_result(
                ToolOutcomeDisposition.RETRYABLE_ERROR,
                "invalid_query",
                "The query was invalid. Check its dataset aliases, column names, and syntax.",
            )
        if isinstance(error, (FileLoadError, FileNotFoundError, UnsupportedFormatError)):
            return self._outcome_result(
                ToolOutcomeDisposition.RETRYABLE_ERROR,
                "file_load_failed",
                "The file could not be loaded. Check the listed guild filename and supported format.",
            )
        if isinstance(error, (DataAnalyzerError, InvalidTransformationError, ValueError)):
            return self._outcome_result(
                ToolOutcomeDisposition.RETRYABLE_ERROR,
                "invalid_data_operation",
                "The data operation was invalid. Check the dataset and column names and correct the operation.",
            )
        return self._outcome_result(
            ToolOutcomeDisposition.TERMINAL_ERROR,
            "unexpected_data_failure",
            "The data operation failed safely.",
        )

    def interpret_result(self, tool_name: str, args: BaseModel, result: str) -> ReActToolOutcome:
        """Interpret the toolset's private, structured outcome marker."""
        del tool_name, args
        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return ReActToolOutcome(disposition=ToolOutcomeDisposition.SUCCESS)
        if not isinstance(payload, dict) or payload.get("_rustic_data_analyst_outcome") is not True:
            return ReActToolOutcome(disposition=ToolOutcomeDisposition.SUCCESS)
        return ReActToolOutcome(
            disposition=ToolOutcomeDisposition(payload["disposition"]),
            code=payload.get("code"),
            message=payload.get("message"),
        )

    @staticmethod
    def _outcome_result(disposition: ToolOutcomeDisposition, code: str, message: str) -> str:
        return json.dumps(
            {
                "_rustic_data_analyst_outcome": True,
                "disposition": disposition.value,
                "code": code,
                "message": message,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _safe_relative_path(value: str) -> str:
        raw = value.strip()
        if not raw or any(ord(character) < 32 for character in raw):
            raise UnsafeGuildPathError
        decoded = unquote(raw)
        if unquote(decoded) != decoded:
            raise UnsafeGuildPathError
        if urlsplit(decoded).scheme or decoded.startswith(("/", "\\", "//")) or "\\" in decoded:
            raise UnsafeGuildPathError
        if any(part in ("", ".", "..") for part in decoded.split("/")):
            raise UnsafeGuildPathError
        posix_path = PurePosixPath(decoded)
        windows_path = PureWindowsPath(decoded)
        if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise UnsafeGuildPathError
        if any(part in ("", ".", "..") for part in posix_path.parts):
            raise UnsafeGuildPathError
        return posix_path.as_posix()

    def _format_result(self, result: Any) -> str:
        """Format the result Pydantic model into a string for the LLM."""
        if hasattr(result, "model_dump_json"):
            return result.model_dump_json(indent=2)
        return str(result)


class UnsafeGuildPathError(ValueError):
    """A requested path was not confined to the injected guild filesystem."""
