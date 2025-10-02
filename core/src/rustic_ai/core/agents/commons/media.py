from functools import cached_property
from hashlib import sha256
import json
import logging
import mimetypes
from typing import Any, Optional
from urllib.parse import urlparse

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import BaseModel, Field, model_validator
import shortuuid

from ...messaging import JsonDict


class MediaUtils:
    @staticmethod
    def get_meta_file_name(filepath: str) -> str:
        filename = filepath.split("/")[-1]  # Strip any path
        return f".{filename}.meta"

    @staticmethod
    def medialink_from_file(filesystem: FileSystem, file_url: str) -> "MediaLink":
        """
        Create a MediaLink from a file URL.
        """
        if not file_url:
            raise ValueError("file_url must be a non-empty string")

        # Determine if this is a remote URL (http/https or other scheme) vs a filesystem path
        # Files from filesystem are expected to be plain paths without protocol, or file:/// URLs.
        try:
            parsed = urlparse(str(file_url))
        except Exception:
            parsed = None

        scheme = (parsed.scheme if parsed else "") or ""

        # Handle file:/// scheme by converting to local path relative to provided filesystem
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
        elif scheme and scheme != "":
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

        meta_file_name = MediaUtils.get_meta_file_name(file_path)
        meta_file = f"{file_path.rsplit('/', 1)[0]}/{meta_file_name}" if "/" in file_path else meta_file_name
        meta_dict = {}
        if filesystem.exists(meta_file):
            with filesystem.open(meta_file, "r") as f:
                try:
                    meta_data = f.read()
                    meta_dict = json.loads(meta_data)
                except Exception as e:
                    logging.error(f"Failed to read metadata for {file_path}: {e}")

        name = meta_dict.get("name", file_path.split("/")[-1])
        mimetype = meta_dict.get("mimetype", mimetypes.guess_type(file_path, strict=False)[0])
        encoding = meta_dict.get("encoding", "utf-8")
        id = meta_dict.get("id", shortuuid.uuid())

        size_in_bytes = 0
        content_hash = None

        if "size_in_bytes" in meta_dict and "content_hash" in meta_dict:
            size_in_bytes = meta_dict["size_in_bytes"]
            content_hash = meta_dict["content_hash"]
        else:
            try:
                with filesystem.open(file_path, "rb") as f:
                    content = f.read()
                    size_in_bytes = len(content)
                    content_hash = sha256(content).hexdigest().lower()
            except Exception as e:
                logging.error(f"Failed to read content for {file_path} to compute size and hash: {e}")

        return MediaLink(
            id=id,
            url=file_url,
            name=name,
            mimetype=mimetype,
            encoding=encoding,
            on_filesystem=True,
            metadata=meta_dict,
            size_in_bytes=size_in_bytes,
            content_hash=content_hash,
        )

    @staticmethod
    def media_from_media_link(filesystem: FileSystem, medialink: "MediaLink") -> "Media":
        """
        Load a Media (Document, Image, Audio, Video) from a MediaLink.
        """

        parsed = urlparse(str(medialink.url))

        if not medialink.on_filesystem or (parsed.scheme and parsed.scheme != "file"):
            raise ValueError("file_url must point to a file in the filesystem")

        if not filesystem.exists(parsed.path):
            raise FileNotFoundError(f"File {medialink.url} not found in the filesystem.")

        path = parsed.path

        with filesystem.open(path, "rb") as f:
            content = f.read()

        # Decode content if it's text
        if medialink.mimetype and medialink.mimetype.startswith("text/"):
            encoding = medialink.encoding or "utf-8"
            try:
                content = content.decode(encoding)
            except Exception as e:
                logging.error(f"Failed to decode content of {medialink.url} with encoding {encoding}: {e}")
                content = content.decode("utf-8", errors="replace")

            return Document(
                id=medialink.id,
                name=medialink.name,
                content=content,
                mimetype=medialink.mimetype,
                encoding=encoding,
                metadata=medialink.metadata,
            )
        elif medialink.mimetype and medialink.mimetype.startswith("image/"):
            return Image(
                id=medialink.id,
                name=medialink.name,
                content=content,
                mimetype=medialink.mimetype,
                encoding="base64",
                metadata=medialink.metadata,
            )
        elif medialink.mimetype and medialink.mimetype.startswith("audio/"):
            return Audio(
                id=medialink.id,
                name=medialink.name,
                content=content,
                mimetype=medialink.mimetype,
                encoding="base64",
                metadata=medialink.metadata,
            )
        elif medialink.mimetype and medialink.mimetype.startswith("video/"):
            return Video(
                id=medialink.id,
                name=medialink.name,
                content=content,
                mimetype=medialink.mimetype,
                encoding="base64",
                metadata=medialink.metadata,
            )
        else:
            return Binary(
                id=medialink.id,
                name=medialink.name,
                content=content,
                mimetype=medialink.mimetype or "application/octet-stream",
                encoding="utf-8",
                metadata=medialink.metadata,
            )

    @staticmethod
    def save_media_to_file(
        filesystem: FileSystem,
        media: "Media",
        dir: str = "media",
        filename: Optional[str] = None,
    ) -> "MediaLink":
        """
        Save a Media's content and metadata to the filesystem.
        """
        if not media or not hasattr(media, "content"):
            raise ValueError("media must be a non-empty Media object with content")

        filename = filename or media.name or media.id

        # Write content to file
        content = media.content
        # If content is str, encode to bytes using media.encoding or utf-8
        encoding = getattr(media, "encoding")
        if encoding is None and isinstance(content, str):
            encoding = "utf-8"
        elif encoding is None:
            encoding = "base64"

        # Prepare and write metadata
        meta_dict = media.metadata or {}

        mimetype = media.mimetype
        if mimetype is None:
            if filename and "." in filename:
                mimetype = mimetypes.guess_type(filename, strict=False)[0]

        if mimetype is None:
            mimetype = "application/octet-stream"

        return MediaUtils.save_content_to_file(
            filesystem=filesystem,
            id=media.id,
            filename=filename,
            media_name=media.name or filename,
            mimetype=mimetype,
            content=content,
            dir=dir,
            encoding=encoding,
            metadata=meta_dict,
        )

    @staticmethod
    def save_content_to_file(
        filesystem: FileSystem,
        id: str,
        filename: str,
        media_name: str,
        mimetype: str,
        content: bytes,
        dir: str = "media",
        encoding: str = "utf-8",
        metadata: JsonDict = {},
    ) -> "MediaLink":
        """
        Save a Media's content and metadata to the filesystem.
        """

        file_path = f"{dir}/{filename}"
        meta_file = MediaUtils.get_meta_file_name(filename)
        meta_file_path = f"{dir}/{meta_file}"

        # If content is str, encode to bytes using media.encoding or utf-8
        if isinstance(content, str):
            content = content.encode(encoding)

        shahash = sha256(content).hexdigest().lower()

        # Prepare and write metadata
        meta_dict = metadata
        meta_dict.update(
            {
                "id": id,
                "name": media_name,
                "mimetype": mimetype,
                "encoding": encoding,
                "size_in_bytes": len(content),
                "content_hash": shahash,
            }
        )

        with filesystem.transaction:
            with filesystem.open(file_path, "wb") as f:
                f.write(content)

            with filesystem.open(meta_file_path, "w") as f:
                f.write(json.dumps(meta_dict, indent=2))

        return MediaUtils.medialink_from_file(filesystem, file_path)

    @staticmethod
    def delete_media_file(filesystem: FileSystem, file_url: str) -> None:
        """
        Delete a media file and its metadata from the filesystem.
        """
        if not file_url:
            raise ValueError("file_url must be a non-empty string")

        parsed = urlparse(str(file_url))
        scheme = (parsed.scheme if parsed else "") or ""

        if scheme == "file":
            local_path = parsed.path if parsed else str(file_url)
            file_path = local_path
        elif scheme:
            raise ValueError("file_url must point to a file in the filesystem")
        else:
            file_path = str(file_url)

        if filesystem.exists(file_path):
            filesystem.rm(file_path)
        else:
            raise FileNotFoundError(f"File {file_path} not found in the filesystem.")

        meta_file_name = MediaUtils.get_meta_file_name(file_path)
        meta_file = f"{file_path.rsplit('/', 1)[0]}/{meta_file_name}" if "/" in file_path else meta_file_name
        if filesystem.exists(meta_file):
            filesystem.rm(meta_file)


class Media(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid)
    name: Optional[str] = None
    mimetype: Optional[str] = None
    metadata: Optional[JsonDict] = {}
    content_hash: Optional[str] = None
    size_in_bytes: Optional[int] = None


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


class Binary(Media):
    content: bytes
    mimetype: Optional[str] = "application/octet-stream"
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

    @cached_property
    def only_name(self) -> str:
        filename = self.get_filename()
        return filename.split(".")[0]

    @model_validator(mode="before")
    @classmethod
    def normalize_filesystem_url(cls, data: Any):
        if isinstance(data, dict):
            url = data.get("url")
            if data.get("on_filesystem") and isinstance(url, str) and url.startswith("file:///"):
                data = {**data, "url": url.replace("file://", "", 1)}
        return data
