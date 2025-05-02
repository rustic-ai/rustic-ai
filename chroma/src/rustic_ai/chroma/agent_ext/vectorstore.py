import logging
from typing import Dict, List, Optional

import chromadb
from chromadb import EmbeddingFunction as ChromaEF
from chromadb import Embeddings as ChromaEmbeddings
from chromadb.api.types import D as ChromaEmbeddable

from rustic_ai.core.agents.commons.media import Document
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.agent_ext.depends.embeddings import Embeddings
from rustic_ai.core.guild.agent_ext.depends.vectorstore import (
    UpsertResponse,
    VectorStore,
)
from rustic_ai.core.guild.agent_ext.depends.vectorstore.vectorstore import (
    DEFAULT_K,
    VectorSearchResult,
    VectorSearchResults,
)
from rustic_ai.core.utils import JsonDict


class Chroma(VectorStore):
    def __init__(self, collection) -> None:
        self.collection = collection

    def upsert(self, documents: List[Document]) -> UpsertResponse:
        ids = [doc.id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
        return UpsertResponse(succeeded=ids, failed=[])

    def delete(self, ids: Optional[List[str]] = None) -> Optional[bool]:
        self.collection.delete(ids=ids)
        return True

    def get_by_ids(self, ids: List[str]) -> List[Document]:
        results = self.collection.get(ids=ids)
        docs = []
        for i in range(len(results["ids"])):
            docs.append(
                Document(id=results["ids"][i], content=results["documents"][i], metadata=results["metadatas"][i])
            )
        return docs

    def similarity_search(
        self,
        query: str,
        k: int = DEFAULT_K,
        metadata_filter: Optional[Dict[str, str]] = None,
        where_documents: Optional[Dict[str, str]] = None,
    ) -> VectorSearchResults:
        results = self.collection.query(query_texts=[query], n_results=k, where=metadata_filter or where_documents)

        search_results = []
        for i in range(len(results["ids"][0])):
            doc = Document(
                id=results["ids"][0][i], content=results["documents"][0][i], metadata=results["metadatas"][0][i]
            )
            score = results["distances"][0][i] if "distances" in results else 1.0
            search_results.append(VectorSearchResult(document=doc, score=score))

        return VectorSearchResults(query=query, results=search_results)


class ChromaEmbeddingFunction(ChromaEF):
    def __init__(self, embeddings: Embeddings):
        self.embeddings = embeddings

    def __call__(self, input: ChromaEmbeddable) -> ChromaEmbeddings:
        return self.embeddings.embed(input)


class ChromaResolver(DependencyResolver[VectorStore]):
    def __init__(self, chroma_settings: JsonDict = {}):
        super().__init__()
        self.chroma_settings = chroma_settings

    def resolve(self, guild_id: str, agent_id: str) -> VectorStore:
        try:
            embeddings: Embeddings = self.inject(Embeddings, "embeddings", guild_id, agent_id)
        except Exception as e:
            logging.error(f"Error creating embeddings: {e}")
            raise

        settings = chromadb.config.Settings.validate(self.chroma_settings)
        settings.anonymized_telemetry = False

        if settings.persist_directory is None:
            client = chromadb.Client(settings)
        else:
            client = chromadb.PersistentClient(path=settings.persist_directory, settings=settings)

        ef = ChromaEmbeddingFunction(embeddings)

        collection = client.get_or_create_collection(name=f"rusticai_{guild_id}_{agent_id}", embedding_function=ef)

        return Chroma(collection)
