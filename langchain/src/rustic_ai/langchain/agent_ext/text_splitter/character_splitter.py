from typing import Callable, Literal, Union

from langchain_text_splitters import CharacterTextSplitter
from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.text_splitter import TextSplitter
from rustic_ai.core.utils import JsonDict


class CharacterSplitterConf(BaseModel):
    """
    Configuration for the CharacterSplitter.
    """

    chunk_size: int = 1000
    chunk_overlap: int = 100
    length_function: Callable[[str], int] = len
    keep_separator: Union[bool, Literal["start", "end"]] = False
    add_start_index: bool = False
    strip_whitespace: bool = True
    separator: str = "\n\n"
    is_separator_regex: bool = False


class CharacterSplitter(TextSplitter):
    """
    Character text splitter that splits text into chunks of a specified size.
    """

    def __init__(self, conf: CharacterSplitterConf):
        self.splitter = CharacterTextSplitter(
            separator=conf.separator,
            is_separator_regex=conf.is_separator_regex,
            **conf.model_dump(exclude={"separator", "is_separator_regex"}),
        )

    def split(self, text: str) -> list[str]:
        return self.splitter.split_text(text)


class CharacterSplitterResolver(DependencyResolver[TextSplitter]):
    memoize_resolution: bool = False

    def __init__(self, conf: JsonDict = {}):
        super().__init__()
        splitter_conf = CharacterSplitterConf.model_validate(conf)
        self.splitter = CharacterSplitter(splitter_conf)

    def resolve(self, guild_id: str, agent_id: str) -> TextSplitter:
        return self.splitter
