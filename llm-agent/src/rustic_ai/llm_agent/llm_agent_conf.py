from enum import Enum
from typing import Optional, Union

from pydantic import ConfigDict, Field
from typing_extensions import Annotated

from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.llm_agent.llm_plugin_mixin import LLMPluginMixin
from rustic_ai.llm_agent.plugins.prompt_generators import PromptGenerator


class Models(str, Enum):
    gpt_5 = "gpt-5"
    gpt_5_chat = "gpt-5-chat"
    gpt_5_mini = "gpt-5-mini"
    gpt_5_nano = "gpt-5-nano"

    gpt_4o = "gpt-4o"
    gpt_4o_mini = "gpt-5-nano"

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


class LLMAgentConfig(BaseAgentProps, LLMPluginMixin):
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

    default_system_prompt: Optional[str] = None
    """
    Default system prompt to use if no other mechanism updates the prompt.
    """

    system_prompt_generator: Optional[PromptGenerator] = Field(discriminator="type", default=None)
    """
    Mechanism to update the system prompt based on messages from other agents messages.
    """

    send_response: bool = True
    """
    Whether to send the original LLM response back to the conversation.
    If False, only the post-processed messages (if any) will be sent back.
    This is useful if the LLM response is only used for tool calls and not for direct responses.
    """

    vertex_location: Optional[str] = None
    """
    Place where vertex model is deployed (us-central1, asia-southeast1, etc.). If None, attempts to use the VERTEXAI_LOCATION environment variable.
    """

    vertex_project: Optional[str] = None
    """
    The Google Cloud project ID. If None, attempts to use the VERTEXAI_PROJECT environment variable.
    """

    # Fields that should not be passed to the LLM
    _non_llm_fields = {
        "max_retries",
        "request_preprocessors",
        "llm_request_wrappers",
        "response_postprocessors",
        "default_system_prompt",
        "system_prompt_generator",
        "send_response",
    }

    def get_llm_params(self) -> dict:
        """
        Get the LLM parameters from the config, excluding non-LLM fields.
        """
        return self.model_dump(exclude={*self._non_llm_fields})
