import hashlib
from typing import List

from ..chunks import ChunkBase, TextChunk
from ..plugins import EmbedderPlugin


class ByteNgramTextEmbedder(EmbedderPlugin):
    """Hash k-byte shingles into a fixed-size vector (no deps)."""

    dimension: int = 2048
    ngram_k: int = 3
    use_sign_hash: bool = True

    def supports_mimetype(self, mimetype: str) -> bool:
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        return major in {"text", "application"}

    async def embed(self, chunk: ChunkBase, *, fs, library_path: str = "library") -> List[float]:
        if not isinstance(chunk, TextChunk):
            raise TypeError("ByteNgramTextEmbedder expects TextChunk")
        raw = chunk.content_bytes
        if raw is None:
            raw = await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = chunk.encoding or "utf-8"
        try:
            text = bytes(raw).decode(encoding, errors="ignore")
        except Exception:
            text = str(raw)
        data = (text or "").encode(encoding, errors="ignore")
        k = max(1, int(self.ngram_k))
        dim = int(self.dimension)
        vec = [0.0] * dim
        if len(data) < k:
            return vec
        for i in range(0, len(data) - k + 1):
            ngram = data[i : i + k]
            h = hashlib.sha256(ngram).digest()
            bucket = int.from_bytes(h[:8], "big") % dim
            sign = 1.0
            if self.use_sign_hash:
                sign = 1.0 if (h[8] & 1) == 0 else -1.0
            vec[bucket] += sign
        return vec
