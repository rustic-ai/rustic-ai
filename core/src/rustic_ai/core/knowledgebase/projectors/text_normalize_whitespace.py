import re
from typing import Optional

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from ..chunks import ChunkBase, TextChunk
from ..model import Modality
from ..plugins import ProjectorPlugin


def _normalize_whitespace(text: str) -> str:
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse internal whitespace runs to single spaces (not across newlines)
    s = re.sub(r"[\t\f\v\u00A0]+", " ", s)
    s = re.sub(r"[ ]{2,}", " ", s)
    # Trim trailing and leading spaces per line
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    # Collapse multiple blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


class TextNormalizeWhitespaceProjector(ProjectorPlugin):
    """Normalize whitespace in textual chunks, preserving line breaks.

    Useful as a post-processing step after HTML or JSON projection.
    """

    source_modality: Modality = Modality.TEXT
    target_modality: Modality = Modality.TEXT
    target_mimetype: Optional[str] = "text/plain"

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        if not mimetype:
            return False
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        return major == "text" or mimetype == "application/json"

    async def project(
        self,
        chunk: ChunkBase,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> ChunkBase:  # type: ignore[override]
        raw = chunk.content_bytes or await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = getattr(chunk, "encoding", None) or "utf-8"
        try:
            text = raw.decode(encoding, errors="ignore")
        except Exception:
            text = str(raw)

        norm = _normalize_whitespace(text)
        data = norm.encode("utf-8", errors="ignore")

        out = TextChunk(
            id=f"{chunk.knol_id}:{self.__class__.__name__}:{chunk.index}",
            knol_id=chunk.knol_id,
            index=chunk.index,
            producer_id=self.id,
            content_bytes=data,
            language=getattr(chunk, "language", None),
            encoding="utf-8",
            mimetype="text/plain",
            name=chunk.name,
        )
        return out
