import logging
from typing import Any, AsyncGenerator, List

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from jsonpath_ng import parse as jp_parse
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class JSONPathChunker(ChunkerPlugin):
    """Split JSON documents into chunks by JSONPath selections.

    Each selected node (object/array element) becomes a chunk. If no paths provided,
    falls back to a single chunk.
    """

    include_paths: List[str] = Field(default_factory=list)

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in {"text", "application"}:
            return

        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        raw = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
        content = bytes(raw).decode(encoding, errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)

        try:
            import json

            data: Any = json.loads(content) if content else None
        except Exception:
            logging.warning("Failed to load JSON", exc_info=True)
            data = None

        idx = 0
        if not data or not self.include_paths:
            data = (content or "").encode(encoding, errors="ignore")
            chunk = TextChunk(
                id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                knol_id=knol.id,
                index=idx,
                producer_id=self.id,
                content_bytes=data if self.attach_bytes else None,
                language=knol.language,
                encoding=encoding,
                mimetype=mimetype or "application/json",
                name=knol.name,
            )
            if self.write_derived_bytes:
                await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
            yield chunk
            return

        for path in self.include_paths:
            try:
                expr = jp_parse(path)
                matches = [m.value for m in expr.find(data)]
            except Exception:
                matches = []
            for node in matches:
                try:
                    text = json.dumps(node, ensure_ascii=False)
                except Exception:
                    text = str(node)
                data_b = text.encode(encoding, errors="ignore")
                chunk = TextChunk(
                    id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                    knol_id=knol.id,
                    index=idx,
                    producer_id=self.id,
                    content_bytes=data_b if self.attach_bytes else None,
                    language=knol.language,
                    encoding=encoding,
                    mimetype=mimetype or "application/json",
                    name=knol.name,
                )
                if self.write_derived_bytes:
                    await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data_b)
                yield chunk
                idx += 1
        return
