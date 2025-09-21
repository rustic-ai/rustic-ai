from typing import AsyncGenerator, List

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class RecursiveCharacterChunker(ChunkerPlugin):
    """Hierarchy-aware character splitter inspired by LangChain's RecursiveCharacterTextSplitter.

    Splits text using an ordered list of separators, then packs units into chunks with overlap.
    For non-text media, returns a single chunk (no-op).
    """

    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=100, ge=0)
    separators: List[str] = Field(default_factory=lambda: ["\n\n", "\n", " ", ""])
    keep_separator: bool = Field(default=False)

    def _split_units(self, text: str, seps: List[str]) -> List[str]:
        if not seps:
            return [text]
        sep = seps[0]
        # Character-level fallback
        if sep == "":
            return list(text)

        parts = text.split(sep)
        # If separator not found, try next level
        if len(parts) == 1:
            return self._split_units(text, seps[1:])

        units: List[str] = []
        for i, part in enumerate(parts):
            sub = self._split_units(part, seps[1:])
            units.extend(sub)
            if self.keep_separator and i < len(parts) - 1:
                units.append(sep)
        return units

    def _pack(self, units: List[str]) -> List[str]:
        chunks: List[str] = []
        buffer_parts: List[str] = []
        buffer_len = 0
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))

        for unit in units:
            if not unit:
                continue
            unit_len = len(unit)
            if buffer_len + unit_len > size:
                if buffer_len > 0:
                    chunk_text = "".join(buffer_parts)
                    chunks.append(chunk_text)
                    if overlap > 0:
                        # Keep tail of previous chunk as start of next buffer
                        overlap_text = chunk_text[-overlap:]
                        buffer_parts = [overlap_text, unit]
                        buffer_len = len(overlap_text) + unit_len
                    else:
                        buffer_parts = [unit]
                        buffer_len = unit_len
                else:
                    # Very long single unit; hard cut
                    chunks.append(unit[:size])
                    remainder = unit[size - overlap :] if overlap > 0 else unit[size:]
                    buffer_parts = [remainder]
                    buffer_len = len(remainder)
            else:
                buffer_parts.append(unit)
                buffer_len += unit_len

        if buffer_len > 0:
            chunks.append("".join(buffer_parts))
        return chunks

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in {"text", "application"}:
            return

        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        # Read whole content; this chunker packs based on unit boundaries
        data = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
        text = bytes(data).decode(encoding, errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data)

        units = self._split_units(text, list(self.separators))
        texts = self._pack(units)
        language = knol.language
        for idx, piece in enumerate(texts):
            data = piece.encode(encoding, errors="ignore")
            chunk = TextChunk(
                id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                knol_id=knol.id,
                index=idx,
                producer_id=self.id,
                content_bytes=data if self.attach_bytes else None,
                language=language,
                encoding=encoding,
                mimetype=mimetype,
                name=knol.name,
            )
            if self.write_derived_bytes:
                await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
            yield chunk
