import hashlib
import re
from typing import List

from ..chunks import ChunkBase, TextChunk
from ..plugins import EmbedderPlugin

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


class FeatureHashingTextEmbedder(EmbedderPlugin):
    """No-dependency text embedder using the hashing trick over tokens.

    - Lowercases input; extracts alnum/underscore tokens
    - Hashes tokens via stable sha256 and maps into fixed-dim bins
    - Optionally uses signed hash (positive/negative bucket updates)
    """

    dimension: int = 1024
    use_sign_hash: bool = True
    use_tf_log: bool = True

    def supports_mimetype(self, mimetype: str) -> bool:
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        return major in {"text", "application"}

    async def embed(self, chunk: ChunkBase, *, fs, library_path: str = "library") -> List[float]:
        if not isinstance(chunk, TextChunk):
            raise TypeError("FeatureHashingTextEmbedder expects TextChunk")
        # Obtain text, falling back to derived bytes if content_bytes is missing
        raw = chunk.content_bytes
        if raw is None:
            raw = await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = chunk.encoding or "utf-8"
        try:
            text = bytes(raw).decode(encoding, errors="ignore")
        except Exception:
            text = str(raw)
        text = (text or "").lower()
        tokens = _TOKEN_RE.findall(text)
        vec = [0.0] * int(self.dimension)
        if not tokens:
            return vec
        # compute term frequencies
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            # bucket index from first 8 bytes
            bucket = int.from_bytes(h[:8], "big") % int(self.dimension)
            sign = 1.0
            if self.use_sign_hash:
                sign = 1.0 if (h[8] & 1) == 0 else -1.0
            vec[bucket] += sign
        if self.use_tf_log:
            # Apply simple log scaling: log1p(|v|) * sign(v)
            import math

            vec = [0.0 if v == 0.0 else math.copysign(math.log1p(abs(v)), v) for v in vec]
            # Normalization handled by base
        return vec
