"""Bounded source translation, native scope and lossless recall serialization."""

import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
from functools import lru_cache
import mimetypes
import threading
from typing import Any

import tiktoken
from uniko import IngestSource, Scope, Turn, Viewer

from .models import (
    IngestOutcome,
    MemoryRecordKind,
    MemoryScope,
    MemorySource,
    RecallItem,
)

MIME_ALIASES = {
    "text": "text/plain",
    "markdown": "text/markdown",
    "html": "text/html",
    "csv": "text/csv",
    "json": "application/json",
    "code": "text/plain",
    "pdf": "application/pdf",
}


def mime_type(value: str | None, path: str | None = None) -> str:
    return MIME_ALIASES.get(value or "", value) or mimetypes.guess_type(path or "")[0] or "text/plain"


@lru_cache(maxsize=1)
def tokenizer():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, disallowed_special=()))


class OperationGate:
    """One bounded gate per agent, independent of sessions and asyncio event loops."""

    def __init__(self):
        self.lock = threading.Lock()

    @asynccontextmanager
    async def hold(self):
        acquired = False
        try:
            while not acquired:
                acquired = self.lock.acquire(blocking=False)
                if not acquired:
                    await asyncio.sleep(0.005)
            yield
        finally:
            if acquired:
                self.lock.release()


def native_scope(spec: MemoryScope) -> Scope:
    scope = Scope()
    for name in ("sessions", "participants", "categories", "sources", "since", "until"):
        value = getattr(spec, name)
        if value is not None and (value or name == "sessions"):
            scope = getattr(scope, name)(value)
    if spec.include_superseded:
        scope = scope.include_superseded()
    if spec.viewer:
        scope = scope.as_viewer(Viewer(spec.viewer.participant_id, spec.viewer.teams, spec.viewer.orgs))
    return scope


def apply_provenance(builder: Any, spec: Any, kind: MemoryRecordKind) -> Any:
    is_turn = isinstance(builder, Turn) or type(builder).__name__ == "ToolCall"
    for field, method, default in (
        ("category", "category" if is_turn else "with_category", kind.value),
        ("source_id", "source" if is_turn else "with_source", None),
        ("revision_id", "revision" if is_turn else "with_revision", None),
    ):
        value = getattr(spec, field, None) or default
        if value is not None:
            builder = getattr(builder, method)(value)
    if getattr(spec, "visibility", None):
        if not is_turn:
            raise ValueError("Document visibility is unavailable in Uniko 0.5.1")
        builder = builder.visibility(spec.visibility)
    return builder


async def build_source(
    spec: MemorySource | dict, guild_fs: Any, max_bytes: int, byte_counts: list[int] | None = None
) -> IngestSource:
    spec = MemorySource.model_validate(spec)
    if spec.text is not None:
        data = spec.text.encode("utf-8")
    elif spec.base64_data is not None:
        if len(spec.base64_data) > 4 * ((max_bytes + 2) // 3):
            raise ValueError("Source exceeds byte limit")
        try:
            data = base64.b64decode(spec.base64_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid base64 source") from exc
    else:
        if guild_fs is None or spec.media_link is None:
            raise ValueError("Guild filesystem is required")
        path = spec.media_link.url
        if getattr(guild_fs, "asynchronous", False):
            # fsspec byte ranges bound the allocation even for unknown-size objects.
            data = await guild_fs._cat_file(path, start=0, end=max_bytes + 1)
        else:

            def read():
                with guild_fs.open(path, "rb") as stream:
                    return stream.read(max_bytes + 1)

            data = await asyncio.to_thread(read)
    if len(data) > max_bytes:
        raise ValueError("Source exceeds byte limit")
    if byte_counts is not None:
        byte_counts.append(len(data))
    hint = spec.path_hint or (
        (spec.media_link.metadata.get("source_uri") or spec.media_link.name or spec.media_link.url)
        if spec.media_link
        else None
    )
    mime = spec.mime_type or (spec.media_link.mimetype if spec.media_link else None)
    builder = IngestSource.from_bytes(data).with_mime(mime_type(mime, hint))
    if hint:
        builder = builder.with_path(hint)
    if spec.id:
        builder = builder.with_id(spec.id)
    return apply_provenance(builder, spec, MemoryRecordKind.EXTERNAL_EVIDENCE)


def ingest_outcome(outcome: Any, record_id: str | None = None) -> IngestOutcome:
    chunks = list(getattr(outcome, "chunk_node_ids", []) or [])
    failed = getattr(outcome, "extraction_failed", None)
    return IngestOutcome(
        artifact_id=getattr(outcome, "artifact_id", None),
        artifact_node_id=getattr(outcome, "artifact_node_id", None),
        chunk_node_ids=chunks,
        chunk_count=len(chunks),
        page_count=getattr(outcome, "page_count", None) or 0,
        page_node_ids=list(getattr(outcome, "page_node_ids", []) or []),
        block_node_ids=list(getattr(outcome, "block_node_ids", []) or []),
        was_deduplicated=bool(getattr(outcome, "was_deduplicated", False)),
        extraction_failed=failed,
        extraction_error=getattr(outcome, "extraction_error", None),
        success=not bool(failed),
        stored=getattr(outcome, "artifact_node_id", None) is not None,
        searchable=bool(chunks) and not bool(failed),
        record_id=record_id,
    )


def serialize_source(source: Any) -> dict:
    return {
        name: getattr(source, name, None)
        for name in ("kind", "message_id", "session_id", "call_id", "tool_name", "artifact_id", "chunk_id")
    }


def bound_items(
    items: list[RecallItem], item_limit: int, characters: int, token_budget: int | None
) -> tuple[list[RecallItem], bool]:
    retained: list[RecallItem] = []
    used_chars = used_tokens = 0
    truncated = False
    for item in items:
        if (
            len(retained) >= item_limit
            or used_chars >= characters
            or (token_budget is not None and used_tokens >= token_budget)
        ):
            truncated = True
            break
        text = item.content[: characters - used_chars]
        changed = text != item.content
        tokens = count_tokens(text) if changed else item.token_count
        if token_budget is not None and tokens > token_budget - used_tokens:
            encoded = tokenizer().encode(text, disallowed_special=())[: token_budget - used_tokens]
            # decoding a partial multi-byte code point must not emit a replacement character.
            text = tokenizer().decode_bytes(encoded).decode("utf-8", errors="ignore")
            tokens = count_tokens(text)
            changed = True
        context = (item.context or "")[: max(0, characters - used_chars - len(text))]
        context_tokens = count_tokens(context)
        if token_budget is not None and context_tokens > token_budget - used_tokens - tokens:
            encoded = tokenizer().encode(context, disallowed_special=())[: max(0, token_budget - used_tokens - tokens)]
            context = tokenizer().decode_bytes(encoded).decode("utf-8", errors="ignore")
            context_tokens = count_tokens(context)
        changed = changed or context != (item.context or "")
        method = "cl100k_base" if text != item.content else item.token_count_method
        if context:
            method += "+cl100k_base_context"
        item = item.model_copy(
            update={
                "content": text,
                "context": context or None,
                "token_count": tokens + context_tokens,
                "token_count_method": method,
            }
        )
        truncated = truncated or changed
        if text:
            retained.append(item)
            used_chars += len(text) + len(context)
            used_tokens += tokens + context_tokens
    return retained, truncated
