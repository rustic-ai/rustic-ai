from abc import ABC, abstractmethod
from functools import cached_property
import json
from typing import List, Optional

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionTool,
    SystemMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper


class ToolspecsProvider(BaseModel, ABC):

    kind: Optional[str] = Field(default=None, frozen=True, description="FQCN of the wrap processor class")

    additional_system_prompt: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", f"{self.__class__.__module__}.{self.__class__.__qualname__}")

    @model_validator(mode="after")
    def _enforce_kind_matches_class(self):
        fqcn = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if self.kind and self.kind != fqcn:
            raise ValueError(f"`kind` must be {fqcn!r}, got {self.kind!r}")
        return self

    @abstractmethod
    def get_toolspecs(self) -> List[ToolSpec]:
        pass

    @cached_property
    def toolspecs_by_name(self) -> dict[str, ToolSpec]:
        return {tool.name: tool for tool in self.get_toolspecs()}

    def get_toolspec_by_name(self, name: str) -> Optional[ToolSpec]:
        return self.toolspecs_by_name.get(name, None)

    @cached_property
    def chat_tools(self) -> List[ChatCompletionTool]:
        return [tool.chat_tool for tool in self.get_toolspecs()]


class ToolspecsListProvider(ToolspecsProvider):

    tools: List[ToolSpec] = Field(description="List of ToolSpec objects", min_length=1)

    def get_toolspecs(self) -> List[ToolSpec]:
        return self.tools


class ToolsHelper:

    @staticmethod
    def parse_tool_args(provider: ToolspecsProvider, name: str, args: dict) -> Optional[BaseModel]:
        """
        Parses the arguments for a tool by its name and validates them against the parameter class.
        This method attempts to create an instance of the parameter class using the provided arguments.

        :param tool: The ToolSpec object representing the tool.
        :param name: The name of the tool.
        :param args: A dictionary of arguments to be validated.
        :return: An instance of the parameter class if validation is successful, None otherwise.
        """

        tool = provider.get_toolspec_by_name(name)
        if not tool:
            return None

        return tool.parse_args(args)

    @staticmethod
    def extract_tool_calls(provider: ToolspecsProvider, response: ChatCompletionResponse) -> List[BaseModel]:
        """
        Extract tool calls from the model's response.

        :param response: The ChatCompletionResponse object containing the model's response.
        :return: A list of tool calls extracted from the response.
        """

        tool_calls: List[BaseModel] = []
        for choice in response.choices:
            if choice.message and choice.message.tool_calls:
                calls = choice.message.tool_calls
                for call in calls:
                    name = call.function.name
                    args = json.loads(call.function.arguments)
                    tool = ToolsHelper.parse_tool_args(provider, name, args)

                    if tool:
                        tool_calls.append(tool)

        return tool_calls


class ToolsManagerPlugin(LLMCallWrapper):

    toolset: ToolspecsProvider

    def preprocess(
        self,
        agent,
        ctx,
        request,
        llm,
    ) -> ChatCompletionRequest:
        messages = request.messages
        if messages is None:
            messages = []

        if self.toolset.additional_system_prompt:
            if len(messages) > 0 and messages[0].role == "system":
                # If system prompt already exists, add the additional prompt as a new system message after it.
                messages = [messages[0]] + [SystemMessage(content=self.toolset.additional_system_prompt)] + messages[1:]
            else:
                messages = [SystemMessage(content=self.toolset.additional_system_prompt)] + messages

        tools = self.toolset.chat_tools

        tools = request.tools + tools if request.tools else tools

        request = request.model_copy(update={"tools": tools, "messages": messages})
        return request

    def postprocess(
        self,
        agent,
        ctx,
        final_prompt,
        llm_response,
        llm,
    ) -> Optional[List[BaseModel]]:
        tool_calls = ToolsHelper.extract_tool_calls(self.toolset, llm_response)
        return tool_calls

    @field_validator("toolset", mode="before")
    @classmethod
    def _load_toolset(cls, v):
        if isinstance(v, dict):
            kind = v.get("kind")
            if not kind:
                # Default to list provider if kind is not specified
                toolset_cls = ToolspecsListProvider
            else:
                toolset_cls = get_class_from_name(kind)

            if not issubclass(toolset_cls, ToolspecsProvider):
                raise ValueError(f"Toolset class {toolset_cls} is not a subclass of ToolspecsProvider")
            return toolset_cls.model_validate(v)

        elif isinstance(v, ToolspecsProvider):
            return v

        else:
            raise ValueError("Toolset must be a dict or an instance of ToolspecsProvider")

    @field_serializer("toolset", mode="plain")
    def _serialize_toolset(self, toolset):
        return toolset.model_dump()
