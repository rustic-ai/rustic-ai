import json
from typing import Optional

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from ..chunks import ChunkBase, TextChunk
from ..model import Modality
from ..plugins import ProjectorPlugin


class JSONToTextProjector(ProjectorPlugin):
    """Project JSON bytes into pretty-printed UTF-8 text."""

    source_modality: Modality = Modality.TEXT
    target_modality: Modality = Modality.TEXT
    target_mimetype: Optional[str] = "text/plain"
    indent: int = 2
    ensure_ascii: bool = False

    def supports_mimetype(self, mimetype: str) -> bool:  # type: ignore[override]
        if not mimetype:
            return False
        mt = mimetype.split(";", 1)[0].strip().lower()
        return mt == "application/json" or mt.endswith("+json")

    async def project(
        self,
        chunk: ChunkBase,
        *,
        fs: FileSystem,
        library_path: str = "library",
    ) -> ChunkBase:  # type: ignore[override]
        raw = chunk.content_bytes or await self.get_chunk_bytes(chunk, fs, library_path)
        encoding = getattr(chunk, "encoding", None) or "utf-8"
        try:
            s = raw.decode(encoding, errors="ignore")
        except Exception:
            s = str(raw)

        try:
            obj = json.loads(s)
            text = json.dumps(obj, indent=int(self.indent), ensure_ascii=bool(self.ensure_ascii))
        except Exception:
            # Fallback to raw string if not valid JSON
            text = s

        data = text.encode("utf-8", errors="ignore")

        out = TextChunk(
            id=f"{chunk.knol_id}:{self.__class__.__name__}:{chunk.index}",
            knol_id=chunk.knol_id,
            index=chunk.index,
            producer_id=self.id,
            content_bytes=data,
            language=getattr(chunk, "language", None),
            encoding="utf-8",
            mimetype="text/plain",
            name=chunk.name,
        )
        return out
