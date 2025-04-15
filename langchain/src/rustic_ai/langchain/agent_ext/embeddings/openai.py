from typing import List, Optional

from langchain_core.embeddings import Embeddings as LangchainEmbeddings
from langchain_openai import OpenAIEmbeddings as LangchainOAIE
from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.embeddings import Embeddings
from rustic_ai.core.utils import JsonDict

DEFAULT_MODEL: str = "text-embedding-ada-002"


class OpenAIEmbeddingConf(BaseModel):
    openai_api_version: Optional[str] = Field(default=None)
    """Automatically inferred from env var `OPENAI_API_VERSION` if not provided."""
    # to support Azure OpenAI Service custom endpoints
    openai_api_base: Optional[str] = Field(default=None)
    """Base URL path for API requests, leave blank if not using a proxy or service
        emulator."""
    # to support Azure OpenAI Service custom endpoints
    openai_api_type: Optional[str] = None
    # to support explicit proxy for OpenAI
    openai_proxy: Optional[str] = None
    embedding_ctx_length: int = 8191
    """The maximum number of tokens to embed at once."""
    openai_api_key: Optional[str] = Field(default=None)
    """Automatically inferred from env var `OPENAI_API_KEY` if not provided."""
    openai_organization: Optional[str] = Field(default=None)
    """Automatically inferred from env var `OPENAI_ORG_ID` if not provided."""


class OpenAIEmbeddings(Embeddings):
    """
    Embeddings backed by Open AI.
    """

    def __init__(self, model: str, deployment: str, conf: OpenAIEmbeddingConf):
        self.oaie = LangchainOAIE(
            model=model,
            deployment=deployment,
            **conf.model_dump(exclude_none=True, exclude_unset=True),
        )

    def embed(self, text: List[str]) -> List[List[float]]:
        return self.oaie.embed_documents(text)

    @property
    def langchain_embeddings(self) -> LangchainEmbeddings:
        return self.oaie


class OpenAIEmbeddingsResolver(DependencyResolver[Embeddings]):
    memoize_resolution: bool = False

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        deployment: Optional[str] = None,
        model_conf: JsonDict = {},
    ):
        super().__init__()
        mconf = OpenAIEmbeddingConf.model_validate(model_conf)

        self.embedding = OpenAIEmbeddings(
            model=model_name,
            deployment=deployment or model_name,
            conf=mconf,
        )

    def resolve(self, guild_id: str, agent_id: str) -> Embeddings:
        return self.embedding
