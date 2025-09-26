from typing import AsyncGenerator

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import AudioChunk, ChunkBase
from ..constants import DEFAULT_CHUNK_SIZE, LIBRARY_DIR
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class AudioFixedByteChunker(ChunkerPlugin):
    """Split audio payload into fixed-size byte segments (dependency-free)."""

    chunk_bytes: int = Field(default=DEFAULT_CHUNK_SIZE, gt=0)

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = LIBRARY_DIR) -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major != "audio":
            return

        idx = 0
        async with KnolUtils.stream_content(knol, fs, library_path, mode="rb", chunk_size=self.chunk_bytes) as stream:
            async for block in stream:
                chunk = AudioChunk(
                    id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                    knol_id=knol.id,
                    index=idx,
                    producer_id=self.id,
                    mimetype=mimetype,
                )
                data = bytes(block)
                if self.attach_bytes:
                    chunk.content_bytes = data
                if self.write_derived_bytes:
                    await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
                yield chunk
                idx += 1
