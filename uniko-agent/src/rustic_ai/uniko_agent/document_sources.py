"""Bounded immutable source snapshots and transport metadata preservation."""

import base64
from hashlib import sha256
from typing import Any

from rustic_ai.core.agents.commons.media import MediaLink

from .document_models import DocumentSourceOutcome
from .integration import mime_type, read_source_bytes
from .models import MemorySource


def normalize_document_attachment(attachment: dict[str, Any] | MediaLink) -> MemorySource:
    """Normalize a raw file part before a transport model drops filename/MIME.

    Accept a MediaLink or its dictionary, and the chat file-part shape with
    ``file_data`` (a filesystem URL or a base64 data URI). Remote URLs must be
    acquired and staged by the guild before calling this helper.
    """
    if isinstance(attachment, MediaLink):
        return MemorySource(media_link=attachment)
    wrapped = attachment.get("mediaLink") or attachment.get("media_link")
    if wrapped is not None:
        return MemorySource(media_link=MediaLink.model_validate(wrapped))
    if "file_url" in attachment:
        raw = attachment["file_url"]
        value = raw.get("url")
        link = MediaLink.model_validate(
            {
                **raw,
                "name": raw.get("name") or raw.get("filename"),
                "mimetype": raw.get("mimetype") or raw.get("mime_type"),
                "on_filesystem": raw.get("on_filesystem", isinstance(value, str) and value.startswith("file://")),
            }
        )
        return MemorySource(media_link=link)
    if attachment.get("type") == "file" or "file" in attachment:
        raw = attachment.get("file", attachment)
        value = raw.get("file_data")
        name = raw.get("filename") or raw.get("name")
        mime = raw.get("mime_type") or raw.get("mimetype")
        if not isinstance(value, str):
            raise ValueError("File part requires file_data")
        if value.startswith("data:"):
            header, separator, data = value.partition(",")
            if not separator or not header.endswith(";base64"):
                raise ValueError("Only base64 data URIs are supported")
            return MemorySource(base64_data=data, mime_type=mime or header[5:-7] or None, path_hint=name)
        link = MediaLink(
            url=value,
            name=name,
            mimetype=mime,
            encoding=raw.get("encoding"),
            metadata=raw.get("metadata") or {},
            on_filesystem=value.startswith("file://"),
        )
    else:
        value = attachment.get("url")
        link = MediaLink.model_validate(
            {
                **attachment,
                "on_filesystem": attachment.get(
                    "on_filesystem", isinstance(value, str) and value.startswith("file://")
                ),
            }
        )
    return MemorySource(media_link=link)


async def snapshot_document(
    source: MemorySource, corpus: str, guild_fs: Any, max_bytes: int, index: int
) -> tuple[MemorySource, DocumentSourceOutcome, int]:
    data = await read_source_bytes(source, guild_fs, max_bytes)
    link = source.media_link
    metadata = (link.metadata or {}) if link else {}
    uri = metadata.get("source_uri") or metadata.get("source_url") or metadata.get("url")
    locator = source.source_id or source.id or uri or (link.url if link else None) or source.path_hint
    hint = source.path_hint or (link.name or link.url if link else None)
    mime = mime_type(source.mime_type or (link.mimetype if link else None), hint)
    content_digest = sha256(data).hexdigest()
    logical = sha256(f"{corpus}\0{locator or content_digest}".encode()).hexdigest()
    source_id = "document:" + logical
    revision = sha256(f"{source_id}\0{mime}\0{content_digest}".encode()).hexdigest()
    record_id = "document:" + revision
    # Bytes, not a mutable filesystem link, cross the ingestion protocol.
    snapshot = MemorySource(
        base64_data=base64.b64encode(data).decode("ascii"),
        mime_type=mime,
        path_hint=hint,
        source_id=source_id,
        revision_id=revision,
        category=source.category,
    )
    outcome = DocumentSourceOutcome(
        index=index,
        source_id=source_id,
        revision_id=revision,
        record_id=record_id,
        name=link.name if link else source.path_hint,
        mime_type=mime,
        source_uri=str(uri or link.url) if link else (str(locator) if locator else None),
        encoding=link.encoding if link else None,
    )
    return snapshot, outcome, len(data)
