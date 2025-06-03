from functools import cached_property
import json
import logging
import mimetypes
from typing import Optional

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
        if not filesystem.exists(file_url):
            raise FileNotFoundError(f"File {file_url} not found in the filesystem.")

        meta_file = MediaUtils.get_meta_file_name(file_url)
        meta_dict = {}
        if filesystem.exists(meta_file):
            with filesystem.open(meta_file, "r") as f:
                try:
                    meta_data = f.read()
                    meta_dict = json.loads(meta_data)
                except Exception as e:
                    logging.error(f"Failed to read metadata for {file_url}: {e}")

        name = meta_dict.get("name", file_url.split("/")[-1])
        mimetype = meta_dict.get("mime", mimetypes.guess_type(file_url, strict=False)[0])
        encoding = meta_dict.get("encoding", "utf-8")

        return MediaLink(
            url=file_url,
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
