from typing import Annotated, Any, List, Literal, Optional, Type, Union, cast

from pydantic import BaseModel, ConfigDict, Field

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    FunctionMessage,
    Models,
    SystemMessage,
    ToolMessage,
    UserMessage,
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


class LiteLLMConf(BaseAgentProps):
    """
    Properties to apply to all LiteLLM calls made by the agent.
    """

    model_config = ConfigDict(extra="ignore")

    model: Annotated[Union[str, Models], Field(examples=["gpt-4-turbo"])]
    """
    ID of the model to use. See the [model endpoint compatibility](/docs/models/model-endpoint-compatibility) table
    for details on which models work with the Chat API.
    """
    stream: Optional[bool] = False
    """
    If set, partial message deltas will be sent, like in ChatGPT. Tokens will be sent as data-only
    [server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#Event_stream_format)
    as they become available, with the stream terminated by a `data: [DONE]` message.
    [Example Python code](https://cookbook.openai.com/examples/how_to_stream_completions).

    """
    # set api_base, api_version, api_key
    base_url: Optional[str] = None
    api_version: Optional[str] = None

    """
    If provided, return a mock completion response for testing or debugging purposes (default is None).
    """

    custom_llm_provider: Optional[str] = None
    """
    Used for Non-OpenAI LLMs, Example usage for bedrock, set model="amazon.titan-tg1-large" and custom_llm_provider="bedrock"
    """

    timeout: Optional[float] = None
    """
    The maximum time in seconds to wait for the completion.
    If the completion is not returned within this time, the request will time out.
    """

    messages: Optional[
        List[
            Union[
                SystemMessage,
                UserMessage,
                AssistantMessage,
                ToolMessage,
                FunctionMessage,
            ]
        ]
    ] = None
    """
    List of messages to send to the model before the prompt.
    These messages will be prependended to the list of messages in the prompt.
    """

    toolset: Optional[ToolsetUnion] = Field(
        default=None, description="Either {'type':'toolset_class', ...} or {'type':'toolspec_list', ...}"
    )
    """
    Toolset is an predefined implementation of Toolset (fully qualified name) or a list of tool
    specifications. Toolset gives a ToolManager which is used to work with tools and parse tool
    calls. The list of ToolSpec is used to create a ToolManager.
    """

    message_memory: Optional[int] = None
    """
    Number of messages to remember in the conversation history.
    """

    filter_attachments: bool = False
    """
    If set to True, attachments will be filtered out from the messages before sending to the model.
    """

    extract_tool_calls: bool = False
    """
    If set to True, the agent will extract tool calls from the model's response and
    publish them as well as chat completion responses.
    """

    skip_chat_response_on_tool_call: bool = False
    """
    If set to True, the agent will skip publishing the chat completion response when the response includes a tool call.
    Only the tool call will be published. This only applies when `extract_tool_calls` is set to True.
    """

    retries_on_tool_parse_error: int = 0
    """
    LLM may return an invalid tool call or with wrong args. In those cases, parsing will fail.
    Number of retries to LLM completion on tool parse error.
    If set to 0, the agent will not retry on tool parse error.
    """

    vertex_location: Optional[str] = None
    """
    Place where vertex model is deployed (us-central1, asia-southeast1, etc.). If None, attempts to use the VERTEXAI_LOCATION environment variable.
    """

    vertex_project: Optional[str] = None
    """
    The Google Cloud project ID. If None, attempts to use the VERTEXAI_PROJECT environment variable.
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
