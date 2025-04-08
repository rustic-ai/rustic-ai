from typing import Annotated, List, Optional, Union

from pydantic import ConfigDict, Field

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionTool,
    FunctionMessage,
    Models,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import BaseAgentProps


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

    tools: Optional[List[ChatCompletionTool]] = None
    """
    List of tools to enable for completion.
    These tools will be appended to the list of tools in the prompt.
    """

    message_memory: Optional[int] = None
    """
    Number of messages to remember in the conversation history.
    """
