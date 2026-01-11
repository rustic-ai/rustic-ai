import asyncio
from contextlib import asynccontextmanager
import json
import logging
from typing import Any, Dict, List, Optional, Union

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import TypeAdapter

from .chunks import AnyChunk, AudioChunk, ChunkBase, ImageChunk, TextChunk, VideoChunk
from .constants import (
    BYTES_SUBDIR,
    CHUNK_FILENAME_PATTERN,
    CHUNKS_DIR_PREFIX,
    CONTENT_FILENAME,
    DEFAULT_BINARY_EXT,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_ENCODING,
    DEFAULT_JSON_EXT,
    DEFAULT_TEXT_EXT,
    ENCODING_ERRORS,
    KNOL_META_FILENAME,
    LIBRARY_DIR,
    PREVIEWS_SUBDIR,
    TEXT_LIKE_TYPES,
)
from .fs_adapter import FileSystemAdapter
from .metadata import (
    AnyMetaPart,
    AudioMetaPart,
    CommonMetaPart,
    DocumentMetaPart,
    ExtraMetaPart,
    ImageMetaPart,
    VideoMetaPart,
)
from .model import Knol

logger = logging.getLogger(__name__)


class KnolUtils:

    @staticmethod
    async def read_knol_from_library(filesystem, library_dir: str, knol_id: str) -> Knol:
        """
        Async-only: expects an fsspec AsyncFileSystem (or DirFileSystem wrapping one),
        created with `asynchronous=True`.

        Uses underscore async methods and async file handles.
        """
        adapter = FileSystemAdapter(filesystem)
        knol_dir = f"{library_dir}/{knol_id}"

        if not await adapter.exists(knol_dir):
            raise FileNotFoundError(f"Knol {knol_id} not found in the filesystem.")

        knol_meta_file = f"{knol_dir}/{KNOL_META_FILENAME}"

        try:
            raw = await adapter.read_bytes(knol_meta_file)
            metadata_dict = json.loads(raw.decode(DEFAULT_ENCODING))
            return Knol.model_validate(metadata_dict)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to read knol metadata from {knol_meta_file}: {e}")
            raise ValueError(f"Invalid knol metadata in {knol_meta_file}") from e

    @staticmethod
    @asynccontextmanager
    async def stream_content(
        knol: Knol,
        fs: FileSystem,
        library_path: str = LIBRARY_DIR,
        mode: str = "rb",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        """
        Context manager for streaming knol content using fsspec's async capabilities.

        Usage:
            async with KnolUtils.stream_content(knol, fs) as stream:
                async for chunk in stream:
                    process(chunk)
        """
        content_path = f"{library_path}/{knol.id}/{CONTENT_FILENAME}"
        encoding = knol.metadata_consolidated.get("encoding", DEFAULT_ENCODING) if "t" in mode else None

        # Use fsspec's native async file operations
        # According to fsspec docs, async methods are prefixed with underscore
        # AsyncFileSystemWrapper should provide these methods
        if hasattr(fs, "_open"):
            try:
                # _open is the async version of open for AsyncFileSystem
                f = await fs._open(content_path, mode="rb")

                # Check if the file handle supports async operations
                if hasattr(f, "read") and asyncio.iscoroutinefunction(f.read):
                    try:

                        async def _stream_from_async_file():
                            while True:
                                chunk = await f.read(chunk_size)
                                if not chunk:
                                    break
                                if "t" in mode:
                                    yield chunk.decode(encoding or DEFAULT_ENCODING, errors=ENCODING_ERRORS)
                                else:
                                    yield chunk

                        yield _stream_from_async_file()
                        return
                    finally:
                        if hasattr(f, "close"):
                            if asyncio.iscoroutinefunction(f.close):
                                await f.close()
                            else:
                                f.close()
                else:
                    # File handle doesn't support async, close it and fall back
                    if hasattr(f, "close"):
                        f.close()
                    logger.debug("File handle doesn't support async operations")
            except Exception as e:
                logger.debug(f"Native async file operations failed: {e}")

        # Fallback: Read all and chunk in-memory (current behavior)
        adapter = FileSystemAdapter(fs)
        raw = await adapter.read_bytes(content_path)

        if "t" in mode:
            text = raw.decode(encoding or DEFAULT_ENCODING)

            async def _gen_text():
                i = 0
                n = len(text)
                while i < n:
                    j = min(n, i + chunk_size)
                    yield text[i:j]
                    i = j

            yield _gen_text()
        else:
            data = raw

            async def _gen_bytes():
                i = 0
                n = len(data)
                while i < n:
                    j = min(n, i + chunk_size)
                    yield data[i:j]
                    i = j

            yield _gen_bytes()

    @staticmethod
    @asynccontextmanager
    async def open_content(
        knol: Knol,
        fs: FileSystem,
        library_path: str = LIBRARY_DIR,
        mode: str = "rb",
    ):
        """
        Context manager for accessing knol content as file handle.

        Usage:
            async with KnolUtils.open_content(knol, fs, mode='rt') as f:
                content = await f.read()
        """
        content_path = f"{library_path}/{knol.id}/{CONTENT_FILENAME}"
        encoding = knol.metadata_consolidated.get("encoding", DEFAULT_ENCODING) if "t" in mode else None

        # Try to use fsspec's native async file operations if available
        # According to fsspec docs, AsyncFileSystemWrapper should provide _open
        if hasattr(fs, "_open"):
            try:
                # fsspec's _open returns an async context manager for async filesystems
                file_obj = await fs._open(content_path, mode="rb")

                # Create an adapter that handles text mode if needed
                class _AsyncFileAdapter:
                    def __init__(self, file_handle):
                        self._file = file_handle
                        self._encoding = encoding
                        self._mode = mode

                    async def read(self, n=-1):
                        data = await self._file.read(n)
                        if "t" in self._mode and isinstance(data, bytes):
                            return data.decode(self._encoding or DEFAULT_ENCODING, errors=ENCODING_ERRORS)
                        return data

                    async def close(self):
                        await self._file.close()

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        await self.close()

                yield _AsyncFileAdapter(file_obj)
                return
            except Exception as e:
                logger.debug(f"Native async file open not available: {e}")

        # Fallback: Read all into buffer (current behavior)
        adapter = FileSystemAdapter(fs)
        raw = await adapter.read_bytes(content_path)

        class _BufferAdapter:
            def __init__(self, buf: bytes | str):
                self._buf = buf
                self._pos = 0

            async def read(self, n=-1):
                if n is None or n < 0:
                    s = self._buf[self._pos :]
                    self._pos = len(self._buf)
                    return s
                s = self._buf[self._pos : self._pos + n]
                self._pos += len(s)
                return s

            async def close(self):
                return None

        if "t" in mode:
            text = raw.decode(encoding or DEFAULT_ENCODING)
            yield _BufferAdapter(text)
        else:
            yield _BufferAdapter(raw)

    @staticmethod
    async def read_content(
        knol: Knol,
        fs: FileSystem,
        library_path: str = LIBRARY_DIR,
        mode: str = "rb",
    ) -> Union[str, bytes]:
        """
        Read entire knol content into memory.
        Only use for small files!

        Returns:
            str if mode contains 't', bytes otherwise
        """
        async with KnolUtils.open_content(knol, fs, library_path, mode) as f:
            return await f.read()

    @staticmethod
    def create_metaparts_for_mime(
        mime_type: Optional[str],
        metadata: Dict[str, Any] | None,
    ) -> List[AnyMetaPart]:
        """
        Build metaparts from a schema-aligned metadata dict.
        - No renaming: `metadata` keys are expected to match your MetaPart model fields.
        - Always emits CommonMetaPart.
        - Emits one type-specific part based on the top-level media type from `mime_type`.
        - Emits ExtraMetaPart for any remaining keys.
        """
        meta = dict(metadata or {})  # copy so we can pop/filter safely
        parts: List[AnyMetaPart] = []

        # Helper: pick only keys present on a model, drop Nones
        def slice_for_model(model_cls):
            fields = model_cls.model_fields  # pydantic v2
            return {k: v for k, v in meta.items() if k in fields and v is not None}

        # Common first
        common_payload = slice_for_model(CommonMetaPart)
        if common_payload:
            parts.append(CommonMetaPart(**common_payload))
        else:
            # Always include CommonMetaPart, even if empty
            parts.append(CommonMetaPart())

        # Type-specific based on the *major* type
        type_payload = {}
        if mime_type:
            major = mime_type.split("/", 1)[0].lower()
            if major in TEXT_LIKE_TYPES:
                type_payload = slice_for_model(DocumentMetaPart)
                if type_payload:
                    parts.append(DocumentMetaPart(**type_payload))
            elif major == "image":
                type_payload = slice_for_model(ImageMetaPart)
                if type_payload:
                    parts.append(ImageMetaPart(**type_payload))
            elif major == "audio":
                type_payload = slice_for_model(AudioMetaPart)
                if type_payload:
                    parts.append(AudioMetaPart(**type_payload))
            elif major == "video":
                type_payload = slice_for_model(VideoMetaPart)
                if type_payload:
                    parts.append(VideoMetaPart(**type_payload))

        # Extra: anything not consumed by parts we added
        consumed = set().union(*(p.__class__.model_fields.keys() for p in parts))
        leftovers = {k: v for k, v in meta.items() if v is not None and k not in consumed}
        if leftovers:
            parts.append(ExtraMetaPart(data=leftovers))

        return parts

    # ---------------- Chunk descriptor I/O ----------------
    @staticmethod
    def _chunk_dir(library_dir: str, knol_id: str, chunker_name: str) -> str:
        return f"{library_dir}/{knol_id}/{CHUNKS_DIR_PREFIX}{chunker_name}"

    @staticmethod
    def _chunk_descriptor_path(library_dir: str, knol_id: str, chunker_name: str, index: int) -> str:
        # zero-pad for lexicographic ordering; 6 digits should suffice for most docs
        chunk_dir = KnolUtils._chunk_dir(library_dir, knol_id, chunker_name)
        filename = CHUNK_FILENAME_PATTERN.format(index=index, ext=DEFAULT_JSON_EXT)
        return f"{chunk_dir}/{filename}"

    @staticmethod
    async def write_chunk_descriptor(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        chunk: ChunkBase,
    ) -> None:
        """
        Persist a chunk descriptor JSON at library/<knol_id>/chunks_<chunker_name>/<index>.json
        """
        adapter = FileSystemAdapter(filesystem)
        dir_path = KnolUtils._chunk_dir(library_dir, knol_id, chunker_name)
        await adapter.makedirs(dir_path, exist_ok=True)
        path = KnolUtils._chunk_descriptor_path(library_dir, knol_id, chunker_name, chunk.index)
        data = chunk.model_dump_json(exclude={"text"}).encode(DEFAULT_ENCODING)
        await adapter.write_bytes(path, data)

    @staticmethod
    async def read_chunk_descriptor(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
    ) -> ChunkBase:
        adapter = FileSystemAdapter(filesystem)
        path = KnolUtils._chunk_descriptor_path(library_dir, knol_id, chunker_name, index)

        try:
            raw = await adapter.read_bytes(path)
            obj = json.loads(raw.decode(DEFAULT_ENCODING))
            # Validate against discriminated union AnyChunk
            return TypeAdapter(AnyChunk).validate_python(obj)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to read chunk descriptor from {path}: {e}")
            raise ValueError(f"Invalid chunk descriptor in {path}") from e

    @staticmethod
    async def list_chunk_descriptors(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
    ) -> List[ChunkBase]:
        adapter = FileSystemAdapter(filesystem)
        dir_path = KnolUtils._chunk_dir(library_dir, knol_id, chunker_name)

        if not await adapter.exists(dir_path):
            return []

        # list and read in lexical order
        entries = await adapter.ls(dir_path)
        files = sorted(
            e["name"] for e in entries if e.get("type") == "file" and e["name"].endswith(f".{DEFAULT_JSON_EXT}")
        )
        chunks: List[ChunkBase] = []

        for f in files:
            try:
                raw = await adapter.read_bytes(f)
                obj = json.loads(raw.decode(DEFAULT_ENCODING))
                chunks.append(TypeAdapter(AnyChunk).validate_python(obj))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Skipping invalid chunk descriptor {f}: {e}")
                continue

        return chunks

    # ---------------- Derived bytes & previews ----------------
    @staticmethod
    def _derived_bytes_dir(library_dir: str, knol_id: str, chunker_name: str) -> str:
        return f"{library_dir}/{knol_id}/{CHUNKS_DIR_PREFIX}{chunker_name}/{BYTES_SUBDIR}"

    @staticmethod
    def _previews_dir(library_dir: str, knol_id: str, chunker_name: str) -> str:
        return f"{library_dir}/{knol_id}/{CHUNKS_DIR_PREFIX}{chunker_name}/{PREVIEWS_SUBDIR}"

    @staticmethod
    def _derived_bytes_path(
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> str:
        bytes_dir = KnolUtils._derived_bytes_dir(library_dir, knol_id, chunker_name)
        filename = CHUNK_FILENAME_PATTERN.format(index=index, ext=ext)
        return f"{bytes_dir}/{filename}"

    @staticmethod
    def _preview_path(
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> str:
        preview_dir = KnolUtils._previews_dir(library_dir, knol_id, chunker_name)
        filename = CHUNK_FILENAME_PATTERN.format(index=index, ext=ext)
        return f"{preview_dir}/{filename}"

    @staticmethod
    async def write_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        data: bytes,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> str:
        adapter = FileSystemAdapter(filesystem)
        dir_path = KnolUtils._derived_bytes_dir(library_dir, knol_id, chunker_name)
        await adapter.makedirs(dir_path, exist_ok=True)
        path = KnolUtils._derived_bytes_path(library_dir, knol_id, chunker_name, index, ext)
        await adapter.write_bytes(path, data)
        return path

    @staticmethod
    async def read_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> bytes:
        adapter = FileSystemAdapter(filesystem)
        path = KnolUtils._derived_bytes_path(library_dir, knol_id, chunker_name, index, ext)
        return await adapter.read_bytes(path)

    @staticmethod
    async def delete_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> None:
        adapter = FileSystemAdapter(filesystem)
        path = KnolUtils._derived_bytes_path(library_dir, knol_id, chunker_name, index, ext)
        if await adapter.exists(path):
            await adapter.rm(path)

    @staticmethod
    async def write_preview(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        data: bytes,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> str:
        adapter = FileSystemAdapter(filesystem)
        dir_path = KnolUtils._previews_dir(library_dir, knol_id, chunker_name)
        await adapter.makedirs(dir_path, exist_ok=True)
        path = KnolUtils._preview_path(library_dir, knol_id, chunker_name, index, ext)
        await adapter.write_bytes(path, data)
        return path

    @staticmethod
    async def read_preview(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> bytes:
        adapter = FileSystemAdapter(filesystem)
        path = KnolUtils._preview_path(library_dir, knol_id, chunker_name, index, ext)
        return await adapter.read_bytes(path)

    @staticmethod
    async def delete_preview(
        filesystem: FileSystem,
        library_dir: str,
        knol_id: str,
        chunker_name: str,
        index: int,
        ext: str = DEFAULT_BINARY_EXT,
    ) -> None:
        adapter = FileSystemAdapter(filesystem)
        path = KnolUtils._preview_path(library_dir, knol_id, chunker_name, index, ext)
        if await adapter.exists(path):
            await adapter.rm(path)

    # ---------------- Convenience helpers ----------------
    @staticmethod
    def default_bytes_ext_for_chunk(chunk: ChunkBase) -> str:
        # Reasonable defaults for derived bytes
        if isinstance(chunk, AudioChunk):
            return "wav"  # PCM 16-bit mono WAV often used for embedders
        if isinstance(chunk, VideoChunk):
            return "mp4"  # h264 yuv420p for broad compatibility
        if isinstance(chunk, ImageChunk):
            return "png"  # lossless crops/thumbnails
        if isinstance(chunk, TextChunk):
            return DEFAULT_TEXT_EXT
        return DEFAULT_BINARY_EXT

    @staticmethod
    def default_preview_ext_for_chunk(chunk: ChunkBase) -> str:
        if isinstance(chunk, ImageChunk):
            return "jpg"
        if isinstance(chunk, VideoChunk):
            return "jpg"
        if isinstance(chunk, AudioChunk):
            return "png"  # e.g., waveform image
        return DEFAULT_TEXT_EXT

    @staticmethod
    async def write_chunk_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        data: bytes,
        ext: Optional[str] = None,
    ) -> str:
        return await KnolUtils.write_derived_bytes(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            data,
            ext or KnolUtils.default_bytes_ext_for_chunk(chunk),
        )

    @staticmethod
    async def read_chunk_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        ext: Optional[str] = None,
    ) -> bytes:
        return await KnolUtils.read_derived_bytes(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            ext or KnolUtils.default_bytes_ext_for_chunk(chunk),
        )

    @staticmethod
    async def delete_chunk_derived_bytes(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        ext: Optional[str] = None,
    ) -> None:
        await KnolUtils.delete_derived_bytes(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            ext or KnolUtils.default_bytes_ext_for_chunk(chunk),
        )

    @staticmethod
    async def write_chunk_preview(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        data: bytes,
        ext: Optional[str] = None,
    ) -> str:
        return await KnolUtils.write_preview(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            data,
            ext or KnolUtils.default_preview_ext_for_chunk(chunk),
        )

    @staticmethod
    async def read_chunk_preview(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        ext: Optional[str] = None,
    ) -> bytes:
        return await KnolUtils.read_preview(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            ext or KnolUtils.default_preview_ext_for_chunk(chunk),
        )

    @staticmethod
    async def delete_chunk_preview(
        filesystem: FileSystem,
        library_dir: str,
        chunker_name: str,
        chunk: ChunkBase,
        ext: Optional[str] = None,
    ) -> None:
        await KnolUtils.delete_preview(
            filesystem,
            library_dir,
            chunk.knol_id,
            chunker_name,
            chunk.index,
            ext or KnolUtils.default_preview_ext_for_chunk(chunk),
        )
