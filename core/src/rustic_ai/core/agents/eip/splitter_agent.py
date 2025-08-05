from abc import ABC, abstractmethod
from typing import List, Literal, Union

from jsonata import Jsonata
from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps
from rustic_ai.core.utils.json_utils import JsonDict

# Format selectors


class BaseFormatSelector(BaseModel):
    strategy: str

    @abstractmethod
    def get_formats(self, elements: List[JsonDict]) -> List[str]:
        pass


class FixedFormatSelector(BaseFormatSelector):
    strategy: Literal["fixed"] = "fixed"
    fixed_format: str

    def get_formats(self, elements) -> List[str]:
        return [self.fixed_format] * len(elements)


class ListFormatSelector(BaseFormatSelector):
    strategy: Literal["list"] = "list"
    format_list: List[str]

    def get_formats(self, elements) -> List[str]:
        return self.format_list


class DictFormatSelector(BaseFormatSelector):
    strategy: Literal["dict"] = "dict"
    format_dict: dict

    def get_formats(self, elements) -> List[str]:
        return [value for key, value in sorted(self.format_dict.items())]


class JsonataFormatSelector(BaseFormatSelector):
    strategy: Literal["jsonata"] = "jsonata"
    jsonata_expr: str

    def get_formats(self, elements) -> List[str]:
        expr = Jsonata(self.jsonata_expr)
        return [expr.evaluate(item) for item in elements]


# Splitter


class BaseSplitter(BaseModel, ABC):
    split_type: str

    @abstractmethod
    def split(self, payload: Union[str, JsonDict]) -> List[JsonDict]:
        pass


class ListSplitter(BaseSplitter):
    split_type: Literal["list"] = "list"
    field_name: str

    def split(self, payload: JsonDict) -> List[JsonDict]:
        if isinstance(payload[self.field_name], list):
            return payload[self.field_name]
        return [payload[self.field_name]]


class DictSplitter(BaseSplitter):
    split_type: Literal["dict"] = "dict"

    def split(self, payload: JsonDict) -> List[JsonDict]:
        return [value for key, value in sorted(payload.items())]


class StringSplitter(BaseSplitter):
    split_type: Literal["string"] = "string"
    field_name: str
    delimiter: str = Field(default=",")

    def split(self, payload: JsonDict) -> List[JsonDict]:
        if not isinstance(payload[self.field_name], str):
            raise ValueError("StringSplitter expects a string payload.")
        return payload[self.field_name].split(self.delimiter)


class JsonataSplitter(BaseSplitter):
    split_type: Literal["jsonata"] = "jsonata"
    expression: str

    def split(self, payload: JsonDict) -> List[JsonDict]:
        evaluator = Jsonata(self.expression)
        result = evaluator.evaluate(payload)
        if isinstance(result, list):
            return result
        elif result is not None:
            return [result]
        return []


class SplitterConf(BaseAgentProps):
    splitter: Union[ListSplitter, StringSplitter, JsonataSplitter, DictSplitter]
    format_selector: Union[FixedFormatSelector, ListFormatSelector, DictFormatSelector, JsonataFormatSelector]


class SplitterAgent(Agent[SplitterConf]):
    def __init__(self, agent_spec: AgentSpec[SplitterConf]):
        super().__init__(agent_spec)
        self.splitter = agent_spec.props.splitter
        self.format_selector = agent_spec.props.format_selector

    @agent.processor(JsonDict)
    def split_and_send(self, ctx: ProcessContext[JsonDict]) -> None:
        try:
            items = self.splitter.split(ctx.payload)
            formats = self.format_selector.get_formats(items)

            if len(formats) != len(items):
                ctx.send_error(
                    ErrorMessage(
                        agent_type=self.get_qualified_class_name(),
                        error_type="LengthMismatch",
                        error_message=f"Number of formats: {len(formats)} is not same as number of items {len(items)}",
                    )
                )
                return

            for item, fmt in zip(items, formats):
                ctx.send_dict(payload=item, format=fmt)
        except Exception as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SplitterError",
                    error_message=str(e),
                )
            )
