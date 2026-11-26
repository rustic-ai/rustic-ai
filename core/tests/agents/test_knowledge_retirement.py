"""Retired knowledge imports must fail without breaking independent capabilities."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "rustic_ai.core.knowledgebase.knowledge_base",
        "rustic_ai.core.agents.indexing.knowledge_agent",
        "rustic_ai.core.guild.agent_ext.depends.knowledgebase",
    ],
)
def test_retired_knowledge_modules_are_unavailable(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_independent_vector_and_embedding_contracts_remain_importable():
    from rustic_ai.core.agents.indexing.vector_agent import VectorAgent
    from rustic_ai.core.guild.agent_ext.depends.embeddings import Embeddings
    from rustic_ai.core.guild.agent_ext.depends.vectorstore import VectorStore

    assert VectorAgent and Embeddings and VectorStore
