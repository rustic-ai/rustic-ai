from typing import AsyncGenerator, List

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..constants import (
    CHUNK_ID_PATTERN,
    DEFAULT_ENCODING,
    DEFAULT_TEXT_CHUNK_SIZE,
    DEFAULT_TEXT_OVERLAP,
    ENCODING_ERRORS,
    LIBRARY_DIR,
    TEXT_LIKE_TYPES,
)
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class SimpleTextChunker(ChunkerPlugin):
    """Naive, dependency-free chunker.

    - For text media: splits by character length with overlap, preserves modality and metadata
    - For non-text media: returns a single chunk (no-op)
    """

    chunk_size: int = Field(default=DEFAULT_TEXT_CHUNK_SIZE, gt=0)
    chunk_overlap: int = Field(default=DEFAULT_TEXT_OVERLAP, ge=0)

    def _split_text(self, text: str) -> List[str]:
        if not text:
            return [""]
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))

        chunks: List[str] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(n, start + size)
            chunks.append(text[start:end])
            if end == n:
                break
            start = end - overlap
        return chunks

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = LIBRARY_DIR) -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        # Only process textual knols (text/* or application/* treated as documents)
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in TEXT_LIKE_TYPES:
            return

        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))
        buffer: str = ""
        idx = 0
        language = knol.language
        encoding = knol.metadata_consolidated.get("encoding") or DEFAULT_ENCODING

        async with KnolUtils.stream_content(knol, fs, library_path, mode="rb") as stream:
            async for block in stream:
                # block is bytes; decode using declared encoding
                if isinstance(block, (bytes, bytearray)):
                    block_text = bytes(block).decode(encoding, errors=ENCODING_ERRORS)
                else:
                    # Fallback, should rarely occur
                    block_text = str(block)
                buffer += block_text
                # Flush full-size chunks from the buffer
                while len(buffer) > size:
                    piece = buffer[:size]
                    data = piece.encode(encoding, errors=ENCODING_ERRORS)
                    chunk = TextChunk(
                        id=CHUNK_ID_PATTERN.format(knol_id=knol.id, chunker_name=self.__class__.__name__, index=idx),
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
                    idx += 1
                    buffer = buffer[size - overlap :] if overlap > 0 else buffer[size:]

        # Flush any remainder
        if buffer:
            data = buffer.encode(encoding, errors=ENCODING_ERRORS)
            chunk = TextChunk(
                id=CHUNK_ID_PATTERN.format(knol_id=knol.id, chunker_name=self.__class__.__name__, index=idx),
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
