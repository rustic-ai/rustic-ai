"""
Shared plugin configuration mixin for LLM-based agents.

This module provides the LLMPluginMixin class that contains common plugin
configuration fields used by both LLMAgent and ReActAgent.
"""

from typing import Any, List, Protocol, Type, TypeVar, cast, runtime_checkable

from pydantic import BaseModel, Field, field_serializer, field_validator

from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor

T = TypeVar("T", bound=BaseModel)


def build_plugins(value: Any, base_type: type[T]) -> List[T]:
    """
    Build plugin instances from dict specs or pass through existing instances.

    Accepts:
      - list of dicts/instances (mixed allowed)
      - single dict
      - single instance

    Dict shape: {"kind": "pkg.mod.Class", ...kwargs}
    Instances are kept as-is.

    Args:
        value: The value to coerce into plugin instances
        base_type: The expected base class for the plugins

    Returns:
        List of plugin instances

    Raises:
        TypeError: If a plugin spec is invalid
    """
    if value is None:
        return []

    items = value if isinstance(value, list) else [value]
    out: List[T] = []

    for i, item in enumerate(items):
        # Already constructed instance (programmatic usage)
        if isinstance(item, base_type):
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


@runtime_checkable
class PluginConfigProtocol(Protocol):
    """Protocol for configs that support plugins."""

    request_preprocessors: List[RequestPreprocessor]
    llm_request_wrappers: List[LLMCallWrapper]
    response_postprocessors: List[ResponsePostprocessor]
    max_retries: int


class LLMPluginMixin(BaseModel):
    """
    Mixin class providing plugin configuration for LLM-based agents.

    This mixin provides common plugin fields and their validators/serializers
    that can be inherited by both LLMAgentConfig and ReActAgentConfig.
    """

    request_preprocessors: List[RequestPreprocessor] = Field(default_factory=list)
    """
    0 or more request preprocessors to apply before sending prompts to the LLM.
    The order of preprocessors matters: they are applied in the order they are listed.
    """

    llm_request_wrappers: List[LLMCallWrapper] = Field(default_factory=list)
    """
    0 or more request wrap processors to apply before sending prompts to the LLM
    and after receiving the response from the LLM. The plugin may modify the prompts
    before sending them to the LLM and also act on the response after receiving it.
    The order of wrap processors matters: they are applied in the order they are listed.
    """

    response_postprocessors: List[ResponsePostprocessor] = Field(default_factory=list)
    """
    0 or more response postprocessors to apply after receiving the response from the LLM.
    All the post processors get the response as is and can act on it.
    Any modifications to the response don't have any affect on other post processors
    or the final response.
    """

    max_retries: int = 0
    """
    Maximum number of retries for LLM requests if post processing fails.
    This is useful if the LLM returns a response that can not be processed successfully
    e.g. due to a parsing error in tools response.
    """

    @field_validator("request_preprocessors", mode="before")
    @classmethod
    def _coerce_req(cls, v):
        return build_plugins(v, RequestPreprocessor)

    @field_validator("llm_request_wrappers", mode="before")
    @classmethod
    def _coerce_wrap(cls, v):
        return build_plugins(v, LLMCallWrapper)

    @field_validator("response_postprocessors", mode="before")
    @classmethod
    def _coerce_resp(cls, v):
        return build_plugins(v, ResponsePostprocessor)

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

    def has_plugins(self) -> bool:
        """Check if any plugins are configured."""
        return bool(
            self.request_preprocessors or self.llm_request_wrappers or self.response_postprocessors
        )
