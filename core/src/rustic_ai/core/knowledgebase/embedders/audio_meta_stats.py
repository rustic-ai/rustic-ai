from typing import List

from ..chunks import AudioChunk, ChunkBase
from ..plugins import EmbedderPlugin


class AudioMetaStatsEmbedder(EmbedderPlugin):
    """Metadata-only audio embedder (no deps, no decoding).

    Vector shape (example, dim=8):
      [sample_rate_scaled, channels_scaled, duration_sec_scaled, start_ms_scaled,
       end_ms_scaled, duration_ms_scaled, one_hot_channels_mono, one_hot_channels_multi]
    Scaled features are simple min-max style with coarse constants.
    """

    dimension: int = 8

    def supports_mimetype(self, mimetype: str) -> bool:
        return mimetype.lower().startswith("audio/")

    async def embed(self, chunk: ChunkBase, *, fs=None, library_path: str = "library") -> List[float]:
        if not isinstance(chunk, AudioChunk):
            raise TypeError("AudioMetaStatsEmbedder expects AudioChunk")
        sr = float(chunk.sample_rate_hz or 0)
        ch = float(chunk.channels or 0)
        start_ms = float(chunk.start_ms or 0)
        end_ms = float(chunk.end_ms or 0)
        duration_ms = max(0.0, end_ms - start_ms)
        duration_sec = duration_ms / 1000.0

        # Simple scaling with coarse bounds
        sr_scaled = min(sr / 48000.0, 1.0)
        ch_scaled = min(ch / 8.0, 1.0)
        dur_scaled = min(duration_sec / 600.0, 1.0)  # cap at 10 minutes
        start_scaled = min(start_ms / 600000.0, 1.0)
        end_scaled = min(end_ms / 600000.0, 1.0)
        dur_ms_scaled = min(duration_ms / 600000.0, 1.0)
        mono = 1.0 if ch == 1.0 else 0.0
        multi = 1.0 if ch > 1.0 else 0.0

        vec = [
            sr_scaled,
            ch_scaled,
            dur_scaled,
            start_scaled,
            end_scaled,
            dur_ms_scaled,
            mono,
            multi,
        ]
        # Pad/trim to exact dimension
        dim = int(self.dimension)
        if len(vec) < dim:
            vec = vec + [0.0] * (dim - len(vec))
        else:
            vec = vec[:dim]
        return vec
