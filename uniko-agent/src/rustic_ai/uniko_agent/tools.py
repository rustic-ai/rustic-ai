"""Narrow configuration diagnostics and authorized deterministic source tools."""

import base64
from importlib.metadata import version
import logging
from typing import Any, AsyncContextManager

import uniko

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import ProcessContext

from .config import MemoryAgentConfig
from .integration import native_scope
from .models import (
    CapabilityRequest,
    EffectiveConfigRequest,
    MemoryAgentError,
    MemoryDiagnostics,
    MemoryHealthRequest,
    MemoryScope,
    SourceReadRequest,
    SourceResponse,
    SourceSearchRequest,
)
from .resolver import runtime_info


def snapshot(value: Any, fields: tuple[str, ...]) -> dict:
    return {key: getattr(value, key, None) for key in fields}


def literal(value: str) -> str:
    # Cypher string quoting; identifiers and property names are fixed below.
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def redact(value: Any, key: str = "") -> Any:
    if any(word in key.lower() for word in ("secret", "token", "password", "key", "provider_options")) and key not in {
        "recall_token_budget",
        "max_chunk_tokens",
        "min_chunk_tokens",
        "chunk_overlap_tokens",
        "chunk_context_max_tokens",
    }:
        return "<redacted>"
    if isinstance(value, dict):
        return {name: redact(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class MemoryTools:
    config: MemoryAgentConfig

    def _authorized_scope(self, ctx: ProcessContext, spec: MemoryScope) -> MemoryScope:
        raise NotImplementedError

    def _session_lock(self, session_id: str, handle=None) -> AsyncContextManager:
        raise NotImplementedError

    @agent.processor(EffectiveConfigRequest, depends_on=["uniko"])
    async def effective_config(self, ctx: ProcessContext[EffectiveConfigRequest], uniko: uniko.Agent):
        runtime = runtime_info(uniko)
        if runtime is None:
            ctx.send(MemoryDiagnostics(unknown=["effective_native_config"]))
            return
        ctx.send(
            MemoryDiagnostics(
                configured=redact(runtime["instance"].config()),
                observed={"streaming": runtime["streaming"]},
                unknown=["effective_execution_provider", "model_warmup", "adapter_availability"],
            )
        )

    @agent.processor(CapabilityRequest, depends_on=["uniko"])
    async def capabilities(self, ctx: ProcessContext[CapabilityRequest], uniko: uniko.Agent):
        runtime = runtime_info(uniko)
        ctx.send(
            MemoryDiagnostics(
                configured={"streaming": runtime["streaming"] if runtime else None},
                observed={
                    "sdk": version("uniko"),
                    "recall_overrides": ["limit", "token_budget", "min_score", "reranker", "reference_ts"],
                    "document_visibility": False,
                    "answer_max_tokens": False,
                    "phase1_only_control": False,
                    "structured_experience": True,
                    "atomic_units": True,
                    "structured_owner": "authenticated_reporting_sender",
                    "native_registration": "registered_agent_with_organization_membership",
                },
                unknown=["effective_execution_provider", "ocr", "multimodal_adapters", "sparse_and_colbert_readiness"],
            )
        )

    @agent.processor(MemoryHealthRequest, depends_on=["uniko"])
    async def memory_health(self, ctx: ProcessContext[MemoryHealthRequest], uniko: uniko.Agent):
        runtime = runtime_info(uniko)
        health = runtime["instance"].health() if runtime else None
        observed: dict[str, Any] = {"pipeline_available": health is not None}
        if runtime is not None:
            observed["active_operations"] = runtime["runtime"].active
            observed["managed_handles"] = len(runtime["runtime"].handles)
            observed["structured_receipts"] = "at_most_once_with_unknown_outcome"
        if health is not None:
            observed.update(snapshot(health, ("uptime_secs", "llm_circuit")))
            for name in ("ingest", "consolidation"):
                observed[name] = snapshot(
                    getattr(health, name),
                    ("status", "queue_depth", "queue_capacity", "items_processed", "items_failed", "avg_latency_ms"),
                )
        ctx.send(MemoryDiagnostics(observed=observed, unknown=["model_readiness", "dead_letter_queue"]))

    async def _source_allowed(self, uniko: uniko.Agent, kind: str, identifier: str, spec: MemoryScope) -> bool:
        # query_in supplies $allow but does not insert predicates: explicitly
        # constrain chunk/message nodes before dereferencing a source.
        label, prop = ("Message", "message_id") if kind == "message" else ("Artifact", "artifact_id")
        if kind == "artifact" and not spec.include_superseded:
            current = await uniko.query(
                f"MATCH (n:Artifact {{artifact_id: {literal(identifier)}}}) "
                "WHERE n.superseded_at IS NULL RETURN id(n) AS nid LIMIT 1"
            )
            if not current:
                return False
        query = f"MATCH (n:{label} {{{prop}: {literal(identifier)}}})"
        active = any(
            (spec.sessions is not None, spec.participants, spec.categories, spec.sources, spec.since, spec.until)
        )
        if kind == "message":
            query += " WHERE id(n) IN $allow" if active else ""
        else:
            query += "-[:HAS_CHUNK]->(c:Chunk) WHERE id(c) IN $allow" if active else ""
        rows = await uniko.query_in(query + " RETURN id(n) AS nid LIMIT 1", native_scope(spec))
        if (
            not rows
            and kind == "artifact"
            and spec.sessions is not None
            and not any((spec.participants, spec.categories, spec.sources, spec.since, spec.until))
        ):
            # An artifact without extracted chunks may still retain its original
            # bytes. Authorize its actual session anchor without requiring it to
            # be searchable. More restrictive dimensions continue to fail closed.
            sessions = "[" + ",".join(literal(sid) for sid in spec.sessions) + "]"
            for anchor in ("(s:Session)", "(:Message)-[:IN_SESSION]->(s:Session)"):
                rows = await uniko.query(
                    f"MATCH (n:Artifact {{artifact_id: {literal(identifier)}}})-[:ATTACHED_TO]->{anchor} "
                    f"WHERE s.session_id IN {sessions} RETURN id(n) AS nid LIMIT 1"
                )
                if rows:
                    break
        if not rows:
            return False
        message = await uniko.data.message(identifier) if kind == "message" else None
        if kind == "artifact":
            artifact = await uniko.data.artifact(identifier)
            if artifact is None:
                return False
            if artifact.attached_to_message:
                message = await uniko.data.message(artifact.attached_to_message)
                if message is None:
                    return False
        if message is not None:
            visibility = getattr(message, "visibility", None)
            if visibility:
                viewer = spec.viewer
                if viewer is None:
                    # Native resolver-level policy still applies; explicit
                    # visibility cannot be elevated by omitting a viewer.
                    return False
                permitted = {
                    f"private:{viewer.participant_id}",
                    *[f"team:{x}" for x in viewer.teams],
                    *[f"org:{x}" for x in viewer.orgs],
                }
                if visibility not in permitted:
                    return False
        return True

    @agent.processor(SourceSearchRequest, depends_on=["uniko"])
    async def source_search(self, ctx: ProcessContext[SourceSearchRequest], uniko: uniko.Agent):
        try:
            spec = self._authorized_scope(ctx, ctx.payload.scope)
            results: dict[str, dict[str, Any]] = {}
            async with self._session_lock("*", uniko):
                sessions: list[str | None] = list(spec.sessions) if spec.sessions is not None else [None]
                for session in sessions:
                    hits = await uniko.sources.search(ctx.payload.query, limit=ctx.payload.limit, session_id=session)
                    for hit in hits:
                        if await self._source_allowed(uniko, hit.source_kind, hit.source_id, spec):
                            results.setdefault(
                                hit.chunk_id,
                                snapshot(
                                    hit,
                                    (
                                        "source_kind",
                                        "source_id",
                                        "chunk_id",
                                        "chunk_index",
                                        "address",
                                        "start",
                                        "end",
                                        "text",
                                        "context",
                                        "score",
                                        "session_id",
                                        "call_id",
                                        "tool_name",
                                    ),
                                ),
                            )
            retained: list[dict[str, Any]] = []
            used = 0
            truncated = False
            for candidate in sorted(results.values(), key=lambda hit: hit["score"], reverse=True):
                if len(retained) >= ctx.payload.limit or used >= ctx.payload.max_characters:
                    truncated = True
                    break
                hit_data = dict(candidate)
                for field in ("text", "context"):
                    value = hit_data.get(field) or ""
                    clipped = value[: ctx.payload.max_characters - used]
                    truncated = truncated or clipped != value
                    hit_data[field] = clipped if value else hit_data.get(field)
                    used += len(clipped)
                retained.append(hit_data)
            ctx.send(SourceResponse(results=retained, truncated=truncated))
        except ValueError:
            logging.getLogger(__name__).warning("Source operation rejected")
            ctx.send_error(
                MemoryAgentError(error="source_read_failed", message="The authorized source could not be read")
            )
        except Exception:
            logging.getLogger(__name__).exception("Authorized source operation failed")
            ctx.send_error(
                MemoryAgentError(error="source_read_failed", message="The authorized source could not be read")
            )

    async def _read_source(self, uniko: uniko.Agent, req: SourceReadRequest, spec: MemoryScope) -> SourceResponse:
        if not await self._source_allowed(uniko, req.source_kind, req.source_id, spec):
            return SourceResponse(available=False)
        if req.operation == "original":
            data = await uniko.data.artifact_bytes(req.source_id)
            if data is None:
                return SourceResponse(available=False)
            if len(data) > self.config.max_source_bytes:
                raise ValueError("Original artifact exceeds source limit")
            return SourceResponse(base64_data=base64.b64encode(data).decode("ascii"))
        value: Any
        if req.operation == "outline":
            value = await uniko.sources.outline(
                req.source_kind, req.source_id, depth=req.depth, max_entries=req.max_entries
            )
            if value is None:
                return SourceResponse(available=False)
            result = snapshot(value, ("source_kind", "source_id", "format", "total_bytes", "total_lines", "truncated"))
            result["entries"] = [
                snapshot(entry, ("address", "kind", "summary", "start", "end", "depth")) for entry in value.entries
            ]
        else:
            value = await uniko.sources.read(
                req.source_kind,
                req.source_id,
                address=req.address,
                bytes=(
                    req.bytes
                    if any((req.address, req.bytes, req.lines, req.chunks))
                    else (0, self.config.max_source_bytes)
                ),
                lines=req.lines,
                chunks=req.chunks,
                max_tokens=req.max_tokens,
            )
            if value is None:
                return SourceResponse(available=False)
            result = snapshot(
                value,
                (
                    "source_kind",
                    "source_id",
                    "text",
                    "start",
                    "end",
                    "first_line",
                    "last_line",
                    "truncated",
                    "next_bytes",
                ),
            )
        return SourceResponse(result=result)

    @agent.processor(SourceReadRequest, depends_on=["uniko"])
    async def source_read(self, ctx: ProcessContext[SourceReadRequest], uniko: uniko.Agent):
        try:
            spec = self._authorized_scope(ctx, ctx.payload.scope)
            async with self._session_lock("*", uniko):
                response = await self._read_source(uniko, ctx.payload, spec)
            ctx.send(response)
        except ValueError:
            logging.getLogger(__name__).warning("Source operation rejected")
            ctx.send_error(
                MemoryAgentError(error="source_read_failed", message="The authorized source could not be read")
            )
        except Exception:
            logging.getLogger(__name__).exception("Authorized source operation failed")
            ctx.send_error(
                MemoryAgentError(error="source_read_failed", message="The authorized source could not be read")
            )
