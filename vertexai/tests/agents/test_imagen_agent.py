import os
import time

from fsspec import filesystem
import pytest

from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
from rustic_ai.core.guild.agent_ext.depends.filesystem import (
    FileSystem,
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.vertexai.agents.image_generation import (
    VertexAiImageGenerationRequest,
    VertexAiImagenAgent,
)


class TestImagenAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_response_is_generated(self, probe_spec, org_id):
        """
        Test that the agent responds to a message with a message.
        """
        # Arrange
        agent_spec = (
            AgentBuilder(VertexAiImagenAgent)
            .set_id("imagen_agent")
            .set_name("Test Imagen Agent")
            .set_description("An agent for testing VertexAI Image Generation")
            .build_spec()
        )

        dep_map = {
            "filesystem": DependencySpec(
                class_name=FileSystemResolver.get_qualified_class_name(),
                properties={
                    "path_base": "/tmp",
                    "protocol": "file",
                    "storage_options": {
                        "auto_mkdir": True,
                    },
                },
            )
        }

        guild_builder = (
            GuildBuilder("imagen_guild", "Imagen Test Guild", "Guild to test Imagen")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )

        protocol = dep_map["filesystem"].properties["protocol"]
        protocol_props = dep_map["filesystem"].properties["storage_options"]

        fs = filesystem(protocol, **protocol_props)

        dfs = FileSystem(path="/tmp/imagen_guild/GUILD_GLOBAL", fs=fs)

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent = guild._add_local_agent(probe_spec)

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            {"prompt": "a pizza", "negative_prompt": "pepperoni"},
            in_response_to=1,
            format=VertexAiImageGenerationRequest,
        )

        time.sleep(30)
        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(ImageGenerationResponse)
        image_gen_response = messages[0].payload
        assert len(image_gen_response["errors"]) == 0
        for image in image_gen_response["files"]:
            assert dfs.exists(image["name"])
        dfs.rm("", recursive=True)
        guild.shutdown()
