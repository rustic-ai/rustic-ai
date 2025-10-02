import html as html_lib
import re
from typing import Optional

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from ..chunks import ChunkBase, TextChunk
from ..model import Modality
from ..plugins import ProjectorPlugin

_SCRIPT_STYLE_RE = re.compile(r"<\s*(script|style)[^>]*?>[\s\S]*?<\s*/\s*\1\s*>", re.IGNORECASE)
_BLOCK_TAGS = (
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "li",
    "ul",
    "ol",
    "table",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)
_BLOCK_OPEN_RE = re.compile(r"<\s*(?:" + "|".join(_BLOCK_TAGS) + r")\b[^>]*>", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(r"<\s*/\s*(?:" + "|".join(_BLOCK_TAGS) + r")\s*>", re.IGNORECASE)
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html_to_text(html: str) -> str:
    # Remove scripts and styles
    s = _SCRIPT_STYLE_RE.sub(" ", html)
    # Convert some structural tags to newlines/spaces
    s = _BR_RE.sub("\n", s)
    s = _BLOCK_OPEN_RE.sub("\n", s)
    s = _BLOCK_CLOSE_RE.sub("\n", s)
    # Drop remaining tags
    s = _TAG_RE.sub(" ", s)
    # Unescape entities
    s = html_lib.unescape(s)
    # Normalize whitespace: collapse spaces/tabs, normalize multiple blank lines
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[\t\f\v\u00A0]+", " ", s)  # replace tabs/nbsp etc with space
    s = re.sub(r"[ ]{2,}", " ", s)
    s = re.sub(r"\n[ \t]*\n{2,}", "\n\n", s)
    # Trim spaces around newlines
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    return s.strip()


class HTMLToTextProjector(ProjectorPlugin):
    """Project HTML text into normalized plain text.

    - Accepts text/html or application/xhtml+xml inputs
    - Outputs text/plain encoded as UTF-8
    """

    source_modality: Modality = Modality.TEXT
    target_modality: Modality = Modality.TEXT
    target_mimetype: Optional[str] = "text/plain"

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        if not mimetype:
            return False
        mt = mimetype.split(";", 1)[0].strip().lower()
        return mt == "text/html" or mt == "application/xhtml+xml" or mt.endswith("+html")

    async def project(
        self,
        chunk: ChunkBase,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> ChunkBase:  # type: ignore[override]
        # Obtain bytes from the source chunk
        raw = chunk.content_bytes or await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = getattr(chunk, "encoding", None) or "utf-8"
        try:
            html_text = raw.decode(encoding, errors="ignore")
        except Exception:
            html_text = str(raw)

        text = _strip_html_to_text(html_text)
        data = text.encode("utf-8", errors="ignore")

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
