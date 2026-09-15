"""A ReAct data analyst with explicit Forge-managed dependencies."""

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig

from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency

from .react_toolset import DataAnalystReActToolset


class DataAnalystAgentConfig(ReActAgentConfig):
    """Configuration for the filesystem-bound data analyst."""

    toolset: DataAnalystReActToolset


class DataAnalystAgent(ReActAgent[DataAnalystAgentConfig]):
    """Run the standard ReAct loop against a shared guild filesystem."""

    @processor(
        clz=ChatCompletionRequest,
        depends_on=[
            "llm",
            AgentDependency(
                dependency_key="filesystem",
                guild_level=True,
                required_type="fsspec.implementations.dirfs.DirFileSystem",
            ),
        ],
    )
    def handle_chat_completion_request(
        self,
        ctx: ProcessContext[ChatCompletionRequest],
        llm: LLM,
        filesystem: FileSystem,
    ) -> None:
        self.config.toolset.bind_filesystem(filesystem)
        self._handle_chat_completion_request(ctx, llm)
