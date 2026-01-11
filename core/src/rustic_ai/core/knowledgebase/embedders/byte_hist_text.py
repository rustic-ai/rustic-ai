from typing import List

from ..chunks import ChunkBase, TextChunk
from ..plugins import EmbedderPlugin


class ByteHistogramTextEmbedder(EmbedderPlugin):
    """256-dim byte histogram over UTF-8 bytes of TextChunk.text."""

    dimension: int = 256

    def supports_mimetype(self, mimetype: str) -> bool:
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        return major in {"text", "application"}

    async def embed(self, chunk: ChunkBase, *, fs, library_path: str = "library") -> List[float]:
        if not isinstance(chunk, TextChunk):
            raise TypeError("ByteHistogramTextEmbedder expects TextChunk")
        # Use content_bytes if available, otherwise read derived bytes
        raw = chunk.content_bytes
        if raw is None:
            raw = await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = chunk.encoding or "utf-8"
        try:
            text = bytes(raw).decode(encoding, errors="ignore")
        except Exception:
            text = str(raw)
        data = text.encode(encoding, errors="ignore")
        hist = [0.0] * 256
        for b in data:
            hist[b] += 1.0
        return hist
