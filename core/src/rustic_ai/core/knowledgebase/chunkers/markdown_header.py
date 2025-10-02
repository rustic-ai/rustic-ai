import re
from typing import AsyncGenerator, ClassVar, List, Tuple

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import Field

from ..chunks import ChunkBase, TextChunk
from ..knol_utils import KnolUtils
from ..model import Knol
from ..plugins import ChunkerPlugin


class MarkdownHeaderChunker(ChunkerPlugin):
    """Markdown-aware splitter using ATX/setext headers, packing into chunks.

    Header path is stored in metadata as `header_path`.
    """

    chunk_size: int = Field(default=2000, gt=0)
    chunk_overlap: int = Field(default=200, ge=0)
    include_code_blocks: bool = Field(default=True)

    atx_re: ClassVar[re.Pattern[str]] = re.compile(r"^(#{1,6})\s+(.*)$")
    setext_re: ClassVar[re.Pattern[str]] = re.compile(r"^(.+)\n(=+|-+)\s*$", re.M)

    def _parse_sections(self, text: str) -> List[Tuple[List[str], str]]:
        lines = text.splitlines()
        header_stack: List[Tuple[int, str]] = []  # (level, title)
        sections: List[Tuple[List[str], str]] = []  # (header_path, body)
        body_lines: List[str] = []
        current_path: List[str] = []

        def flush_section():
            nonlocal body_lines
            if body_lines:
                sections.append((current_path.copy(), "\n".join(body_lines).strip()))
                body_lines = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            m = self.atx_re.match(line)
            if m:
                flush_section()
                level = len(m.group(1))
                title = m.group(2).strip()
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                current_path = [t for _, t in header_stack]
                i += 1
                continue

            # naive code fence handling when include_code_blocks=False
            if not self.include_code_blocks and line.strip().startswith("```"):
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    i += 1
                i += 1
                continue

            body_lines.append(line)
            i += 1

        flush_section()
        if not sections:
            sections = [([], text)]
        return sections

    def _pack(self, body: str, size: int, overlap: int) -> List[str]:
        if not body:
            return [""]
        chunks: List[str] = []
        start = 0
        n = len(body)
        while start < n:
            end = min(n, start + size)
            chunk = body[start:end]
            chunks.append(chunk)
            if end == n:
                break
            start = end - overlap
        return chunks

    async def split(self, knol: Knol, *, fs: FileSystem, library_path: str = "library") -> AsyncGenerator[ChunkBase, None]:  # type: ignore[override]
        mimetype = knol.mimetype or ""
        major = mimetype.split("/", 1)[0].lower() if "/" in mimetype else ""
        if major not in {"text", "application"}:
            return

        encoding = knol.metadata_consolidated.get("encoding") or "utf-8"
        data = await KnolUtils.read_content(knol, fs, library_path, mode="rb")
        content = bytes(data).decode(encoding, errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data)

        sections = self._parse_sections(content)
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size - 1))
        idx = 0
        for header_path, body in sections:
            texts = self._pack(body, size, overlap)
            for t in texts:
                data = t.encode(encoding, errors="ignore")
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
                idx += 1
        return
