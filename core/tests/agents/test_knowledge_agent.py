import os
from pathlib import Path

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.agents.indexing.knowledge_agent import (
    CatalogMediaLinks,
    CatalogMediaResults,
    IndexMediaLinks,
    IndexMediaResults,
    KBSearchRequest,
    KBSearchResults,
    KnowledgeAgent,
)
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    GUILD_GLOBAL,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.knowledgebase.agent_config import KnowledgeAgentConfig
from rustic_ai.core.knowledgebase.kbindex_backend_memory import (
    InMemoryKBIndexBackendResolver,
)
from rustic_ai.core.knowledgebase.pipeline import (
    ChunkerRef,
    EmbedderRef,
    PipelineSpec,
    SchemaRef,
    StorageSpec,
    TargetSelector,
)
from rustic_ai.core.knowledgebase.plugins import RerankerPlugin
from rustic_ai.core.knowledgebase.query import (
    BoolFilter,
    FilterClause,
    FilterOp,
    FusionStrategy,
    HybridOptions,
    RerankOptions,
    RerankStrategy,
    SearchQuery,
)
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def dependency_map(tmp_path):
    base = Path(tmp_path) / "kb_agent_tests"
    return {
        "filesystem": DependencySpec(
            class_name=FileSystemResolver.get_qualified_class_name(),
            properties={
                "path_base": str(base),
                "protocol": "file",
                "storage_options": {"auto_mkdir": True},
                "asynchronous": True,
            },
        ),
        "kb_backend": DependencySpec(
            class_name=InMemoryKBIndexBackendResolver.get_qualified_class_name(),
            properties={},
        ),
    }


@pytest.fixture
def agent_spec():
    return (
        AgentBuilder(KnowledgeAgent)
        .set_id("knowledge_agent")
        .set_name("Knowledge Agent")
        .set_description("Indexes media and performs KB search")
        .build_spec()
    )


def _build_message(generator, payload, fmt):
    return Message(
        id_obj=generator.get_id(Priority.NORMAL),
        topics="default_topic",
        sender=AgentTag(id="tester", name="tester"),
        payload=payload,
        format=fmt,
    )


def _prepare_media_on_fs(agent, dependency_map, relative_path: str, content: bytes) -> None:
    base_path = Path(dependency_map["filesystem"].properties["path_base"])  # type: ignore[index]
    root = base_path / agent.guild_id / GUILD_GLOBAL
    os.makedirs(root, exist_ok=True)
    (root / relative_path).write_bytes(content)


