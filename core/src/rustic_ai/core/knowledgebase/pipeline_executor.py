"""Interfaces for executing knowledge base pipelines.

This module defines a minimal, storage-agnostic executor interface. Pipelines
are treated as pure transformations (target -> chunker -> [projector] -> embedder).
The executor orchestrates these transforms and yields rows as an async iterable.
Chunkers own content bytes via KnolUtils; the executor does not handle content
persistence.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Sequence, cast

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import BaseModel, ConfigDict, Field

from .chunks import AnyChunk
from .model import Knol
from .plugins import ChunkerPlugin, EmbedderPlugin, ProjectorPlugin


class EmittedRow(BaseModel):
    """Schema-agnostic record representing one source chunk and its vectors.

    - chunk_id identifies the chunk deterministically
    - knol is the source Knol snapshot (no content bytes involved)
    - chunk is the original source chunk from the chunker (not projected)
    - vectors maps vector_space_id to embedding vectors computed for this chunk
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    knol: Knol
    chunk: AnyChunk
    vectors: Dict[str, List[float]] = Field(default_factory=dict)


class ResolvedPipeline(BaseModel):
    """Concrete pipeline with plugin instances and vector space identity."""

    model_config = ConfigDict(extra="forbid")

    id: str
    chunker_id: str
    policy_version: str
    vector_space_id: str

    chunker: ChunkerPlugin
    embedder: EmbedderPlugin
    projector: Optional[ProjectorPlugin] = None


class PipelineExecutor(ABC):
    """Abstract executor: transform pipelines into emitted rows via an async sink.

    - No schema/table awareness; pure transform-to-records
    - Chunkers own bytes/derived bytes; executor does not persist content
    - Caller provides an async sink to handle storage
    """

    @abstractmethod
    async def rows_for_knol(
        self,
        *,
        knol: Knol,
        fs: FileSystem,
        library_path: str,
        pipelines: Sequence[ResolvedPipeline],
    ) -> AsyncIterator[EmittedRow]:
        """Yield rows for a single Knol by executing the provided pipelines.

        Args:
            knol: The Knol to process.
            fs: Async fsspec filesystem (created with asynchronous=True).
            library_path: Root library directory containing the Knol.
            pipelines: Concrete pipelines with plugin instances.

        Yields:
            EmittedRow instances ready for persistence by a storage layer.
        """
        if False:
            # Hint to type-checker: this is an async generator
            yield cast(EmittedRow, None)
        raise NotImplementedError


class SimplePipelineExecutor(PipelineExecutor):
    """Minimal, sequential executor that yields one row per chunk (per policy).

    - Groups pipelines by (chunker_id, policy_version)
    - Runs the shared chunker once; aggregates vectors from all pipelines in the group
    - Applies projector per-pipeline when supported
    - Embeds per-chunk (no batching) for simplicity
    """

    async def rows_for_knol(
        self,
        *,
        knol: Knol,
        fs: FileSystem,
        library_path: str,
        pipelines: Sequence[ResolvedPipeline],
    ) -> AsyncIterator[EmittedRow]:
        # Group pipelines by (chunker_id, policy_version)
        groups: Dict[tuple[str, str], List[ResolvedPipeline]] = {}
        for p in pipelines:
            groups.setdefault((p.chunker_id, p.policy_version), []).append(p)

        for (chunker_id, policy_version), group in groups.items():
            chunker = group[0].chunker
            async for base_chunk in chunker.split(knol, fs=fs, library_path=library_path):
                base_mime = base_chunk.mimetype or knol.mimetype or ""

                vectors: Dict[str, List[float]] = {}

                # For each pipeline in the group, attempt to project+embed
                for p in group:
                    cmime = base_mime
                    chunk = base_chunk
                    if p.projector and cmime and p.projector.supports_mimetype(cmime):
                        try:
                            chunk = await p.projector.project(base_chunk, fs=fs, library_path=library_path)
                        except Exception:
                            continue

                    emime = getattr(chunk, "mimetype", None) or cmime
                    if emime and hasattr(p.embedder, "supports_mimetype"):
                        try:
                            if not p.embedder.supports_mimetype(emime):
                                continue
                        except Exception:
                            continue

                    try:
                        vec = await p.embedder.embed(chunk, fs=fs, library_path=library_path)
                        vectors[p.vector_space_id] = [float(x) for x in vec]
                    except Exception:
                        continue

                if vectors:
                    yield EmittedRow(
                        chunk_id=base_chunk.id,
                        knol=knol,
                        chunk=base_chunk,  # preserve original source chunk
                        vectors=vectors,
                    )
