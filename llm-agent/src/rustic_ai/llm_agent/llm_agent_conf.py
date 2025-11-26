from enum import Enum
from typing import Any, List, Optional, Type, TypeVar, Union, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from typing_extensions import Annotated

from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.prompt_generators import PromptGenerator
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor


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


T = TypeVar("T", bound=BaseModel)


def _build_plugins(value: Any, base_type: type[T]) -> List[T]:
    """
    Accepts:
      - list of dicts/instances (mixed allowed)
      - single dict
      - single instance

    Dict shape: {"kind": "pkg.mod.Class", ...kwargs}
    Instances are kept as-is.
    """
    if value is None:
        return []

    items = value if isinstance(value, list) else [value]
    out: List[T] = []

    for i, item in enumerate(items):
        # Already constructed instance (programmatic usage)
        if isinstance(item, base_type):
            # mypy: item is a runtime instance of base_type (a subclass of BaseModel)
            out.append(cast(T, item))
            continue

        # Dict spec with FQCN
        if isinstance(item, dict):
            cls_path = item.get("kind")
            if not cls_path or not isinstance(cls_path, str):
                raise TypeError(f"Plugin spec at index {i} must include string 'kind' (FQCN)")
            cls: Type[Any] = get_class_from_name(cls_path)
            if not issubclass(cls, base_type):
                raise TypeError(f"{cls_path!r} is not a subclass of {base_type.__name__}")
            kwargs = {k: v for k, v in item.items() if k != "kind"}
            instance = cls(**kwargs)
            out.append(cast(T, instance))
            continue

        raise TypeError(
            f"Unsupported plugin spec at index {i}: expected dict or {base_type.__name__} instance; "
            f"got {type(item).__name__}"
        )

    return out


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

    max_retries: int = 0
    """
    Maximum number of retries for LLM requests if post processing fails.
    This is useful if the LLM returns a response that can not be processed successfully
    e.g. due to a parsing error in tools response.
    """

    default_system_prompt: Optional[str] = None
    """
    Default system prompt to use if no other mechanism updates the prompt.
    """

    system_prompt_generator: Optional[PromptGenerator] = Field(discriminator="type", default=None)
    """
    Mechanism to update the system prompt based on messages from other agents messages.
    """

    request_preprocessors: List[RequestPreprocessor] = Field(default_factory=list)
    """
    0 or more request preprocessors to apply before sending prompts to the LLM.
    The order of preprocessors matters: they are applied in the order they are listed.
    """

    llm_request_wrappers: List[LLMCallWrapper] = Field(default_factory=list)
    """
    0 or more request wrap processors to apply before sending prompts to the LLM
    and after receiving the response from the LLM. The plugin may modify the prompts before sending them to the LLM
    and also act on the response after receiving it from the LLM.
    The order of wrap processors matters: they are applied in the order they are listed.
    """

    response_postprocessors: List[ResponsePostprocessor] = Field(default_factory=list)
    """
    0 or more response postprocessors to apply after receiving the response from the LLM.
    All the post processors get the response as is and can act on it.
    Any modifications to the response don't have any affect on other post processors or the final response.
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

    @field_validator("request_preprocessors", mode="before")
    @classmethod
    def _coerce_req(cls, v):
        return _build_plugins(v, RequestPreprocessor)

    @field_validator("llm_request_wrappers", mode="before")
    @classmethod
    def _coerce_wrap(cls, v):
        return _build_plugins(v, LLMCallWrapper)

    @field_validator("response_postprocessors", mode="before")
    @classmethod
    def _coerce_resp(cls, v):
        return _build_plugins(v, ResponsePostprocessor)

    @field_serializer("request_preprocessors", mode="plain")
    def _serialize_preprocessors(self, preprocessors):
        """Ensure subclass fields are preserved during serialization."""
        return [p.model_dump(exclude_none=True) for p in preprocessors]

    @field_serializer("llm_request_wrappers", mode="plain")
    def _serialize_wrappers(self, wrappers):
        """Ensure subclass fields are preserved during serialization."""
        return [w.model_dump(exclude_none=True) for w in wrappers]

    @field_serializer("response_postprocessors", mode="plain")
    def _serialize_postprocessors(self, postprocessors):
        """Ensure subclass fields are preserved during serialization."""
        return [p.model_dump(exclude_none=True) for p in postprocessors]

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
