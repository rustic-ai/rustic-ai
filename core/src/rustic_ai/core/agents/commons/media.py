from typing import Optional

import shortuuid
from pydantic import BaseModel, Field

from rustic_ai.core.messaging import JsonDict


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
