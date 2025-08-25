from abc import abstractmethod
from enum import Enum
from typing import List, Literal, Optional

from mistralai import Union
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Annotated

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionTool,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import (
    ToolsManager,
    ToolSpec,
)
from rustic_ai.core.guild.dsl import BaseAgentProps


class ToolsetClassModel(BaseModel):
    type: Literal["toolset_class"] = Field("toolset_class", frozen=True)
    class_path: str  # will be resolved later


class ToolspecListModel(BaseModel):
    type: Literal["toolspec_list"] = Field("toolspec_list", frozen=True)
    tools: List[ToolSpec]


ToolsetUnion = Annotated[Union[ToolsetClassModel, ToolspecListModel], Field(discriminator="type")]


class Models(str, Enum):
    gpt_5 = "gpt-5"
    gpt_5_chat = "gpt-5-chat"
    gpt_5_mini = "gpt-5-mini"
    gpt_5_nano = "gpt-5-nano"

    gpt_4o = "gpt-4o"
    gpt_4o_mini = "gpt-4o-mini"

    gpt_4_1 = "gpt-4.1"
    gpt_4_1_mini = "gpt-4.1-mini"
    gpt_4_1_nano = "gpt-4.1-nano"

    o3 = "o3"
    o3_pro = "o3-pro"
    o3_deep_research = "o3-deep-research"
    o3_mini = "o3-mini"

    o4_mini = "o4-mini"

    gpt_4 = "gpt-4"
    gpt_4_turbo = "gpt-4-turbo"

    gemini_pro = "gemini-pro"
    gemini_2_5_pro = "gemini-2.5-pro"
    gemini_flash = "gemini-flash"
    gemini_2_5_flash = "gemini-2.5-flash"
    gemini_2_5_flash_lite = "gemini-2.5-flash-lite"

    gemini_2_0_flash = "gemini-2.0-flash"
    gemini_2_0_flash_lite = "gemini-2.0-flash-lite"

    gemini_1_5_pro = "gemini-1.5-pro"
    gemini_1_5_flash = "gemini-1.5-flash"

    claude_opus_4_1 = "claude-opus-4-1"
    claude_opus_4_0 = "claude-opus-4-0"
    claude_sonnet_4_0 = "claude-sonnet-4-0"
    claude_sonnet_3_5 = "claude-3-5-sonnet-latest"
    claude_haiku_3_5 = "claude-3-5-haiku-latest"


class LLMAgentConfig(BaseAgentProps):
    """
    Base configuration for LLM agents.
    """

    model_config = ConfigDict(extra="ignore")

    model: Annotated[Union[str, Models], Field(examples=["gpt-5"])]
    """
    ID of the model to use. See the [model endpoint compatibility](/docs/models/model-endpoint-compatibility) table
    for details on which models work with the Chat API.
    """

    base_url: Optional[str] = None
    """Base URL for the LLM API."""

    api_version: Optional[str] = None
    """Version for the LLM API."""

    custom_llm_provider: Optional[str] = None
    """Custom LLM provider to use, e.g., 'bedrock' for Amazon Bedrock or 'vertex' for Google Vertex AI."""

    timeout: Optional[float] = None
    """
    Timeout for the LLM API requests.
    If the completion takes longer than this time, the request will be aborted.
    """

    tools: List[ChatCompletionTool] = []
    """
    List of LLM tools for the agent.
    """

    @abstractmethod
    def get_llm_params(self) -> dict:
        pass

    def get_tools_manager(self) -> Optional[ToolsManager]:
        """
        Returns the tools manager for the agent.
        """
        return None
