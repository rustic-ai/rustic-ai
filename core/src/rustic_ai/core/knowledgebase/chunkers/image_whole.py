from typing import AsyncGenerator

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, ImageChunk
from ..constants import LIBRARY_DIR
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class ImageWholeFileChunker(ChunkerPlugin):
    """Emit a single ImageChunk per image knol without decoding.

    Dependency-free. Consumers can retrieve bytes via KnolUtils when needed.
    """

    # Reserved for future options; present to match other chunkers' style
    pass_through: bool = Field(default=True)

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = LIBRARY_DIR) -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major != "image":
            return

        chunk = ImageChunk(
            id=f"{knol.id}:{self.__class__.__name__}:0",
            knol_id=knol.id,
            index=0,
            producer_id=self.id,
            name=knol.name,
            mimetype=mimetype,
        )
        if self.attach_bytes:
            raw = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
            assert isinstance(raw, bytes)
            chunk.content_bytes = raw
        if self.write_derived_bytes and chunk.content_bytes:
            await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, chunk.content_bytes)
        yield chunk
