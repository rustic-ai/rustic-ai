from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from .metadata import AnyMetaPart, consolidate_metaparts
from .utils import now_utc

Vector = Sequence[float]
# -------------------- Provenance --------------------


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system: Optional[str] = Field(default=None, description="Origin system (e.g., 'SharePoint').")
    source_uri: Optional[AnyUrl] = Field(default=None, description="URI of the original resource in its source.")
    was_derived_from: Optional[str] = None
    was_generated_by: Optional[str] = None
    was_attributed_to: Optional[str] = None
    had_primary_source: Optional[str] = None


# -------------------- Knol model --------------------


class Knol(BaseModel):
    """
    Source-of-truth object for an ingested resource.
    Not the searchable unit; chunks/embeddings/graph live elsewhere and reference `id`.
    """

    # Identity
    id: str
    name: str

    # Type & location
    mimetype: Optional[str] = Field(default=None, description="IANA media type.")
    size_in_bytes: Optional[int] = Field(default=None, ge=0)

    # Lifecycle & integrity
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    content_hash: Optional[str] = Field(default=None, description="64-char sha256 hex, if available.")
    license: Optional[str] = None
    language: Optional[str] = Field(default=None, description="BCP-47 tag for text resources.")

    # Provenance & Metadata (as a list of parts)
    provenance: Provenance = Field(default_factory=Provenance)
    metaparts: List[AnyMetaPart] = Field(default_factory=list)

    # Consolidated metadata (computed on demand)
    @computed_field  # type: ignore[misc]
    @property
    def metadata_consolidated(self) -> Dict[str, Any]:
        return consolidate_metaparts(self.metaparts, policy="priority")

    # ---- Validators ----
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

    @field_validator("content_hash")
    @classmethod
    def _validate_content_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        h = v.lower()
        if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise ValueError("content_hash must be 64-char lowercase hex (sha256).")
        return h

    @model_validator(mode="after")
    def _check_time_order(self) -> "Knol":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at.")
        return self
