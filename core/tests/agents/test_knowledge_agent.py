import os
from pathlib import Path

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencySpec,
    GUILD_GLOBAL,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.core.knowledgebase.agent_config import KnowledgeAgentConfig
from rustic_ai.core.knowledgebase.kbindex_backend_memory import (
    InMemoryKBIndexBackendResolver,
)
from rustic_ai.core.knowledgebase.query import HybridOptions, SearchResults
from rustic_ai.core.agents.indexing.knowledge_agent import (
    KnowledgeAgent,
    CatalogMediaLinks,
    CatalogMediaResults,
    IndexMediaLinks,
    IndexMediaResults,
    KBSearchRequest,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture(autouse=True)
def _patch_knowledge_agent_init(monkeypatch):
    """
    KnowledgeAgent defines __init__ that calls super().__init__(*args, **kwargs).
    The testing builder already calls Agent.__init__ directly and then invokes the
    subclass __init__ with no args. Patch KA.__init__ to be no-arg safe and
    initialize its own fields only.
    """

    def _init(self):  # no call to super(); Agent.__init__ ran already
        self._kb = None
        self._target_to_pipeline = {}
        self._pipeline_specs_by_id = {}
        self._cfg = None

    monkeypatch.setattr(KnowledgeAgent, "__init__", _init, raising=True)


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
        sr = SearchResults.model_validate(results[-1].payload)
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
        sr = SearchResults.model_validate(results[-1].payload)
        assert sr.explain is not None
        assert sr.explain.targets_used is not None and len(sr.explain.targets_used) >= 1
        assert sr.search_duration_ms is not None


