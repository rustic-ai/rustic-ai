from typing import AsyncGenerator

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class NoOpChunker(ChunkerPlugin):
    """No-op chunker."""

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        # For text/application, emit as TextChunk; otherwise, no chunk
        if major not in {"text", "application"}:
            return
        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        raw = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
        text = bytes(raw).decode(encoding, errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
        data = text.encode(encoding, errors="ignore")
        chunk = TextChunk(
            id=f"{knol.id}:{self.__class__.__name__}:0",
            knol_id=knol.id,
            index=0,
            producer_id=self.id,
            content_bytes=data if self.attach_bytes else None,
            language=knol.language,
            encoding=encoding,
            mimetype=mimetype,
            name=knol.name,
        )
        if self.write_derived_bytes:
            await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
        yield chunk
