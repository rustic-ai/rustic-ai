from abc import ABC, abstractmethod
from functools import cached_property
import json
from typing import Annotated, Any, List, Optional, Type, cast

from pydantic import BaseModel, BeforeValidator, PlainSerializer

from rustic_ai.core.utils.basic_class_utils import get_class_from_name

from .....utils import ModelClass
from ..llm.models import (
    ChatCompletionResponse,
    ChatCompletionTool,
    FunctionObject,
    ToolType,
)


class ToolSpec(BaseModel):
    """
    Specification for a tool that can be called by the model.
    """

    name: str
    """
    The name of the tool. This should be unique and descriptive.
    """

    description: str
    """
    A brief description of the tool's purpose and functionality.
    """

    parameter_class: ModelClass
    """
    The Pydantic model class that defines the parameters for the tool.
    This class should inherit from pydantic.BaseModel.
    """

    @cached_property
    def chat_tool(self) -> ChatCompletionTool:
        """
        Returns a ChatCompletionTool object that can be used in the chat model.
        This method constructs the tool object using the name, description,
        and parameters defined in the tool specification.

        :return: A ChatCompletionTool object.
        """

        return ChatCompletionTool(
            type=ToolType.function,
            function=FunctionObject(
                name=self.name,
                description=self.description,
                parameters=self.parameter_class.model_json_schema(),
            ),
        )

    def parse_args(self, args: dict) -> Optional[BaseModel]:
        """
        Parses the arguments for the tool and validates them against the parameter class.
        This method attempts to create an instance of the parameter class using the provided arguments.

        :param args: A dictionary of arguments to be validated.
        :return: An instance of the parameter class if validation is successful, None otherwise.
        """
        return self.parameter_class.model_validate(args)


class ToolsManager:
    """
    Manages a set of tools that can be called by the model.
    This class provides methods to retrieve tools by name, parse arguments for tools,
    and extract tool calls from the model's response.
    """

    def __init__(self, tools: List[ToolSpec]):
        """
        Initializes the ToolsManager with a list of tool specifications.

        :param tools: A list of ToolSpec objects that define the tools.
        """
        self.tool_specs = tools
        self.tools_by_name = {tool.name: tool for tool in tools}

    @cached_property
    def tool_names(self) -> List[str]:
        """
        Returns a list of tool names managed by this ToolsManager.
        """

        return [tool.name for tool in self.tool_specs]

    @cached_property
    def tools(self) -> List[ChatCompletionTool]:
        """
        Returns a list of ChatCompletionTool objects managed by this ToolsManager.
        """

        return [tool.chat_tool for tool in self.tool_specs]

    @cached_property
    def tool_count(self) -> int:
        """
        Returns the number of tools managed by this ToolsManager.
        """

        return len(self.tool_specs)

    def get_tool_by_name(self, name: str) -> Optional[ToolSpec]:
        """
        Retrieves a tool specification by its name.

        :param name: The name of the tool to retrieve.
        :return: The ToolSpec object if found, None otherwise.
        """

        return self.tools_by_name.get(name)

    def parse_tool_args(self, name: str, args: dict) -> Optional[BaseModel]:
        """
        Parses the arguments for a tool by its name and validates them against the parameter class.
        This method attempts to create an instance of the parameter class using the provided arguments.

        :param name: The name of the tool.
        :param args: A dictionary of arguments to be validated.
        :return: An instance of the parameter class if validation is successful, None otherwise.
        """

        tool = self.get_tool_by_name(name)
        if tool:
            return tool.parse_args(args)
        return None

    def extract_tool_calls(self, response: ChatCompletionResponse) -> List[BaseModel]:
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
                    self.parse_tool_args(name, args)

        return tool_calls


class Toolset(ABC):

    @classmethod
    @abstractmethod
    def toolsmanager(cls) -> ToolsManager:
        """
        Returns the ToolsManager instance for this tool set.
        """

        pass


def cls_to_path(cls: Type[Toolset]) -> str:
    """
    Converts a class to its string representation.
    This is used for serialization and deserialization of the class.

    :param cls: The class to convert.
    :return: The string representation of the class.
    """

    return f"{cls.__module__}.{cls.__name__}"


def path_to_cls(value: Any) -> Type[Toolset]:
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


ToolsetClass = Annotated[
    Type[Toolset],
    PlainSerializer(cls_to_path, return_type=str),
    BeforeValidator(path_to_cls),
]
