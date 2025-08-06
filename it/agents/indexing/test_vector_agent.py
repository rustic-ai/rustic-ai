import os
import time

from flaky import flaky
from fsspec import filesystem
import pytest

from rustic_ai.chroma.agent_ext.vectorstore import ChromaResolver
from rustic_ai.core.agents.commons.media import Document
from rustic_ai.core.agents.indexing.vector_agent import (
    IngestDocuments,
    VectorAgent,
    VectorSearchQuery,
)
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.filesystem import (
    FileSystem,
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.langchain.agent_ext.embeddings.openai import OpenAIEmbeddingsResolver
from rustic_ai.langchain.agent_ext.text_splitter.character_splitter import (
    CharacterSplitterResolver,
)


@pytest.mark.skipif(os.getenv("OPENAI_API_KEY") is None, reason="OPENAI_API_KEY environment variable not set")
class TestVectorAgent:
    @flaky(max_runs=3, min_passes=1)
    def test_vector_agent(self, probe_spec, org_id):
        guild_id = "test_vector_guild"
        dep_map = {
            "vectorstore": DependencySpec(
                class_name=ChromaResolver.get_qualified_class_name(),
                properties={"chroma_settings": {"persist_directory": "/tmp/chroma_test"}},
            ),
            "filesystem": DependencySpec(
                class_name=FileSystemResolver.get_qualified_class_name(),
                properties={
                    "path_base": "/tmp",
                    "protocol": "file",
                    "storage_options": {
                        "auto_mkdir": True,
                    },
                },
            ),
            "textsplitter": DependencySpec(
                class_name=CharacterSplitterResolver.get_qualified_class_name(),
                properties={"conf": {"chunk_size": 10000, "chunk_overlap": 1000}},
            ),
            "embeddings": DependencySpec(class_name=OpenAIEmbeddingsResolver.get_qualified_class_name(), properties={}),
        }

        agent_spec: AgentSpec = (
            AgentBuilder(VectorAgent).set_description("Vector Agent").set_name("VectorAgent").build_spec()
        )

        guild_builder = (
            GuildBuilder(guild_id, "Test Guild", "Guild to test Vector Agent")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )

        protocol = dep_map["filesystem"].properties["protocol"]
        protocol_props = dep_map["filesystem"].properties["storage_options"]

        fs = filesystem(protocol, **protocol_props)
        dfs = FileSystem(path=f"/tmp/{guild_id}/GUILD_GLOBAL", fs=fs)

        guild = guild_builder.launch(org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        # Upsert documents
        probe_agent.publish_dict(
            topic="default_topic",
            payload={"documents": [Document(id="doc1", content="test doc", name="doc1", metadata={}).model_dump()]},
            format=IngestDocuments,
        )
        time.sleep(2.0)  # Allow more time for document ingestion

        # Search for documents
        probe_agent.publish_dict(
            topic="default_topic",
            payload={"query": "test"},
            format=VectorSearchQuery,
        )
        time.sleep(3)  # Allow more time for search processing

        messages = probe_agent.get_messages()
        assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"
        assert messages[0].payload["succeeded"] == ["doc1-0"]
        assert messages[1].payload["results"][0]["document"]["content"] == "test doc"

        # Clean up
        probe_agent.clear_messages()
        if dfs.exists(""):
            dfs.rm("", recursive=True)

        time.sleep(2.0)  # Allow time for cleanup

        guild.shutdown()
