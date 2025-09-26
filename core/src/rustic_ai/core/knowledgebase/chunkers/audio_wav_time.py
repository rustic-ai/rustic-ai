import io
from typing import AsyncGenerator
import wave

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import AudioChunk, ChunkBase
from ..constants import LIBRARY_DIR
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class AudioWavTimeChunker(ChunkerPlugin):
    """Split PCM WAV audio by duration using stdlib `wave` (no external deps).

    Writes each segment as a valid WAV (header + frames) to derived bytes.
    """

    chunk_ms: int = Field(default=30_000, gt=0)
    overlap_ms: int = Field(default=0, ge=0)

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = LIBRARY_DIR) -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = (knol.mimetype or "").lower()
        if mimetype != "audio/wav":
            return

        # Read full bytes (WAV header needs random access); still dependency-free
        data = await KnolUtils.read_content(knol, fs, library_path, mode="rb")

        assert isinstance(data, bytes)
        raw = data

        with wave.open(io.BytesIO(raw), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()

            frames_per_ms = framerate / 1000.0
            chunk_frames = max(1, int(self.chunk_ms * frames_per_ms))
            overlap_frames = max(0, min(int(self.overlap_ms * frames_per_ms), chunk_frames - 1))

            start_frame = 0
            idx = 0
            while start_frame < nframes:
                end_frame = min(nframes, start_frame + chunk_frames)
                wf.setpos(start_frame)
                frames = wf.readframes(end_frame - start_frame)

                # Write a proper WAV buffer for the segment
                buf = io.BytesIO()
                with wave.open(buf, "wb") as out:
                    out.setnchannels(nchannels)
                    out.setsampwidth(sampwidth)
                    out.setframerate(framerate)
                    out.writeframes(frames)
                segment = buf.getvalue()

                start_ms = int(start_frame / frames_per_ms)
                end_ms = int(end_frame / frames_per_ms)

                chunk = AudioChunk(
                    id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                    knol_id=knol.id,
                    index=idx,
                    producer_id=self.id,
                    mimetype=mimetype,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    sample_rate_hz=framerate,
                    channels=nchannels,
                )
                if self.attach_bytes:
                    chunk.content_bytes = segment
                if self.write_derived_bytes:
                    await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, segment, ext="wav")
                yield chunk

                if end_frame == nframes:
                    break
                start_frame = end_frame - overlap_frames if overlap_frames > 0 else end_frame
                idx += 1
