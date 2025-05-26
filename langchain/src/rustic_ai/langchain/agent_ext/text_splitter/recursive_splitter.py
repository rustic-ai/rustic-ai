from typing import Callable, List, Literal, Optional, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.text_splitter import TextSplitter
from rustic_ai.core.utils import JsonDict


class RecursiveSplitterConf(BaseModel):
    """
    Configuration class for a recursive splitter.

    This class specifies the configuration for a recursive splitting algorithm
    used to divide text into smaller chunks based on specified rules. The class
    allows customization of chunk size, overlap, and other properties that define
    how the splitting process occurs.

    Attributes:
        chunk_size (int): The size of each text chunk.
        chunk_overlap (int): The overlap size between consecutive chunks.
        length_function (Callable[[str], int]): Function to calculate the length
            of a text. Default is the built-in `len` function.
        add_start_index (bool): Indicates whether to include the start index of
            each chunk in the output.
        strip_whitespace (bool): Specifies if leading and trailing whitespaces
            should be removed from chunks.
        separators (List[str]): A list of delimiters or separators to use for
            splitting text.
        keep_separator (Union[bool, Literal["start", "end"]]): Determines whether
            to retain the separator in the resulting chunks, and if so, whether
            to keep it at the start or end of the chunk.
        is_separator_regex (bool): Indicates if the separators provided should
            be treated as regular expressions.
        hf_tokenizer_model (Optional[str]): The name of a Hugging Face tokenizer
            model to be used for token-based splitting, if applicable.
            If specified, the unit for chunk_size is tokens instead of characters
            and tokenizer is used for the length_function
    """

    chunk_size: int = 1000
    chunk_overlap: int = 100
    length_function: Callable[[str], int] = len
    add_start_index: bool = False
    strip_whitespace: bool = True
    separators: List[str] = ["\n\n", "\n", " ", ""]
    keep_separator: Union[bool, Literal["start", "end"]] = True
    is_separator_regex: bool = False
    hf_tokenizer_model: Optional[str] = None


class RecursiveSplitter(TextSplitter):
    """
    Recursive text splitter that splits text into chunks of a specified size.
    """

    def __init__(self, conf: RecursiveSplitterConf):
        if conf.hf_tokenizer_model:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(conf.hf_tokenizer_model)
            self.tokenizer = tokenizer
            self.splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
                tokenizer, **conf.model_dump(exclude={"hf_tokenizer_model", "length_function"})
            )
        else:
            self.splitter = RecursiveCharacterTextSplitter(
                separators=conf.separators,
                is_separator_regex=conf.is_separator_regex,
                keep_separator=conf.keep_separator,
                **conf.model_dump(exclude={"separators", "is_separator_regex", "keep_separator", "hf_tokenizer_model"}),
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
