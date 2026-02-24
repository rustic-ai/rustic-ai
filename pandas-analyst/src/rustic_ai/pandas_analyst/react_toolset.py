from typing import Any, Dict, List, Optional
import mimetypes

from fsspec import filesystem as create_filesystem
from pydantic import BaseModel, Field, PrivateAttr

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer import DataAnalyzer, LoadDatasetRequest
from rustic_ai.core.guild.agent_ext.depends.code_execution.data_analyzer.tools import DataAnalystToolset
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset
from .analyzer import PandasDataAnalyzer


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
    filesystem_options: Dict[str, Any] = Field(default_factory=lambda: {"auto_mkdir": True}, description="Filesystem storage options")
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

    def get_toolspecs(self) -> List[ToolSpec]:
        """
        Return the list of tool specifications.
        We reuse the tool specifications from DataAnalystToolset and add load_file.
        """
        base_tools = DataAnalystToolset().get_data_analyst_tools()
        
        load_tool = ToolSpec(
            name="load_file",
            description="Load a file from the filesystem as a dataset for analysis.",
            parameter_class=LoadFileRequest
        )
        
        return base_tools + [load_tool]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by name with the given arguments.
        Delegates to the underlying DataAnalyzer instance.
        """
        if tool_name == "load_file":
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

            media_link = MediaLink(
                url=filename,
                name=filename,
                mimetype=mimetype,
                on_filesystem=True
            )

            request = LoadDatasetRequest(name=name, source=media_link)
            result = self.analyzer.load_dataset(request, self.filesystem)
            return self._format_result(result)
             
        # Map tool names to analyzer methods
        try:
            if tool_name == "preview_dataset":
                result = self.analyzer.preview_dataset(
                    name=args.name,
                    num_rows=args.num_rows,
                    include_schema=args.include_schema
                )
                return self._format_result(result)

            elif tool_name == "summarize_dataset":
                result = self.analyzer.get_dataset_summary(name=args.name)
                return self._format_result(result)

            elif tool_name == "query_dataset":
                result = self.analyzer.execute_query(args)
                return self._format_result(result)

            elif tool_name == "transform_dataset":
                result = self.analyzer.transform_dataset(args)
                return self._format_result(result)

            elif tool_name == "describe_dataset":
                result = self.analyzer.get_descriptive_statistics(
                    name=args.name,
                    columns=args.columns,
                    include_categoricals=args.include_categoricals
                )
                return self._format_result(result)

            elif tool_name == "join_datasets":
                result = self.analyzer.join_datasets(args)
                return self._format_result(result)

            elif tool_name == "list_datasets":
                result = self.analyzer.list_datasets()
                return self._format_result(result)

            elif tool_name == "get_schema":
                result = self.analyzer.get_schema(args.name)
                return self._format_result(result)

            elif tool_name == "clean_dataset":
                result = self.analyzer.clean_data(args)
                return self._format_result(result)

            elif tool_name == "value_counts":
                result = self.analyzer.get_value_counts(
                    name=args.name,
                    column=args.column,
                    normalize=args.normalize,
                    max_unique_values=args.max_unique_values
                )
                return self._format_result(result)

            elif tool_name == "correlation_matrix":
                result = self.analyzer.get_correlation(
                    name=args.name,
                    columns=args.columns,
                    method=args.method
                )
                return self._format_result(result)

            elif tool_name == "ask_user":
                return f"ASK_USER: {args.question}"

            else:
                raise ValueError(f"Unknown tool: {tool_name}")
                
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _format_result(self, result: Any) -> str:
        """Format the result Pydantic model into a string for the LLM."""
        if hasattr(result, "model_dump_json"):
             return result.model_dump_json(indent=2)
        return str(result)
