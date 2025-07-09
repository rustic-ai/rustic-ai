from typing import List, Optional

from google.genai.types import EmbedContentConfig, Part
from pydantic.config import JsonDict

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.embeddings import Embeddings
from rustic_ai.vertexai.client import VertexAIBase, VertexAIConf


class VertexAIEmbeddingConf(VertexAIConf):
    auto_truncate: bool = False
    task_type: Optional[str] = None
    output_dimensionality: Optional[int] = None
    tokens_per_entry: int = 500
    max_tokens_per_batch: int = 20000


DEFAULT_MODEL: str = "text-embedding-005"


class VertexAIEmbeddings(Embeddings, VertexAIBase):
    def __init__(self, model: str, conf: VertexAIEmbeddingConf):
        self.conf = conf
        VertexAIBase.__init__(self, conf.project_id, conf.location)
        self.model = model

    def _create_embedding_batches(self, text: list[str], tokens_per_entry: int) -> list[list[Part]]:
        if not text:
            return []

        if tokens_per_entry <= 0:
            raise ValueError("Tokens per entry must be greater than 0")

        # Create batches
        batches = []
        current_batch = []
        current_batch_tokens = 0

        for t in text:
            embedding_input = Part.from_text(text=t)

            # If adding this would exceed our token limit, start a new batch
            if current_batch_tokens + tokens_per_entry < self.conf.max_tokens_per_batch:
                # Add to current batch
                current_batch.append(embedding_input)
                current_batch_tokens += tokens_per_entry
            else:
                batches.append(current_batch)
                current_batch = [embedding_input]
                current_batch_tokens = tokens_per_entry

        # Add the last batch if it's not empty
        if current_batch:
            batches.append(current_batch)

        return batches

    def embed(self, text: List[str]) -> List[List[float]]:
        input_batches = self._create_embedding_batches(text, self.conf.tokens_per_entry)
        result: List[List[float]] = []
        for batch in input_batches:
            embeddings = self.genai_client.models.embed_content(
                model=self.model,
                contents=batch,
                config=EmbedContentConfig(
                    task_type=self.conf.task_type,
                    auto_truncate=self.conf.auto_truncate,
                    output_dimensionality=self.conf.output_dimensionality,
                ),
            ).embeddings
            for embedding in embeddings:
                result.append(embedding.values)
        return result


class VertexAIEmbeddingsResolver(DependencyResolver[Embeddings]):
    memoize_resolution: bool = False

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        conf: JsonDict = {},
    ):
        super().__init__()
        embedding_conf = VertexAIEmbeddingConf.model_validate(conf)

        self.embedding = VertexAIEmbeddings(
            model=model_name,
            conf=embedding_conf,
        )

    def resolve(self, guild_id: str, agent_id: str) -> Embeddings:
        return self.embedding
