from typing import AsyncGenerator, Dict, List

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin

LANG_SEPARATORS: Dict[str, List[str]] = {
    "python": ["\nclass ", "\ndef ", "\nasync def ", "\nif __name__ == ", "\n"],
    "javascript": ["\nclass ", "\nfunction ", "\nexport ", "\nconst ", "\nlet ", "\n"],
    "typescript": ["\nclass ", "\nfunction ", "\nexport ", "\nconst ", "\nlet ", "\n"],
    "java": ["\nclass ", "\npublic ", "\nprivate ", "\nprotected ", "\n"],
    "go": ["\npackage ", "\nfunc ", "\ntype ", "\nvar ", "\nconst ", "\n"],
    "rust": ["\nfn ", "\nstruct ", "\nenum ", "\nimpl ", "\nmod ", "\n"],
    "cpp": ["\nclass ", "\nstruct ", "\ntemplate<", "\nnamespace ", "\n"],
}


class CodeLanguageChunker(ChunkerPlugin):
    """Language-aware code splitter using priority separators, then packs into chunks.

    Falls back to general line-based splitting when language is unknown.
    """

    language: str = Field(default="python")
    chunk_size: int = Field(default=1200, gt=0)
    chunk_overlap: int = Field(default=120, ge=0)

    def _split_by_separators(self, text: str, separators: List[str]) -> List[str]:
        if not separators:
            return [text]
        sep = separators[0]
        parts = text.split(sep)
        if len(parts) == 1:
            return self._split_by_separators(text, separators[1:])
        units: List[str] = []
        for i, part in enumerate(parts):
            sub = self._split_by_separators(part, separators[1:])
            units.extend(sub)
            if i < len(parts) - 1:
                units.append(sep)
        return units

    def _pack(self, units: List[str]) -> List[str]:
        chunks: List[str] = []
        buf: List[str] = []
        bl = 0
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))
        for u in units:
            if bl + len(u) > size:
                if bl > 0:
                    txt = "".join(buf)
                    chunks.append(txt)
                    if overlap > 0:
                        tail = txt[-overlap:]
                        buf = [tail, u]
                        bl = len(tail) + len(u)
                    else:
                        buf = [u]
                        bl = len(u)
                else:
                    chunks.append(u[:size])
                    rem = u[size - overlap :] if overlap > 0 else u[size:]
                    buf = [rem]
                    bl = len(rem)
            else:
                buf.append(u)
                bl += len(u)
        if bl > 0:
            chunks.append("".join(buf))
        return chunks

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in {"text", "application"}:
            return

        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        data = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
        content = bytes(data).decode(encoding, errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data)

        separators = LANG_SEPARATORS.get(self.language.lower(), ["\n\n", "\n", " ", ""])
        units = self._split_by_separators(content, separators)
        texts = self._pack(units)

        for idx, text in enumerate(texts):
            data = text.encode(encoding, errors="ignore")
            chunk = TextChunk(
                id=f"{knol.id}:{self.__class__.__name__}:{idx}",
                knol_id=knol.id,
                index=idx,
                producer_id=self.id,
                content_bytes=data if self.attach_bytes else None,
                language=knol.language,
                encoding=encoding,
                mimetype=mimetype,
                name=knol.name,
            )
            if self.write_derived_bytes:
                await KnolUtils.write_chunk_derived_bytes(fs, library_path, self.id, chunk, data)
            yield chunk
