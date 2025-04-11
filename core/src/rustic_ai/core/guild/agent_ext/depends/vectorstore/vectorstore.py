from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.media import Document

DEFAULT_K = 4


class UpsertResponse(BaseModel):
    """
    Represents the response of an upsert operation.

    The response contains a list of succeeded and failed document IDs.
    """

    succeeded: List[str] = []
    failed: List[str] = []


class VectorSearchResult(BaseModel):
    """
    Represents a single search result.

    A search result contains a document and its score.
    """

    document: Document
    score: float = 1.0


class VectorSearchResults(BaseModel):
    """
    Represents the result of a search operation.

    The result contains a list of documents and the total number of documents found.
    """

    query: str
    query_id: str = Field(default="")
    results: List[VectorSearchResult] = []

    @property
    def total(self) -> int:  # pragma: no cover
        return len(self.results)

    @property
    def documents(self) -> List[Document]:
        return [sr.document for sr in self.results]

    @property
    def scores(self) -> List[float]:  # pragma: no cover
        return [sr.score for sr in self.results]


class VectorStore(ABC):
    """Interface for vector stores."""

    @abstractmethod
    def upsert(self, documents: List[Document]) -> UpsertResponse:
        """Upsert a document into the vector store.

        Args:
            documents: List of documents to upsert.

        Returns:
            UpsertResponse: Response of the upsert operation,
            containing a list of succeeded and failed document IDs.
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete(self, ids: Optional[List[str]] = None) -> Optional[bool]:
        """
        Delete a document from the vector store.

        Args:
            ids: List of document IDs to delete. If None, all documents will be deleted.

        Returns:
            bool: True if the operation was successful, False otherwise.
            None if the operation is not supported by the vecotr store.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_by_ids(self, ids: List[str]) -> List[Document]:
        """
        Get documents by their IDs.

        Args:
            ids: List of document IDs.

        Returns:
            List[Document]: List of documents.
        """
        pass  # pragma: no cover

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        k: int = DEFAULT_K,
        metadata_filter: Optional[Dict[str, str]] = None,
        where_documents: Optional[Dict[str, str]] = None,
    ) -> VectorSearchResults:
        """
        Performs a similarity search against a vector search system. This method identifies
        the most relevant results based on the provided query, constraints, and the number
        of results to return. The search is conducted in such a way that the function may
        also incorporate document-based filters to refine results.

        Args:
            query: The string query to be used for matching in the similarity search.
            k: The number of top results to return from the search. Defaults to 'DEFAULT_K'.
            metadata_filter: An optional dictionary specifying constraints on metadata fields
            where_documents: An optional dictionary representing additional document-specific
                constraints or conditions for refining the search.

        Returns:
            VectorSearchResults: object with list of documents and the total number of documents found.
        """
        pass  # pragma: no cover
