from typing import List, Tuple

from langchain_core.documents import Document as LCDocument
from langchain_core.indexing import UpsertResponse as LCUpsertResponse

from rustic_ai.core.guild.agent_ext.depends.vectorstore.vectorstore import (
    UpsertResponse,
    VectorSearchResult,
    VectorSearchResults,
)
from rustic_ai.langchain.utils.doc_utils import DocUtils


class VectorSearchUtils:
    @staticmethod
    def from_langchain_response(langchain_response: Tuple[LCDocument, float]) -> VectorSearchResult:  # pragma: no cover
        langchain_doc, score = langchain_response
        return VectorSearchResult(document=DocUtils.from_langchain(langchain_doc), score=score)

    @staticmethod
    def from_langchain_responses(
        query: str, langchain_responses: List[Tuple[LCDocument, float]]
    ) -> VectorSearchResults:
        results = [
            VectorSearchResult(document=DocUtils.from_langchain(langchain_doc), score=score)
            for langchain_doc, score in langchain_responses
        ]
        return VectorSearchResults(query=query, results=results)


class UpsertResponseUtils:
    @staticmethod
    def from_langchain(langchain_response: LCUpsertResponse) -> UpsertResponse:  # pragma: no cover
        return UpsertResponse(succeeded=langchain_response["succeeded"], failed=langchain_response["failed"])
