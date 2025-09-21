"""Storage backend interface for persisting EmittedRows.

This interface keeps storage concerns orthogonal to pipelines and executors.
Implementations (e.g., LanceDB, Milvus) perform schema validation, table/collection
setup, idempotent upserts, and vector search. Row mapping leverages KBSchema so
ColumnSpec selectors (source=knol|chunk|meta) can extract values from EmittedRow.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterable, Dict, List, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .pipeline_executor import EmittedRow
from .query import SearchQuery
from .schema import KBSchema


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Identifier of the matched chunk")
    score: float = Field(description="Similarity score (higher is better unless backend returns distance)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Optional scalar fields returned by backend")


class KBIndexBackend(ABC):
    """Abstract interface for schema-aware storage backends.

    Responsibilities:
    - Ensure target table/collection exists based on KBSchema.TableSpec
    - Validate vector column definitions (dim, distance) for the vector spaces to be written
    - Idempotent upsert of rows mapped from EmittedRow via ColumnSpec selectors
    - Vector search over a designated vector column with optional scalar filtering
    """

    @abstractmethod
    async def ensure_ready(
        self,
        *,
        schema: KBSchema,
    ) -> None:
        """Ensure all tables/collections and vector indexes exist per KBSchema.

        Call once at startup or on schema change. Implementations may cache
        mapping of vector space ids to vector columns internally based on the
        declared VectorSpec entries in each table.
        """
        raise NotImplementedError

    @abstractmethod
    async def upsert(
        self,
        *,
        table_name: str,
        rows: AsyncIterable[EmittedRow],
    ) -> None:
        """Idempotently upsert a batch of rows into the target table.

        Implementations should:
        - Use the cached KBSchema/TableSpec to map ColumnSpec selectors from EmittedRow
        - Construct PK from TableSpec.primary_key
        - Write vectors only for the vector spaces present in each row (vector names
          should match vector column names, or use backend-internal mapping established
          during ensure_ready)
        """
        raise NotImplementedError

    @abstractmethod
    async def delete_by_chunk_ids(
        self,
        *,
        table_name: str,
        chunk_ids: Sequence[str],
    ) -> None:
        """Delete rows by chunk_id if supported/desired by the backend."""
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        *,
        query: SearchQuery,
    ) -> List[SearchResult]:
        """Run vector search with optional scalar filtering.

        Args:
            query: SearchQuery. Implementations may assume a single target
                (first entry of query.targets) and ignore orchestrator-level
                concerns like reranking or expansion.
        """
        raise NotImplementedError
