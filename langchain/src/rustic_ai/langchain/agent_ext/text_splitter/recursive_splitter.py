from typing import Callable, List, Literal, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.text_splitter import TextSplitter
from rustic_ai.core.utils import JsonDict


class RecursiveSplitterConf(BaseModel):
    """
    Configuration for the RecursiveSplitter.
    """

    chunk_size: int = 1000
    chunk_overlap: int = 100
    length_function: Callable[[str], int] = len
    add_start_index: bool = False
    strip_whitespace: bool = True
    separators: List[str] = ["\n\n", "\n", " ", ""]
    keep_separator: Union[bool, Literal["start", "end"]] = True
    is_separator_regex: bool = False


class RecursiveSplitter(TextSplitter):
    """
    Recursive text splitter that splits text into chunks of a specified size.
    """

    def __init__(self, conf: RecursiveSplitterConf):
        self.splitter = RecursiveCharacterTextSplitter(
            separators=conf.separators,
            is_separator_regex=conf.is_separator_regex,
            keep_separator=conf.keep_separator,
            **conf.model_dump(exclude={"separators", "is_separator_regex", "keep_separator"}),
        )

    def split(self, text: str) -> list[str]:
        return self.splitter.split_text(text)


class RecursiveSplitterResolver(DependencyResolver[TextSplitter]):
    memoize_resolution: bool = False

    def __init__(self, conf: JsonDict = {}):
        super().__init__()
        splitter_conf = RecursiveSplitterConf.model_validate(conf)
        self.splitter = RecursiveSplitter(splitter_conf)

    def resolve(self, guild_id: str, agent_id: str) -> TextSplitter:
        return self.splitter
