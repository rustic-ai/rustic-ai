from functools import cached_property
import json
import logging
import mimetypes
from typing import Optional
from urllib.parse import urlparse

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import BaseModel, Field, computed_field
import shortuuid

from ...messaging import JsonDict


class MediaUtils:
    @staticmethod
    def get_meta_file_name(filename: str) -> str:
        return f".{filename}.meta"

    @staticmethod
    def medialink_from_file(filesystem: FileSystem, file_url: str) -> "MediaLink":
        """
        Create a MediaLink from a file URL.
        """
        if not file_url:
            raise ValueError("file_url must be a non-empty string")

        # Determine if this is a remote URL (http/https or other scheme) vs a filesystem path
        # Files from filesystem are expected to be plain paths without protocol, or file:// URLs.
        try:
            parsed = urlparse(str(file_url))
        except Exception:
            parsed = None

        scheme = (parsed.scheme if parsed else "") or ""

        # Handle file:// scheme by converting to local path relative to provided filesystem
        if scheme == "file":
            local_path = parsed.path if parsed else str(file_url)
            file_path = local_path
        elif scheme in ("http", "https"):
            # Remote HTTP(S): don't use filesystem, just build a link
            name = (parsed.path.rsplit("/", 1)[-1] if parsed else str(file_url).rsplit("/", 1)[-1]) or str(file_url)
            mimetype = mimetypes.guess_type(name or str(file_url), strict=False)[0]
            return MediaLink(
                url=str(file_url),
                name=name,
                mimetype=mimetype,
                encoding=None,
                on_filesystem=False,
                metadata={},
            )
        elif scheme:
            # Other schemes (e.g., s3, gs, ftp): treat as remote link without filesystem checks
            name = (parsed.path.rsplit("/", 1)[-1] if parsed else str(file_url).rsplit("/", 1)[-1]) or str(file_url)
            mimetype = mimetypes.guess_type(name or str(file_url), strict=False)[0]
            return MediaLink(
                url=str(file_url),
                name=name,
                mimetype=mimetype,
                encoding=None,
                on_filesystem=False,
                metadata={},
            )
        else:
            # No scheme: treat as filesystem path
            file_path = str(file_url)

        # From here on, we have a filesystem path either from file:// or plain path.
        if not filesystem.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found in the filesystem.")

        meta_file = MediaUtils.get_meta_file_name(file_path)
        meta_dict = {}
        if filesystem.exists(meta_file):
            with filesystem.open(meta_file, "r") as f:
                try:
                    meta_data = f.read()
                    meta_dict = json.loads(meta_data)
                except Exception as e:
                    logging.error(f"Failed to read metadata for {file_path}: {e}")

        name = meta_dict.get("name", file_path.split("/")[-1])
        mimetype = meta_dict.get("mime", mimetypes.guess_type(file_path, strict=False)[0])
        encoding = meta_dict.get("encoding", "utf-8")

        return MediaLink(
            url=file_path,
            name=name,
            mimetype=mimetype,
            encoding=encoding,
            on_filesystem=True,
            metadata=meta_dict,
        )


class Media(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    name: Optional[str] = None
    metadata: Optional[JsonDict] = {}


class Document(Media):
    content: str
    mimetype: Optional[str] = "text/plain"
    encoding: Optional[str] = "utf-8"


class Image(Media):
    content: bytes
    mimetype: Optional[str] = "image/png"
    encoding: Optional[str] = "base64"


class Audio(Media):
    content: bytes
    mimetype: Optional[str] = "audio/wav"
    encoding: Optional[str] = "base64"


class Video(Media):
    content: bytes
    mimetype: Optional[str] = "video/mp4"
    encoding: Optional[str] = "base64"


class MediaLink(Media):
    url: str
    id: str = Field(default_factory=shortuuid.uuid)
    name: Optional[str] = None
    metadata: Optional[JsonDict] = {}
    mimetype: Optional[str] = None
    encoding: Optional[str] = None
    on_filesystem: Optional[bool] = False

    def get_mimetype(self) -> str:
        return self.mimetype or mimetypes.guess_type(self.get_filename())[0] or "application/octet-stream"

    def get_filename(self) -> str:
        return self.name or (self.url.split("/")[-1] if self.url else "unknown_file")

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def only_name(self) -> str:
        filename = self.get_filename()
        return filename.split(".")[0]
