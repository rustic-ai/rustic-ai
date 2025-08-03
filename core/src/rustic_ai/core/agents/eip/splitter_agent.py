from abc import ABC, abstractmethod
from enum import StrEnum
from typing import List, Literal, Optional, Union

from jsonata import Jsonata
from pydantic import BaseModel, Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps
from rustic_ai.core.utils.json_utils import JsonDict


class FormatSelectorStrategies(StrEnum):
    FIXED = "fixed"
    LIST = "list"
    JSONATA = "jsonata"


class FormatSelector(BaseModel):
    strategy: FormatSelectorStrategies  # "fixed", "list", or "jsonata"
    fixed_format: Optional[str] = None
    format_list: Optional[List[str]] = None
    jsonata_expr: Optional[str] = None

    def resolve_formats(self, items: List[JsonDict]) -> List[str]:
        if self.strategy == FormatSelectorStrategies.FIXED:
            if self.fixed_format:
                return [self.fixed_format] * len(items)
            else:
                raise ValueError("fixed format must be specified for FormatSelectorStrategies.Fixed")
        elif self.strategy == FormatSelectorStrategies.LIST:
            if not self.format_list or len(self.format_list) != len(items):
                raise ValueError("Format list length must match split items length.")
            return self.format_list
        elif self.strategy == FormatSelectorStrategies.JSONATA:
            expr = Jsonata(self.jsonata_expr)
            return [expr.evaluate(item) for item in items]
        else:
            raise ValueError(f"Unsupported format strategy: {self.strategy}")


class BaseSplitter(BaseModel, ABC):
    split_type: str

    @abstractmethod
    def split(self, message: Union[str, JsonDict], delimiter: Optional[str] = ",") -> List[JsonDict]:
        pass


class AsIsSplitter(BaseSplitter):
    split_type: Literal["as-is"] = "as-is"

    def split(self, message: Union[str, JsonDict], delimiter: Optional[str] = ",") -> List[JsonDict]:
        if isinstance(message, list):
            return message
        return [message]


class TokenizerSplitter(BaseSplitter):
    split_type: Literal["tokenizer"] = "tokenizer"

    def split(self, message: Union[str, JsonDict], delimiter: Optional[str] = ",") -> List[JsonDict]:
        if not isinstance(message, str):
            raise ValueError("TokenizerSplitter expects a string payload.")
        if delimiter in ("false", "single"):
            return [message]
        return message.split(delimiter)


class JsonataSplitter(BaseSplitter):
    split_type: Literal["jsonata"] = "jsonata"
    expression: str

    def split(self, message: Union[str, JsonDict], delimiter: Optional[str] = ",") -> List[JsonDict]:
        evaluator = Jsonata(self.expression)
        result = evaluator.evaluate(message)
        if isinstance(result, list):
            return result
        elif result is not None:
            return [result]
        return []


class SplitterConf(BaseAgentProps):
    splitter: Union[AsIsSplitter, TokenizerSplitter, JsonataSplitter] = Field(
        default_factory=lambda: AsIsSplitter(), discriminator="split_type"
    )
    format_selector: FormatSelector
    delimiter: Optional[str] = ","
    topics: Optional[List[str]] = Field(default_factory=list)


class SplitterAgent(Agent[SplitterConf]):
    def __init__(self, agent_spec: AgentSpec[SplitterConf]):
        super().__init__(agent_spec)
        self.splitter = agent_spec.props.splitter
        self.delimiter = agent_spec.props.delimiter
        self.format_selector = agent_spec.props.format_selector
        self.topics = agent_spec.props.topics

    @agent.processor(JsonDict)
    def split_and_send(self, ctx: ProcessContext[JsonDict]) -> None:
        # Split the message
        items = self.splitter.split(ctx.payload, delimiter=self.delimiter)

        # Determine formats
        formats = self.format_selector.resolve_formats(items)

        if len(formats) != len(items):
            raise ValueError("Mismatch between split items and format mappings.")

        for item, fmt in zip(items, formats):
            ctx._raw_send(
                priority=ctx.message.priority,
                topics=self.topics,
                payload=item,
                format=fmt,
            )
