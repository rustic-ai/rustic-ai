import mimetypes
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fsspec import filesystem as create_filesystem
from pydantic import BaseModel, Field, PrivateAttr

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer import (
    DataAnalyzer,
    LoadDatasetRequest,
)
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer.models import (
    CorrelationMatrixRequest,
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
from rustic_ai.llm_agent.react.toolset import ReActToolset

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

    This toolset is self-contained and creates its own analyzer and filesystem
    from configuration. It can be used directly with the base ReActAgent.

    When use_guild_filesystem is True (default), the toolset will automatically
    configure its filesystem path to match the guild filesystem structure
    ({base_path}/{org_id}/{guild_id}/GUILD_GLOBAL) when bind_agent_context is called.
    """

    filesystem_base_path: str = Field(default="/tmp", description="Base path for filesystem operations")
    filesystem_protocol: str = Field(default="file", description="Filesystem protocol (e.g., 'file', 's3')")
    filesystem_options: Dict[str, Any] = Field(
        default_factory=lambda: {"auto_mkdir": True}, description="Filesystem storage options"
    )
    use_guild_filesystem: bool = Field(default=True, description="If True, use guild filesystem path structure")

    _analyzer: Optional[DataAnalyzer] = PrivateAttr(default=None)
    _filesystem: Optional[FileSystem] = PrivateAttr(default=None)
    _guild_filesystem_path: Optional[str] = PrivateAttr(default=None)

    @property
    def analyzer(self) -> DataAnalyzer:
        """Lazily initialize the analyzer."""
        if self._analyzer is None:
            self._analyzer = PandasDataAnalyzer()
        return self._analyzer

    @property
    def filesystem(self) -> FileSystem:
        """Lazily initialize the filesystem from config."""
        if self._filesystem is None:
            from fsspec.implementations.dirfs import DirFileSystem

            basefs = create_filesystem(
                self.filesystem_protocol,
                **self.filesystem_options,
            )
            # Use guild filesystem path if configured, otherwise use base path
            path = self._guild_filesystem_path or self.filesystem_base_path
            self._filesystem = DirFileSystem(
                path=path,
                fs=basefs,
            )
        return self._filesystem

    def bind_agent_context(self, org_id: str, guild_id: str, agent_id: str) -> None:
        """
        Configure the filesystem to use the guild filesystem path structure.

        This is called by ReActAgent at the start of processing to provide
        guild context. When use_guild_filesystem is True, the filesystem path
        is constructed as: {filesystem_base_path}/{org_id}/{guild_id}/GUILD_GLOBAL

        Args:
            org_id: The organization ID.
            guild_id: The guild ID.
            agent_id: The agent ID (not used for guild-scoped filesystem).
        """
        if self.use_guild_filesystem:
            # Construct guild filesystem path matching FileSystemResolver convention
            # Guild-scoped filesystems use GUILD_GLOBAL instead of agent_id
            self._guild_filesystem_path = f"{self.filesystem_base_path}/{org_id}/{guild_id}/GUILD_GLOBAL"
            # Reset filesystem so it gets recreated with new path
            self._filesystem = None

    def set_dependencies(self, analyzer: DataAnalyzer, filesystem: FileSystem):
        """
        Inject dependencies after initialization.

        This is kept for backward compatibility but is no longer required.
        The toolset can create its own analyzer and filesystem from config.
        """
        self._analyzer = analyzer
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
        filename = args.filename
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
        if tool_name == "load_file":
            load_args = args if isinstance(args, LoadFileRequest) else LoadFileRequest.model_validate(args)
            return self._load_file(load_args)

        # Map tool names to analyzer methods
        try:
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
                    if isinstance(args, GetSchemaRequest)
                    else GetSchemaRequest.model_validate(args.model_dump() if hasattr(args, "model_dump") else args)
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
                schema_args = (
                    args if isinstance(args, GetSchemaRequest) else GetSchemaRequest.model_validate(args)
                )
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
                    args if isinstance(args, CorrelationMatrixRequest) else CorrelationMatrixRequest.model_validate(args)
                )
                result = self.analyzer.get_correlation(
                    name=corr_args.name, columns=corr_args.columns, method=corr_args.method
                )
                return self._format_result(result)

            elif tool_name == "ask_user":
                ask_args = args if isinstance(args, AskUserRequest) else AskUserRequest.model_validate(args)
                return f"ASK_USER: {ask_args.question}"

            else:
                raise ValueError(f"Unknown tool: {tool_name}")

        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _format_result(self, result: Any) -> str:
        """Format the result Pydantic model into a string for the LLM."""
        if hasattr(result, "model_dump_json"):
            return result.model_dump_json(indent=2)
        return str(result)
