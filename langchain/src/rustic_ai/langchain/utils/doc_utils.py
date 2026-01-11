from langchain_core.documents import Document as LCDocument
import shortuuid

from rustic_ai.core.agents.commons.media import Document


class DocUtils:
    @staticmethod
    def from_langchain(langchain_document: LCDocument) -> Document:
        return Document(
            id=langchain_document.id or shortuuid.uuid(),
            metadata=langchain_document.metadata,
            content=langchain_document.page_content,
        )

    @staticmethod
    def to_langchain(document: Document) -> LCDocument:
        metadata = document.metadata or {}
        metadata["name"] = document.name
        metadata["mimetype"] = document.mimetype
        metadata["encoding"] = document.encoding

        return LCDocument(
            page_content=document.content,
            id=document.id,
            metadata=metadata,
        )
