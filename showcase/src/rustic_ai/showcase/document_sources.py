"""Shared bounded upload acquisition for document-backed showcase guilds."""

import asyncio
import base64
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.utils.json_utils import JsonDict
from rustic_ai.uniko_agent import (
    DocumentSourceOutcome,
    MemorySource,
    normalize_document_attachment,
)
from rustic_ai.uniko_agent.integration import read_source_bytes

from .paper_banana_sources import HttpUploadSourceReader, source_uri


async def acquire_document_source(
    raw: dict,
    guild_fs,
    reader: HttpUploadSourceReader,
    budget: int,
    deadline: float,
    guild_id: str,
    staging_prefix: str = "documents/uploads/",
) -> tuple[MemorySource, int]:
    part = raw.get("mediaLink") or raw.get("media_link") or raw.get("file_url") or raw.get("file") or raw
    url = part.get("url") or part.get("file_data")
    supplied_id = part.get("source_id") or raw.get("source_id")
    logical: str | None
    uri: str | None
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        acquired = await reader.read(url, budget, deadline)
        name = (
            part.get("name")
            or part.get("filename")
            or raw.get("name")
            or acquired.name
            or PurePosixPath(urlsplit(url).path).name
        )
        mime = part.get("mimetype") or part.get("mime_type") or part.get("content_type") or acquired.mime_type
        data = acquired.data
        logical = part.get("source_id") or raw.get("source_id") or "upload:" + sha256(url.encode()).hexdigest()
        uri = source_uri(url)
    else:
        if isinstance(url, str) and not url.startswith("data:"):
            path = reader.staged_path(url, guild_id, getattr(guild_fs, "path", ""))
            raw = {
                "media_link": {
                    **part,
                    "url": path,
                    "name": part.get("name") or part.get("filename") or raw.get("name"),
                    "mimetype": part.get("mimetype") or part.get("mime_type") or part.get("content_type"),
                    "on_filesystem": True,
                    "metadata": {
                        **(part.get("metadata") or {}),
                        "source_uri": (part.get("metadata") or {}).get("source_uri") or source_uri(url),
                    },
                },
                "source_id": part.get("source_id") or raw.get("source_id"),
            }
        source = normalize_document_attachment(raw)
        data = await read_source_bytes(source, guild_fs, budget)
        link = source.media_link
        name = source.path_hint or (link.name or link.url if link else None)
        mime = source.mime_type or (link.mimetype if link else None)
        logical = source.source_id or source.id or supplied_id
        uri = source_uri(str((link.metadata or {}).get("source_uri") or link.url)) if link else None
        if link and logical is None:
            logical = "upload:" + sha256(link.url.encode()).hexdigest()
    name = str(name)[:512] if name else None
    if len(data) > budget:
        raise ValueError("Source exceeds budget")
    if mime and (not isinstance(mime, str) or len(mime) > 128):
        raise ValueError("Invalid MIME")
    if uri is None:
        return MemorySource(
            base64_data=base64.b64encode(data).decode(), path_hint=name, mime_type=mime, source_id=logical
        ), len(data)
    path = staging_prefix + uuid4().hex + PurePosixPath(name or "source.bin").suffix[:12]

    def write():
        with guild_fs.open(path, "wb") as stream:
            stream.write(data)

    await asyncio.to_thread(write)
    return MemorySource(
        media_link=MediaLink(url=path, name=name, mimetype=mime, on_filesystem=True, metadata={"source_uri": uri}),
        source_id=logical,
    ), len(data)


def normalize_showcase_input(payload: JsonDict, format: str) -> tuple[str | None, list[dict]]:
    if format.endswith("FilesWithTextFormat"):
        text, attachments = payload.get("text") or "", payload.get("files", [])
    elif format.endswith("TextFormat"):
        text, attachments = payload.get("text", ""), []
    else:
        users = [
            message
            for message in payload.get("messages", [])
            if isinstance(message, dict) and message.get("role") == "user"
        ]
        if not users:
            raise ValueError("Missing user input")
        content = users[-1].get("content")
        if isinstance(content, str):
            text, attachments = content, []
        elif isinstance(content, list) and len(content) <= 64:
            texts = [part["text"] for part in content if isinstance(part, dict) and part.get("type") == "text"]
            if any(not isinstance(value, str) for value in texts) or sum(map(len, texts)) > 4000:
                raise ValueError("Invalid instruction")
            text = "\n".join(texts)
            attachments = [
                part for part in content if isinstance(part, dict) and part.get("type") in {"file_url", "file"}
            ]
            if len(texts) + len(attachments) != len(content):
                raise ValueError("Unsupported input part")
        else:
            raise ValueError("Invalid user content")
    if (
        not isinstance(text, str)
        or len(text) > 4000
        or not isinstance(attachments, list)
        or len(attachments) > 32
        or any(not isinstance(part, dict) for part in attachments)
    ):
        raise ValueError("Invalid input")
    instruction = text.strip() or None
    if instruction is None and not attachments:
        raise ValueError("Empty request")
    return instruction, attachments


def document_source_info(raw: dict, index: int) -> DocumentSourceOutcome:
    part = raw.get("mediaLink") or raw.get("media_link") or raw.get("file_url") or raw.get("file") or raw
    if not isinstance(part, dict):
        return DocumentSourceOutcome(index=index)
    name = part.get("name") or part.get("filename") or raw.get("name")
    mime = part.get("mimetype") or part.get("mime_type") or part.get("content_type")
    url = part.get("url") or part.get("file_data")
    uri = None
    if isinstance(url, str) and len(url) <= 4096 and not url.startswith("data:"):
        try:
            uri = source_uri(url)
        except ValueError:
            pass
    return DocumentSourceOutcome(
        index=index,
        name=name[:512] if isinstance(name, str) else None,
        mime_type=mime[:128] if isinstance(mime, str) else None,
        source_uri=uri,
    )
