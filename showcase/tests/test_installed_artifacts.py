"""Run with RUSTIC_INSTALLED_ACCEPTANCE=1 against installed, non-editable wheels."""

import importlib
import importlib.metadata
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUSTIC_INSTALLED_ACCEPTANCE") != "1",
    reason="Requires RUSTIC_INSTALLED_ACCEPTANCE=1 in the installed-wheel environment",
)
DISTRIBUTIONS = (
    "rusticai-core",
    "rusticai-testing",
    "rusticai-llm-agent",
    "rusticai-uniko-agent",
    "rusticai-playwright",
    "rusticai-showcase",
    "rusticai-chroma",
    "rusticai-langchain",
    "rusticai-litellm",
    "rusticai-serpapi",
    "rusticai-vertexai",
    "rusticai-pandas-analyst",
    "rusticai-unidb",
    "rusticai-fact-checker",
    "rusticai-mcp",
    "rusticai-research-manager",
)
MODULES = (
    "rustic_ai.core.agents.indexing.vector_agent",
    "rustic_ai.core.guild.agent_ext.depends.embeddings",
    "rustic_ai.llm_agent.llm_agent",
    "rustic_ai.uniko_agent.document_coordinator",
    "rustic_ai.uniko_agent.conversation",
    "rustic_ai.showcase.paper_banana",
    "rustic_ai.showcase.semantic_memory",
    "rustic_ai.playwright.agent",
    "rustic_ai.chroma.agent_ext.vectorstore",
    "rustic_ai.showcase.catalog",
)


def test_runtime_modules_and_metadata_come_from_noneditable_installation():
    for name in DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        origin = json.loads(distribution.read_text("direct_url.json") or "{}")
        assert not origin.get("dir_info", {}).get("editable"), name
        assert not any("rusticai-lancedb" in value.lower() for value in distribution.requires or []), name
    for name in MODULES:
        module = importlib.import_module(name)
        assert isinstance(module.__file__, str), name
        assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (name, module.__file__)
    for name in ("rusticai-lancedb", "lancedb"):
        with pytest.raises(importlib.metadata.PackageNotFoundError):
            importlib.metadata.version(name)


@pytest.mark.parametrize(
    "name",
    [
        "rustic_ai.core.knowledgebase",
        "rustic_ai.core.agents.indexing.knowledge_agent",
        "rustic_ai.core.guild.agent_ext.depends.knowledgebase",
        "rustic_ai.lancedb",
        "rustic_ai.llm_agent.memories.knowledge_memories_store",
    ],
)
def test_retired_modules_are_absent_from_installed_distributions(name):
    with pytest.raises(ModuleNotFoundError) as error:
        importlib.import_module(name)
    assert error.value.name is not None
    assert name == error.value.name or name.startswith(error.value.name + ".")


def test_catalog_is_available_from_installed_package_resources():
    from rustic_ai.showcase.catalog import list_blueprints, load_blueprint

    root = files("rustic_ai.showcase").joinpath("apps")
    assert root.is_dir(), "The wheel must supply its own catalog, not a checkout fallback"
    names = list_blueprints()
    assert len(names) == 16
    for name in names:
        assert load_blueprint(name) == json.loads(root.joinpath(*name.split("/")).read_text(encoding="utf-8"))


def test_independent_vector_capability_works_with_native_chroma():
    import chromadb
    from chromadb import EmbeddingFunction

    from rustic_ai.chroma.agent_ext.vectorstore import Chroma
    from rustic_ai.core.agents.commons.media import Document
    from rustic_ai.core.agents.indexing.vector_agent import VectorAgent

    class LocalEmbedding(EmbeddingFunction):
        def __init__(self):
            pass

        def __call__(self, input):
            return [[1.0, 0.0] if "harbor" in text.lower() else [0.0, 1.0] for text in input]

        @staticmethod
        def name():
            return "local-acceptance-vector"

        def get_config(self):
            return {}

        @staticmethod
        def build_from_config(config):
            return LocalEmbedding()

    client = chromadb.EphemeralClient(settings=chromadb.config.Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection("acceptance-" + uuid4().hex, embedding_function=LocalEmbedding())
    store = Chroma(collection)
    document = Document(id="harbor", name="Harbor", content="Harbor budget CAD 42000", metadata={"project": "harbor"})
    chunks = VectorAgent._split_doc(document, [document.content])
    assert store.upsert(chunks).succeeded == ["harbor-0"]
    assert store.get_by_ids(["harbor-0"])[0].content == document.content
    assert store.similarity_search("Harbor budget", k=1).results[0].document.content == document.content
    assert store.delete(["harbor-0"])
    assert store.get_by_ids(["harbor-0"]) == []
    client.delete_collection(collection.name)


def test_installed_catalog_classes_and_plugins_are_importable():
    from rustic_ai.core.utils.basic_class_utils import get_class_from_name
    from rustic_ai.showcase.catalog import list_blueprints, load_blueprint

    def class_paths(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if (
                    key in {"class_name", "kind", "parameter_class"}
                    and isinstance(child, str)
                    and child.startswith("rustic_ai.")
                ):
                    yield child
                else:
                    yield from class_paths(child)
        elif isinstance(value, list):
            for child in value:
                yield from class_paths(child)

    for name in list_blueprints():
        for path in set(class_paths(load_blueprint(name)["spec"])):
            resolved = get_class_from_name(path)
            assert resolved is not None, (name, path)
            module = importlib.import_module(resolved.__module__)
            assert isinstance(module.__file__, str), (name, path)
            assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (name, path)
