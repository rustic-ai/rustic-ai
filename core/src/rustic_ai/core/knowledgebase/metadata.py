from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import now_utc


class MetaPartBase(BaseModel):
    """
    One extractor/ingestor's structured view over some slice of metadata.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["common", "document", "image", "video", "audio", "extra"]
    provider: Optional[str] = Field(default=None, description="Emitter of this part (e.g., 'ocr', 'exif').")
    collected_at: datetime = Field(default_factory=now_utc, description="UTC time of collection.")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    priority: int = Field(default=0, description="Higher wins on conflicts when policy=priority.")

    def canonical_payload(self) -> Dict[str, Any]:
        """
        Return only the domain keys (exclude identity/housekeeping fields).
        """
        return self.model_dump(
            exclude_none=True,
            exclude={"kind", "provider", "collected_at", "confidence", "priority"},
        )

    @field_validator("collected_at", mode="before")
    @classmethod
    def _aware_utc(cls, v: datetime) -> datetime:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return v


class CommonMetaPart(MetaPartBase):
    kind: Literal["common"] = "common"
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    author: Optional[str] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    capture_datetime: Optional[datetime] = None
    source_filename: Optional[str] = None
    source_collection: Optional[str] = None

    @field_validator("capture_datetime", mode="before")
    @classmethod
    def _cap_aware(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: List[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for t in v:
            tt = t.strip()
            if tt and tt.lower() not in seen:
                seen.add(tt.lower())
                out.append(tt)
        return out


class DocumentMetaPart(MetaPartBase):
    kind: Literal["document"] = "document"
    page_count: Optional[int] = Field(default=None, ge=0)
    page_numbers: List[int] = Field(default_factory=list)

    @field_validator("page_numbers")
    @classmethod
    def _valid_pages(cls, v: List[int]) -> List[int]:
        return [p for p in v if p >= 1]


class ImageMetaPart(MetaPartBase):
    kind: Literal["image"] = "image"
    image_width_px: Optional[int] = Field(default=None, ge=1)
    image_height_px: Optional[int] = Field(default=None, ge=1)
    image_dpi_x: Optional[int] = Field(default=None, ge=1)
    image_dpi_y: Optional[int] = Field(default=None, ge=1)
    image_color_space: Optional[str] = None  # 'RGB','CMYK',...
    image_bit_depth: Optional[int] = Field(default=None, ge=1)
    image_orientation: Optional[str] = None  # 'landscape','portrait','square' or EXIF orientation


class VideoMetaPart(MetaPartBase):
    kind: Literal["video"] = "video"
    video_width_px: Optional[int] = Field(default=None, ge=1)
    video_height_px: Optional[int] = Field(default=None, ge=1)
    video_frame_rate_fps: Optional[float] = Field(default=None, gt=0)
    video_bitrate_kbps: Optional[int] = Field(default=None, ge=0)
    video_codec: Optional[str] = None
    video_aspect_ratio: Optional[str] = Field(default=None, description="e.g., '16:9'")

    @field_validator("video_aspect_ratio")
    @classmethod
    def _ratio_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        a = v.split(":")
        if len(a) != 2 or not all(s.isdigit() and int(s) > 0 for s in a):
            raise ValueError("video_aspect_ratio must look like '16:9'.")
        return v


class AudioMetaPart(MetaPartBase):
    kind: Literal["audio"] = "audio"
    audio_sample_rate_hz: Optional[int] = Field(default=None, gt=0)
    audio_channels: Optional[int] = Field(default=None, ge=1)
    audio_channel_layout: Optional[str] = None  # 'mono','stereo','5.1',...
    audio_bit_depth: Optional[int] = Field(default=None, gt=0)
    audio_bitrate_kbps: Optional[int] = Field(default=None, ge=0)
    audio_codec: Optional[str] = None


class ExtraMetaPart(MetaPartBase):
    """
    Escape hatch for source-specific fields that don't warrant a schema yet.
    """

    kind: Literal["extra"] = "extra"
    data: Dict[str, Any] = Field(default_factory=dict)

    def canonical_payload(self) -> Dict[str, Any]:
        # use provided payload directly (still exclude housekeeping via override)
        return {k: v for k, v in self.data.items() if v is not None}


# Discriminated union for serialization and validation
AnyMetaPart = Annotated[
    Union[CommonMetaPart, DocumentMetaPart, ImageMetaPart, VideoMetaPart, AudioMetaPart, ExtraMetaPart],
    Field(discriminator="kind"),
]


# ---------- Consolidation ----------
ConsolidationPolicy = Literal["priority", "newest", "highest_confidence", "lww"]


class MetaPartScore:
    """Encapsulates scoring logic for MetaParts."""

    def __init__(self, part: MetaPartBase, index: int):
        self.priority = part.priority
        self.collected_at = part.collected_at
        self.confidence = part.confidence if part.confidence is not None else -1.0
        self.index = index

    def compare_by_policy(self, other: "MetaPartScore", policy: ConsolidationPolicy) -> bool:
        """Compare two scores based on the specified policy."""
        comparisons = {
            "priority": self._compare_priority,
            "newest": self._compare_newest,
            "highest_confidence": self._compare_confidence,
            "lww": self._compare_index,
        }

        # Apply primary policy comparison
        comparison_func = comparisons.get(policy, self._compare_priority)
        result = comparison_func(other)

        if result is not None:
            return result

        # Apply fallback comparisons in order
        for fallback in ["priority", "newest", "highest_confidence", "lww"]:
            if fallback != policy:
                result = comparisons[fallback](other)
                if result is not None:
                    return result

        return False

    def _compare_priority(self, other: "MetaPartScore") -> Optional[bool]:
        if self.priority != other.priority:
            return self.priority > other.priority
        return None

    def _compare_newest(self, other: "MetaPartScore") -> Optional[bool]:
        if self.collected_at != other.collected_at:
            return self.collected_at > other.collected_at
        return None

    def _compare_confidence(self, other: "MetaPartScore") -> Optional[bool]:
        if self.confidence != other.confidence:
            return self.confidence > other.confidence
        return None

    def _compare_index(self, other: "MetaPartScore") -> Optional[bool]:
        if self.index != other.index:
            return self.index > other.index
        return None


def consolidate_metaparts(
    parts: List[AnyMetaPart],
    policy: ConsolidationPolicy = "priority",
) -> Dict[str, Any]:
    """
    Merge all MetaParts into a single flat dict of canonical keys.
    Conflict resolution order:
      - policy == 'priority'            -> higher priority wins
      - policy == 'newest'              -> later collected_at wins
      - policy == 'highest_confidence'  -> higher confidence wins (None treated as -1)
      - policy == 'lww'                 -> last in list wins
    Ties fall back to the next criterion in this order: priority -> newest -> confidence -> lww.
    """
    consolidated: Dict[str, tuple[Any, MetaPartScore]] = {}

    for idx, part in enumerate(parts):
        score = MetaPartScore(part, idx)
        payload = part.canonical_payload()

        for key, value in payload.items():
            if value is None:
                continue

            if key not in consolidated:
                consolidated[key] = (value, score)
            else:
                _, existing_score = consolidated[key]
                if score.compare_by_policy(existing_score, policy):
                    consolidated[key] = (value, score)

    return {k: v for k, (v, _) in consolidated.items()}
