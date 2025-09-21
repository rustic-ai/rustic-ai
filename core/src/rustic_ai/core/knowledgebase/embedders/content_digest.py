import hashlib
from typing import List

from ..chunks import ChunkBase, TextChunk
from ..plugins import EmbedderPlugin


class ContentDigestEmbedder(EmbedderPlugin):
    """Digest-based embedding from content (metadata-assisted for text).

    For TextChunk, digests the UTF-8 bytes of `text`. Produces a small fixed-dim
    float vector by chunking the hash digest into lanes.
    """

    dimension: int = 64
    algo: str = "sha256"  # any hashlib.new(algo)

    def supports_mimetype(self, mimetype: str) -> bool:
        # Works for text/application; can be extended to other modalities by reading bytes
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        return major in {"text", "application"}

    async def embed(self, chunk: ChunkBase, *, fs, library_path: str = "library") -> List[float]:
        if isinstance(chunk, TextChunk):
            data = (chunk.text or "").encode(chunk.encoding or "utf-8", errors="ignore")
        else:
            raise TypeError("ContentDigestEmbedder expects TextChunk in this variant")
        h = hashlib.new(self.algo)
        h.update(data)
        digest = h.digest()
        # Map digest bytes into dimension lanes
        vec = [0.0] * int(self.dimension)
        for i, b in enumerate(digest):
            vec[i % int(self.dimension)] += float(b)
        return vec
