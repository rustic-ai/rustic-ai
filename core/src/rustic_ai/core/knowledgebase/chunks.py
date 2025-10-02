from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from .utils import now_utc


class ChunkBase(BaseModel):
    """
    Base class for content chunks derived from a `Knol` payload.
    Search backends may attach embeddings externally; this model is content-only.
    """

    model_config = ConfigDict(extra="forbid")

    # Discriminator for the union
    kind: Literal["text", "image", "audio", "video"]

    # Optional content bytes
    content_bytes: Optional[bytes] = Field(
        default=None, exclude=True, repr=False, description="Optional content bytes for this chunk"
    )

    producer_id: str = Field(description="Producer of this chunk")

    # Identity and lineage
    id: str = Field(description="Chunk identifier within the indexing domain")
    knol_id: str = Field(description="ID of the source Knol this chunk was derived from")
    index: int = Field(ge=0, description="Zero-based position of this chunk within its Knol")

    # Lifecycle
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    # Optional semantic hints
    name: Optional[str] = Field(default=None, description="Optional override label; if absent, display the Knol name")
    mimetype: Optional[str] = Field(default=None, description="IANA media type for this chunk, if specialized")

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_aware_utc(cls, v: datetime) -> datetime:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return v

    @field_validator("mimetype")
    @classmethod
    def _validate_mimetype(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "/" not in v or v.count("/") != 1:
            raise ValueError("mimetype must be like 'application/pdf'.")
        return v


class TextChunk(ChunkBase):
    kind: Literal["text"] = "text"

    # Content
    language: Optional[str] = Field(default=None, description="BCP-47 language tag for text")
    encoding: Optional[str] = Field(default=None, description="Text encoding if relevant")

    # Provenance within the document
    page_number: Optional[int] = Field(default=None, ge=1)
    start_char: Optional[int] = Field(default=None, ge=0)
    end_char: Optional[int] = Field(default=None, ge=0)

    @computed_field  # type: ignore[misc]
    @property
    def text(self) -> str:
        if self.content_bytes is None:
            return ""
        return self.content_bytes.decode(self.encoding or "utf-8", errors="ignore")

    @field_validator("end_char")
    @classmethod
    def _end_after_start(cls, v: Optional[int], info):
        if v is None:
            return v
        start = info.data.get("start_char")
        if start is not None and v < start:
            raise ValueError("end_char must be >= start_char")
        return v


class ImageChunk(ChunkBase):
    kind: Literal["image"] = "image"

    # Pixel-space region (x, y, width, height)
    bbox_xywh: Optional[Tuple[int, int, int, int]] = Field(default=None, description="Bounding box in pixels")
    page_number: Optional[int] = Field(default=None, ge=1)
    image_width_px: Optional[int] = Field(default=None, ge=1)
    image_height_px: Optional[int] = Field(default=None, ge=1)

    @field_validator("bbox_xywh")
    @classmethod
    def _valid_bbox(cls, v: Optional[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
        if v is None:
            return v
        x, y, w, h = v
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError("bbox_xywh must be non-negative origin with positive width and height")
        return v


class AudioChunk(ChunkBase):
    kind: Literal["audio"] = "audio"

    # Time bounds in milliseconds
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=0)

    # Audio hints
    sample_rate_hz: Optional[int] = Field(default=None, gt=0)
    channels: Optional[int] = Field(default=None, ge=1)

    @field_validator("end_ms")
    @classmethod
    def _end_after_start_ms(cls, v: Optional[int], info):
        if v is None:
            return v
        start = info.data.get("start_ms")
        if start is not None and v < start:
            raise ValueError("end_ms must be >= start_ms")
        return v


class VideoChunk(ChunkBase):
    kind: Literal["video"] = "video"

    # Time bounds in milliseconds
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=0)

    # Spatial hints at a representative frame
    frame_index: Optional[int] = Field(default=None, ge=0)
    bbox_xywh: Optional[Tuple[int, int, int, int]] = Field(default=None, description="Bounding box in pixels")

    video_width_px: Optional[int] = Field(default=None, ge=1)
    video_height_px: Optional[int] = Field(default=None, ge=1)
    frame_rate_fps: Optional[float] = Field(default=None, gt=0)

    @field_validator("end_ms")
    @classmethod
    def _vend_after_start_ms(cls, v: Optional[int], info):
        if v is None:
            return v
        start = info.data.get("start_ms")
        if start is not None and v < start:
            raise ValueError("end_ms must be >= start_ms")
        return v

    @field_validator("bbox_xywh")
    @classmethod
    def _vvalid_bbox(cls, v: Optional[Tuple[int, int, int, int]]) -> Optional[Tuple[int, int, int, int]]:
        if v is None:
            return v
        x, y, w, h = v
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError("bbox_xywh must be non-negative origin with positive width and height")
        return v


# Discriminated union for serialization and validation
AnyChunk = Annotated[
    Union[TextChunk, ImageChunk, AudioChunk, VideoChunk],
    Field(discriminator="kind"),
]
