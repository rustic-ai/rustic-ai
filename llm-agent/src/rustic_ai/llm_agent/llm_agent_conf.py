from abc import abstractmethod
from enum import Enum
from typing import Any, List, Literal, Optional, Type, cast

from mistralai import Union
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Annotated

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionTool,
    FunctionMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
    WebSearchOptions,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import (
    Toolset,
    ToolsManager,
    ToolSpec,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.basic_class_utils import get_class_from_name


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


class LLMConfigBase(BaseAgentProps):
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

    @abstractmethod
    def get_prefix_messages(
        self,
    ) -> List[
        Union[
            SystemMessage,
            UserMessage,
            AssistantMessage,
            ToolMessage,
        ]
    ]:
        pass


class LLMAgentConfig(BaseAgentProps):
    """
    Configuration for the LLM Agent.
    """

    model_config = ConfigDict(extra="ignore")

    stream: Optional[bool] = False
    """
    Whether to stream the responses from the LLM.
    """

    stream_options: Optional[dict] = None
    """
    A dictionary containing options for the streaming response. Only set this when you set stream: true.
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

    prefix_messages: Optional[
        List[
            Union[
                SystemMessage,
                UserMessage,
                AssistantMessage,
                ToolMessage,
                FunctionMessage,
            ]
        ]
    ] = Field(None, description="List of messages to prefix the conversation with.")
    """
    List of messages to prefix the conversation with. These messages will be sent before the user input.
    """

    toolset: Optional[ToolsetUnion] = Field(
        None,
        description="Toolset to use for the agent. Can be a class path or a list of tool specifications.",
    )
    """
    Toolset to use for the agent. Can be a class path or a list of tool specifications.
    """

    message_memory: Optional[int] = Field(None, description="Size of the message memory for the agent.")
    """
    Size of the message memory for the agent.
    """

    filter_attachments: bool = Field(True, description="Whether to filter attachments from messages.")
    """
    Whether to filter attachments from messages. If True, attachments will not be included in the messages sent to the LLM.
    Since our messages will have MediaLinks on storage by default, we enable this by default.
    Look at `keep_http_attachments`, it will keep the http attachments by default.
    """

    keep_http_attachments: bool = Field(False, description="Whether to keep HTTP attachments in messages.")
    """
    Whether to keep HTTP attachments in messages. If False, HTTP attachments will be filtered in the messages sent to the LLM.
    Most LLM APIs do not support HTTP attachments, so this is disabled by default.
    """

    extract_attachments: bool = Field(False, description="Whether to extract attachments from messages.")
    """
    Whether to extract attachments from messages.
    If True, attachments will be extracted from the message and sent on message bus to be processed by other agents.
    If this is true and there are attachments, the message will not be sent to the LLM, but will be placed in session_state.
    The routes from attachment handling agents, should bring the message back to LLM Agent if it has to be sent to the LLM.
    """

    attach_medialink_content: bool = Field(
        False, description="Whether to replace media links with URLs in the messages."
    )
    """
    Whether to send MediaLink content to the LLM.
    Some LLMs allow uploading the file, in which case we should upload the file.
    In most cases we should read the file content and send it as text.
    In case LLMs have a vision endpoint (support image input) or audio endpoint (support audio input), we should send the file as is
    to the correct endpoint i.e. as image or audio attachment.
    Some newer LLMs support PDF files as well, as those should be sent as file attachments when supported.
    NOTE: This is currently not implemented.
    """

    extract_tool_calls: bool = Field(False, description="Whether to extract tool calls from the model's response.")
    """
    Whether to extract tool calls from the model's response.
    If True, tool calls will be extracted from the model's response and and publish them as individual messages.
    Note: The agent will still send the complete response as well.
    """

    skip_chat_response_on_tool_call: bool = Field(
        False,
        description="Whether to skip publishing the chat completion response when the response includes a tool call.",
    )
    """
    Whether to skip publishing the chat completion response when the response includes a tool call.
    """

    retries_on_tool_parse_error: int = Field(
        0,
        description="Number of retries on tool parse error.",
    )
    """
    Number of retries on tool parse error. This is in case the LLM returns an invalid tool call or wrong args.
    If set to 0, the agent will not retry the tool call and will send an error message instead.
    """

    get_history_from_context: bool = Field(False, description="Whether to get the message history from the context.")
    """
    Whether to get the enriched history from the context.
    If True, the agent will include the enriched message history in the context sent to the LLM.
    """

    use_agent_state_for_memory: Optional[bool] = Field(
        None, description="Should the agent use its state for memory instead of in memory queue?"
    )
    """
    Should the agent use its state for memory instead of in memory queue? If None, it will use in memory queue.
    If True, it will use agent state for memory.
    Note: this setting depends on State management in the guild.
    """

    use_guild_state_for_memory: Optional[str] = Field(
        None,
        description="If set, the agent will use the specified guild state key for memory instead of in memory queue.",
    )
    """
    If set to a string, the agent will use the specified guild state key for memory instead of in memory queue or agent state.
    Note: this setting depends on State management in the guild.
    """

    reasoning_effort: Annotated[Optional[Literal["low", "medium", "high"]], Field(None)] = None
    """
    The number of reasoning tokens to generate. This can be overridden per message.
    """

    web_search_options: Optional[WebSearchOptions] = None
    """
    Options for the web search tool if using provider `web_search`.
    """

    def get_tools_manager(self) -> Optional[ToolsManager]:
        """
        Returns the tools manager for the agent.
        If the toolset is a list of ToolSpec, it will create a new ToolsManager instance.
        If the toolset is a Toolset class, it will return the ToolsManager instance from the Toolset class.
        """
        if self.toolset is None:
            return None

        if isinstance(self.toolset, ToolsetClassModel):
            cls = self.path_to_cls(self.toolset.class_path)  # resolve string → subclass
            return cls.toolsmanager()  # class method supplied by Toolset

        if isinstance(self.toolset, ToolspecListModel):
            return ToolsManager(self.toolset.tools)

        raise TypeError("Unsupported toolset variant")

    @staticmethod
    def path_to_cls(value: str) -> Type[Toolset]:
        """
        Converts a string representation of a class back to the class itself.
        """
        if isinstance(value, type) and issubclass(value, Toolset):
            return cast(Type[Toolset], value)

        if not isinstance(value, str):
            raise TypeError(
                "parameter_class must be a fully-qualified string or a "
                "subclass of Toolset; got "
                f"{type(value).__name__}"
            )

        module_path, _, qualname = value.rpartition(".")
        if not module_path:
            raise ValueError(f"Not a fully-qualified path: {value!r}")

        mod = get_class_from_name(module_path)
        obj: Any = mod

        for attr in qualname.split("."):
            obj = getattr(obj, attr)

        if not isinstance(obj, type):
            raise TypeError(f"{value!r} does not resolve to a class")

        if not issubclass(obj, Toolset):
            raise TypeError(f"{value!r} is not a Toolset")

        return cast(Type[Toolset], obj)

    def get_llm_params(self) -> dict:
        """
        Returns the LLM parameters for the agent.
        """
        return self.model_dump(
            exclude_none=True,
            exclude_unset=True,
            exclude={
                "attach_medialink_content",
                "message_memory",
                "toolset",
                "filter_attachments",
                "extract_tool_calls",
                "skip_chat_response_on_tool_call",
                "retries_on_tool_parse_error",
            },
        )
