import logging
from typing import List

from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.media import Document, MediaLink
from rustic_ai.core.guild import BaseAgentProps, agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.text_splitter import TextSplitter
from rustic_ai.core.guild.agent_ext.depends.vectorstore import (
    VectorSearchResults,
    VectorStore,
)
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency


class IngestDocuments(BaseModel):
    documents: List[Document | MediaLink]


class VectorSearchQuery(BaseModel):
    query: str
    id: str = Field(default="")
    k: int = Field(1, title="Number of similar documents to return")


class VectorAgentConf(BaseAgentProps):
    chunk_size: int = Field(10000, title="Size of the chunks to split the document into")
    chunk_overlap: int = Field(1000, title="Overlap between chunks")


class VectorAgent(Agent[VectorAgentConf]):
    """
    Agent that handles document indexing and similarity search using a vector store.
    """

    def __init__(self, agent_spec: AgentSpec[VectorAgentConf]):
        super().__init__(agent_spec)
        self.chunk_size = agent_spec.props.chunk_size
        self.chunk_overlap = agent_spec.props.chunk_overlap

    @staticmethod
    def _split_doc(doc: Document, chunks: List[str]) -> List[Document]:
        # create a document for each chunk with document is as docid-chunkid
        # The document metadata and rest of props are copied from the original document to the new document
        # Add the original doc id and chunk id to the metadata
        docs: List[Document] = []

        metadata = doc.metadata or {}

        for i, chunk in enumerate(chunks):
            cdoc = Document(
                id=f"{doc.id}-{i}",
                name=doc.name,
                content=chunk,
                mimetype=doc.mimetype,
                encoding=doc.encoding,
                metadata=metadata | {"doc_id": doc.id, "chunk_id": i},
            )
            docs.append(cdoc)

        return docs

    @agent.processor(
        IngestDocuments,
        depends_on=[
            AgentDependency(dependency_key="vectorstore", guild_level=True),
            AgentDependency(dependency_key="filesystem", guild_level=True),
            AgentDependency(dependency_key="textsplitter", guild_level=True),
        ],
    )
    def ingest_document(
        self,
        ctx: ProcessContext[IngestDocuments],
        vectorstore: VectorStore,
        filesystem: FileSystem,
        splitter: TextSplitter,
    ):
        """
        Handles messages of type MessageDataModel, doing cool things with the data
        """
        ingest_request = ctx.payload
        docs: List[Document] = []
        for doc in ingest_request.documents:
            if isinstance(doc, Document):
                chunks = splitter.split(doc.content)
                cdocs = self._split_doc(doc, chunks)
                docs.extend(cdocs)
            elif isinstance(doc, MediaLink) and doc.on_filesystem:
                with filesystem.open(doc.url, "rb") as f:
                    data = f.read()
                    chunks = splitter.split(data)
                    cdocs = self._split_doc(
                        Document(id=doc.id, name=doc.name, content=data, mimetype=doc.mimetype, encoding=doc.encoding),
                        chunks,
                    )
                    docs.extend(cdocs)
            elif isinstance(doc, MediaLink):
                logging.warning(f"MediaLink {doc.id} is not on the filesystem, skipping")

        response = vectorstore.upsert(docs)

        ctx.send(response)

    @agent.processor(VectorSearchQuery, depends_on=[AgentDependency(dependency_key="vectorstore", guild_level=True)])
    def answer_query(self, ctx: ProcessContext[VectorSearchQuery], vectorstore: VectorStore):
        """
        Handles messages of type MessageDataModel, doing cool things with the data
        """
        query = ctx.payload
        response: VectorSearchResults = vectorstore.similarity_search(query.query, query.k)

        response.query_id = query.id

        ctx.send(response)
