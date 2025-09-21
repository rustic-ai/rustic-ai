"""Filesystem adapter to abstract away implementation details."""

import logging

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

logger = logging.getLogger(__name__)


class FileSystemAdapter:
    """Adapter to abstract filesystem operations and handle different backend implementations."""

    def __init__(self, fs: FileSystem):
        self.fs = fs
        self._has_cat_file = hasattr(fs, "_cat_file")
        self._has_cat = hasattr(fs, "_cat")
        self._has_pipe_file = hasattr(fs, "_pipe_file")
        self._has_pipe = hasattr(fs, "_pipe")

    async def read_bytes(self, path: str) -> bytes:
        """Read file content as bytes."""
        if self._has_cat_file:
            try:
                return await self.fs._cat_file(path)
            except (AttributeError, NotImplementedError) as e:
                logger.debug(f"_cat_file failed for {path}: {e}")

        if self._has_cat:
            try:
                result = await self.fs._cat(path)
                if isinstance(result, dict):
                    # Some implementations return dict for multiple files
                    return result.get(path, b"")
                return result
            except (AttributeError, NotImplementedError) as e:
                logger.debug(f"_cat failed for {path}: {e}")

        raise NotImplementedError(f"Filesystem {type(self.fs).__name__} doesn't support async read operations")

    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to file."""
        if self._has_pipe_file:
            try:
                await self.fs._pipe_file(path, data)
                return
            except (AttributeError, NotImplementedError) as e:
                logger.debug(f"_pipe_file failed for {path}: {e}")

        if self._has_pipe:
            try:
                await self.fs._pipe({path: data})
                return
            except (AttributeError, NotImplementedError) as e:
                logger.debug(f"_pipe failed for {path}: {e}")

        raise NotImplementedError(f"Filesystem {type(self.fs).__name__} doesn't support async write operations")

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        if hasattr(self.fs, "_exists"):
            return await self.fs._exists(path)
        raise NotImplementedError(f"Filesystem {type(self.fs).__name__} doesn't support async exists")

    async def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directory recursively."""
        self.fs.makedirs(path, exist_ok=exist_ok)

    async def rm(self, path: str, recursive: bool = False) -> None:
        """Remove file or directory."""
        if hasattr(self.fs, "_rm"):
            await self.fs._rm(path, recursive=recursive)
        else:
            raise NotImplementedError(f"Filesystem {type(self.fs).__name__} doesn't support async rm")

    async def ls(self, path: str) -> list:
        """List directory contents."""
        if hasattr(self.fs, "_ls"):
            return await self.fs._ls(path)
        raise NotImplementedError(f"Filesystem {type(self.fs).__name__} doesn't support async ls")
