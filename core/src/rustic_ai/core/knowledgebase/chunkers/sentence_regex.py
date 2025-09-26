import re
from typing import AsyncGenerator, List

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class SentenceChunker(ChunkerPlugin):
    """Regex-based sentence splitter with character packing and overlap.

    Heuristic and dependency-free; good default for prose.
    """

    chunk_size: int = Field(default=1200, gt=0)
    chunk_overlap: int = Field(default=120, ge=0)
    # Basic sentence-end punctuation with whitespace
    sentence_pattern: str = Field(default=r"(?<=[.!?])\s+")

    def _split_sentences(self, text: str) -> List[str]:
        if not text:
            return [""]
        try:
            parts = re.split(self.sentence_pattern, text)
        except re.error:
            parts = [text]
        return [p for p in parts if p is not None]

    def _pack(self, sentences: List[str]) -> List[str]:
        chunks: List[str] = []
        buf: List[str] = []
        buf_len = 0
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))

        for sent in sentences:
            if not sent:
                continue
            s = sent if sent.endswith(" ") else sent + " "
            if buf_len + len(s) > size:
                if buf_len > 0:
                    text = "".join(buf).rstrip()
                    chunks.append(text)
                    if overlap > 0:
                        tail = text[-overlap:]
                        buf = [tail, s]
                        buf_len = len(tail) + len(s)
                    else:
                        buf = [s]
                        buf_len = len(s)
                else:
                    chunks.append(s[:size])
                    remainder = s[size - overlap :] if overlap > 0 else s[size:]
                    buf = [remainder]
                    buf_len = len(remainder)
            else:
                buf.append(s)
                buf_len += len(s)

        if buf_len > 0:
            chunks.append("".join(buf).rstrip())
        return chunks

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in {"text", "application"}:
            return

        # Read whole text (small/medium docs) via binary stream, decode blocks
        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        buffer: str = ""
        async with KnolUtils.stream_content(knol, fs, library_path, mode="rb") as stream:
            async for block in stream:
                if isinstance(block, (bytes, bytearray)):
                    buffer += bytes(block).decode(encoding, errors="ignore")
                else:
                    buffer += str(block)

        sentences = self._split_sentences(buffer)
        texts = self._pack(sentences)
        language = knol.language
        for idx, text in enumerate(texts):
            data = text.encode(encoding, errors="ignore")
            chunk = TextChunk(
                id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                knol_id=knol.id,
                index=idx,
                producer_id=self.id,
                content_bytes=data if self.attach_bytes else None,
                language=language,
                encoding=encoding,
                mimetype=mimetype,
                name=knol.name,
            )
            if self.write_derived_bytes:
                await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
            yield chunk