class TestKnowledgeAgent:

    def test_catalog_media_success(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "sample.txt", b"Hello KB!\nSecond line.")

        media = [MediaLink(id="m1", url="file:///sample.txt", name="sample.txt", mimetype="text/plain")]
        msg = _build_message(
            generator,
            CatalogMediaLinks(media=media).model_dump(),
            get_qualified_class_name(CatalogMediaLinks),
        )

        agent._on_message(msg)

        assert len(results) >= 1
        payload = CatalogMediaResults.model_validate(results[-1].payload)
        assert len(payload.results) == 1
        st = payload.results[0]
        assert getattr(st, "status", None) in {"stored", "indexed", "indexing"} or getattr(st, "knol", None)

    def test_catalog_media_missing_file_failure(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        media = [MediaLink(id="m404", url="file:///does_not_exist.txt", name="nope", mimetype="text/plain")]
        msg = _build_message(
            generator,
            CatalogMediaLinks(media=media).model_dump(),
            get_qualified_class_name(CatalogMediaLinks),
        )

        agent._on_message(msg)

        assert len(results) >= 1
        payload = CatalogMediaResults.model_validate(results[-1].payload)
        assert len(payload.results) == 1
        st = payload.results[0]
        assert getattr(st, "status", None) == "failed"

    def test_index_media_success(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "doc.txt", b"first chunk text. second chunk text.")

        media = [MediaLink(id="m2", url="file:///doc.txt", name="doc.txt", mimetype="text/plain")]
        msg = _build_message(
            generator,
            IndexMediaLinks(media=media).model_dump(),
            get_qualified_class_name(IndexMediaLinks),
        )

        agent._on_message(msg)

        assert len(results) >= 1
        payload = IndexMediaResults.model_validate(results[-1].payload)
        assert len(payload.results) == 1
        res = payload.results[0]
        assert res.status == "indexed"
        assert res.knol_id is not None

    def test_search_basic(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "q1.txt", b"first chunk text. second chunk text.")
        media = [MediaLink(id="m3", url="file:///q1.txt", name="q1.txt", mimetype="text/plain")]

        # Ingest first
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=media).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        # Now search
        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(text="first", limit=5).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        assert len(results) >= 2
        sr = KBSearchResults.model_validate(results[-1].payload)
        assert sr.search_duration_ms is not None
        assert isinstance(sr.results, list)
        assert len(sr.results) >= 1

    def test_search_with_explain(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "q2.txt", b"alpha beta gamma delta.")
        media = [MediaLink(id="m4", url="file:///q2.txt", name="q2.txt", mimetype="text/plain")]

        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=media).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        # Use hybrid to exercise explain paths
        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(text="alpha", limit=3, hybrid=HybridOptions(), explain=True).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        assert len(results) >= 2
        sr = KBSearchResults.model_validate(results[-1].payload)
        assert sr.explain is not None
        assert sr.explain.targets_used is not None and len(sr.explain.targets_used) >= 1
        assert sr.search_duration_ms is not None

    def test_hybrid_multi_target_fanout_and_explain_counts(self, agent_spec, dependency_map, generator, monkeypatch):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        def _cfg_two_targets(self):
            cfg = KnowledgeAgentConfig.default_text(id="kb_two")
            # Add a second vector column to text modality
            vname_a = cfg.pipelines[0].storage.vector_column
            vname_b = f"{vname_a}_b"
            vectors = cfg.schema_infer.modalities[cfg.schema_infer.modalities.keys().__iter__().__next__()].vectors  # type: ignore
            # Append a second vector spec with same dim/name variant
            vectors.append(vectors[0].model_copy(update={"name": vname_b}))
            # Add second pipeline bound to the new vector column
            p0 = cfg.pipelines[0]
            cfg.pipelines.append(
                PipelineSpec(
                    id=f"{p0.id}_b",
                    schema_ref=SchemaRef(
                        schema_id=p0.schema_ref.schema_id, schema_version=p0.schema_ref.schema_version
                    ),
                    target=TargetSelector(modality=p0.target.modality, mimetype=p0.target.mimetype),
                    chunker=ChunkerRef(chunker_id=p0.chunker.chunker_id, policy_version=p0.chunker.policy_version),
                    embedder=EmbedderRef(
                        embedder_id=p0.embedder.embedder_id, embedder_version=p0.embedder.embedder_version
                    ),
                    storage=StorageSpec(vector_column=vname_b),
                )
            )
            return cfg

        monkeypatch.setattr(KnowledgeAgent, "_get_cfg", _cfg_two_targets, raising=True)

        _prepare_media_on_fs(agent, dependency_map, "mt.txt", b"alpha beta gamma delta epsilon")
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(
                    media=[MediaLink(id="mt", url="file:///mt.txt", name="mt.txt", mimetype="text/plain")]
                ).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(
                    text="alpha", limit=3, hybrid=HybridOptions(dense_weight=0.6, sparse_weight=0.4), explain=True
                ).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        sr = KBSearchResults.model_validate(results[-1].payload)
        assert sr.explain is not None
        # Fanout used: at least 2 targets recorded with timings
        assert sr.explain.targets_used is not None and len(sr.explain.targets_used) >= 2
        assert all("t." in k or k == "total" for k in sr.explain.timings_ms.keys())

    @pytest.mark.asyncio
    async def test_reranker_applied_and_explain_metadata(self, agent_spec, dependency_map, generator, monkeypatch):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        class TestReranker(RerankerPlugin):  # type: ignore
            id: str = "rr"

            async def rerank(self, *, results, query):
                # Deterministically reverse and re-score top_n candidates
                out = list(reversed(results))
                for i, r in enumerate(out):
                    r.score = 1000.0 - i
                return out

        def _cfg_with_reranker(self):
            cfg = KnowledgeAgentConfig.default_text(id="kb_rr")
            cfg.plugins.rerankers["rr"] = TestReranker()
            return cfg

        monkeypatch.setattr(KnowledgeAgent, "_get_cfg", _cfg_with_reranker, raising=True)

        _prepare_media_on_fs(agent, dependency_map, "rra.txt", b"alpha one two three")
        _prepare_media_on_fs(agent, dependency_map, "rrb.txt", b"alpha three four five")

        # Directly exercise KnowledgeBase to validate reranking end-to-end
        fs = agent._dependency_resolvers["filesystem"].get_or_resolve(agent.guild_id)
        kb_backend = agent._dependency_resolvers["kb_backend"].get_or_resolve(agent.guild_id)
        kb = await agent._get_kb(filesystem=fs, kb_backend=kb_backend)
        await kb.ensure_ready()
        await kb.ingest_media(
            [
                MediaLink(id="rra", url="file:///rra.txt", name="rra.txt", mimetype="text/plain"),
                MediaLink(id="rrb", url="file:///rrb.txt", name="rrb.txt", mimetype="text/plain"),
            ]
        )

        targets = await kb.build_search_targets_from_text(text="alpha")
        q = SearchQuery(
            text="alpha",
            targets=targets,
            limit=2,
            rerank=RerankOptions(strategy=RerankStrategy.LINEAR, top_n=2, model="rr"),
            explain=True,
        )
        sr = await kb.search(query=q)
        assert sr.explain is not None and sr.explain.rerank_used is True
        assert sr.explain.rerank_model == "rr"
        # Scores set by reranker should be strictly decreasing
        scores = [r.score for r in sr.results]
        assert all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))

    def test_index_media_missing_file_failure(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        media = [MediaLink(id="m_missing", url="file:///no_such.txt", name="no_such", mimetype="text/plain")]
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=media).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        assert len(results) >= 1
        payload = IndexMediaResults.model_validate(results[-1].payload)
        assert len(payload.results) == 1
        assert payload.results[0].status == "failed"

    def test_index_media_duplicate_inputs(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "dup.txt", b"duplicate content for knol")
        media = [
            MediaLink(id="mdup1", url="file:///dup.txt", name="dup.txt", mimetype="text/plain"),
            MediaLink(id="mdup2", url="file:///dup.txt", name="dup.txt", mimetype="text/plain"),
        ]

        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=media).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        assert len(results) >= 1
        payload = IndexMediaResults.model_validate(results[-1].payload)
        assert len(payload.results) == 2
        assert all(r.status in {"indexed", "failed"} for r in payload.results)
        # At least one successful indexing with knol_id
        assert any(r.status == "indexed" and r.knol_id for r in payload.results)

    def test_search_limit_and_history(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "limit1.txt", b"alpha beta")
        _prepare_media_on_fs(agent, dependency_map, "limit2.txt", b"alpha gamma")
        media_a = MediaLink(id="ma", url="file:///limit1.txt", name="limit1.txt", mimetype="text/plain")
        media_b = MediaLink(id="mb", url="file:///limit2.txt", name="limit2.txt", mimetype="text/plain")

        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=[media_a, media_b]).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(text="alpha", limit=1).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        assert len(results) >= 2
        sr = KBSearchResults.model_validate(results[-1].payload)
        assert len(sr.results) == 1
        # Validate message history processor
        assert (
            results[-1].message_history and results[-1].message_history[0].processor == KnowledgeAgent.search.__name__
        )

        # Unmatched text returns empty
        # Use a hard filter that can never match to assert empty results deterministically
        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(
                    text="zzzz-does-not-match",
                    limit=3,
                    filter=BoolFilter(must=[FilterClause(field="text", op=FilterOp.EQ, value="no-such-text-value")]),
                ).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )
        sr2 = KBSearchResults.model_validate(results[-1].payload)
        assert isinstance(sr2.results, list) and len(sr2.results) == 0

    def test_search_hybrid_rrf_explain_weighting(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        _prepare_media_on_fs(agent, dependency_map, "rrf.txt", b"one two three four five")
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(
                    media=[MediaLink(id="rrf", url="file:///rrf.txt", name="rrf.txt", mimetype="text/plain")]
                ).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(
                    text="three",
                    limit=3,
                    hybrid=HybridOptions(dense_weight=0.7, sparse_weight=0.3, fusion_strategy=FusionStrategy.RRF),
                    explain=True,
                ).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        sr = KBSearchResults.model_validate(results[-1].payload)
        assert sr.explain is not None
        assert sr.explain.fusion == FusionStrategy.RRF
        assert sr.explain.weighting is not None
        assert abs(float(sr.explain.weighting.dense_weight) - 0.7) < 1e-6
        assert abs(float(sr.explain.weighting.sparse_weight) - 0.3) < 1e-6

    def test_embedder_dimension_mismatch_emits_error(self, agent_spec, dependency_map, generator, monkeypatch):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        def _bad_cfg(self):
            cfg = KnowledgeAgentConfig.default_text(id="kb_mismatch")
            # Mismatch embedder dimension vs schema
            cfg.plugins.embedders["text_embedder"].dimension = 16
            return cfg

        monkeypatch.setattr(KnowledgeAgent, "_get_cfg", _bad_cfg, raising=True)

        _prepare_media_on_fs(agent, dependency_map, "mismatch.txt", b"payload")
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(
                    media=[MediaLink(id="mm", url="file:///mismatch.txt", name="mismatch.txt", mimetype="text/plain")]
                ).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        assert len(results) >= 1
        # Last message should be an error envelope
        assert results[-1].format == get_qualified_class_name(ErrorMessage)

    def test_agent_search_returns_payload(self, agent_spec, dependency_map, generator):
        agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

        content = "This is the content that should be in the payload."
        _prepare_media_on_fs(agent, dependency_map, "payload.txt", content.encode("utf-8"))

        media = [MediaLink(id="m_payload", url="file:///payload.txt", name="payload.txt", mimetype="text/plain")]
        agent._on_message(
            _build_message(
                generator,
                IndexMediaLinks(media=media).model_dump(),
                get_qualified_class_name(IndexMediaLinks),
            )
        )

        # Search for it
        agent._on_message(
            _build_message(
                generator,
                KBSearchRequest(text="content", limit=1).model_dump(),
                get_qualified_class_name(KBSearchRequest),
            )
        )

        assert len(results) >= 2
        sr = SearchResults.model_validate(results[-1].payload)
        assert len(sr.results) == 1
        # Verify payload contains the text content
        # The default text config uses a chunker that puts text in the 'text' field
        assert sr.results[0].payload.get("text") == content
        assert sr.results[0].payload.get("knol_id") is not None
