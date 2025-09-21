from abc import ABC, abstractmethod
from typing import AsyncIterable, AsyncIterator, List, Optional, cast

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rustic_ai.core.knowledgebase.knol_utils import KnolUtils

from .chunks import ChunkBase
from .model import Knol, Modality, Vector
from .query import SearchQuery, SearchResult
from .schema import DistanceType


class KBPlugin(BaseModel, ABC):
    """Serializable and executable knowledge base plugin base."""

    model_config = ConfigDict(extra="forbid")
    kind: Optional[str] = Field(default=None)

    id: str = Field(description="Plugin identifier")

    def model_post_init(self, __context) -> None:
        """Set the kind field to the fully qualified class name if not provided."""
        if not self.kind:
            object.__setattr__(self, "kind", f"{self.__class__.__module__}.{self.__class__.__qualname__}")

    @model_validator(mode="after")
    def _enforce_kind_matches_class(self):
        """Ensure the kind field matches the actual class."""
        fqcn = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if self.kind and self.kind != fqcn:
            raise ValueError(f"`kind` must be {fqcn!r}, got {self.kind!r}")
        return self

    async def get_chunk_bytes(
        self,
        chunk: ChunkBase,
        fs: FileSystem,
        library_path: str = "library",
    ) -> bytes:
        """Get the bytes for a chunk."""
        if chunk.content_bytes:
            return chunk.content_bytes

        content_bytes = await KnolUtils.read_chunk_derived_bytes(fs, library_path, chunk.producer_id, chunk)
        return content_bytes


class EmbedderPlugin(KBPlugin, ABC):
    """Plugin for generating dense embeddings for documents and queries."""

    # Vector contract
    dimension: int = Field(default=0, description="Embedding dimensionality")
    distance: DistanceType = Field(default="cosine", description="Similarity metric")
    normalize: bool = Field(default=True, description="L2-normalize vectors (typically for cosine)")

    # Throughput
    max_batch_size: int = Field(default=0, description="Preferred max batch size; 0 means no batching")

    @abstractmethod
    async def embed(
        self,
        chunk: ChunkBase,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> Vector:
        """Generate a dense embedding vector for the given chunk."""
        pass

    # ---- helpers (can be reused by subclasses) ----
    @staticmethod
    def _l2_norm(vec: Vector) -> float:
        s = 0.0
        for x in vec:
            s += float(x) * float(x)
        return s**0.5

    @staticmethod
    def _normalize(vec: Vector) -> Vector:
        n = EmbedderPlugin._l2_norm(vec)
        if n <= 0.0:
            return [0.0 for _ in vec]
        return [float(x) / n for x in vec]

    def _validate_and_optionally_normalize(self, vec: Vector) -> Vector:
        if self.dimension and len(vec) != int(self.dimension):
            raise ValueError(f"Embedding length {len(vec)} != dimension {self.dimension}")
        # Simple finite check
        for v in vec:
            if not (float("-inf") < float(v) < float("inf")):
                raise ValueError("Embedding contains non-finite values")
        if self.distance == "cosine" and self.normalize:
            return self._normalize(vec)
        return vec

    async def embed_seq(
        self,
        chunks: AsyncIterable[ChunkBase],
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> AsyncIterable[Vector]:
        """Generate embeddings for multiple chunks.

        Default implementation awaits embed() for each item.
        Override for more efficient batch processing.
        """
        async for chunk in chunks:
            vec = await self.embed(chunk, fs=fs, library_path=library_path)
            yield self._validate_and_optionally_normalize(vec)

    async def embed_many(
        self,
        chunks: List[ChunkBase],
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> List[Vector]:
        """Embed a list of chunks, with basic batching by max_batch_size (sequential by default)."""
        if not chunks:
            return []
        batch_size = self.max_batch_size if self.max_batch_size and self.max_batch_size > 0 else len(chunks)
        results: List[Vector] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            for c in batch:
                v = await self.embed(c, fs=fs, library_path=library_path)
                results.append(self._validate_and_optionally_normalize(v))
        return results

    def supports_mimetype(self, mimetype: str) -> bool:
        """Check if this embedder supports the given mimetype."""
        return False

    def get_dimension(self) -> int:
        """Return the embedding dimension (from the 'dimension' field)."""
        return int(self.dimension)


class ChunkerPlugin(KBPlugin, ABC):
    """Plugin for splitting knol into chunk documents owned by the knowledge base.

    Implementations should generate deterministic chunk identifiers and preserve
    stable parent-child relationships via metadata (e.g., parent_id, chunk_index)
    or by setting these as typed fields during upsert in the backend.
    """

    attach_bytes: bool = Field(default=True, description="Whether to attach the bytes to the chunk")
    write_derived_bytes: bool = Field(default=True, description="Whether to write the derived bytes to the filesystem")

    @abstractmethod
    async def split(
        self,
        knol: Knol,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> AsyncIterator[ChunkBase]:
        """Split a single knol into one or more chunk documents.

        Implementations should ensure ordering is stable and each returned
        chunk has content appropriate for embedding and search. Chunks
        should typically preserve modality (text/image/audio/video) unless the
        plugin intentionally converts modalities (e.g., audio->transcript).
        """
        if False:
            # Hint to type-checker: this is an async generator
            yield cast(ChunkBase, None)
        raise NotImplementedError


class RerankerPlugin(KBPlugin, ABC):
    """Abstract base class for second-stage reranking of search results."""

    @abstractmethod
    async def rerank(
        self,
        *,
        results: List["SearchResult"],
        query: SearchQuery,
    ) -> List["SearchResult"]:
        """
        Rerank a list of search results based on the original query.

        Args:
            results: The initial list of SearchResult objects from the backend.
            query: The original SearchQuery object.

        Returns:
            A new list of SearchResult objects, sorted according to the
            reranking strategy, with potentially updated scores.
        """
        raise NotImplementedError


class ProjectorPlugin(KBPlugin, ABC):
    """Plugin for projecting chunks to different modalities (usually to text)."""

    source_modality: Modality  # "image", "audio", "video"
    target_modality: Modality  # "text" usually
    target_mimetype: Optional[str] = Field(
        default=None, description="Optional target mimetype; must match target modality's major type"
    )

    @abstractmethod
    async def project(
        self,
        chunk: ChunkBase,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> ChunkBase:
        """Project a chunk into target modality.

        Args:
            chunk: Source chunk to project

        Returns:
            Projected chunks (e.g., TextChunks from an ImageChunk)
        """
        pass

    async def project_seq(
        self,
        chunks: AsyncIterable[ChunkBase],
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> AsyncIterable[ChunkBase]:
        """Project a sequence of chunks into target modality."""
        async for chunk in chunks:
            projected_chunk = await self.project(chunk, fs=fs, library_path=library_path)
            yield projected_chunk

    def supports_mimetype(self, mimetype: str) -> bool:
        """Check if this projector supports the given mimetype."""
        return False
