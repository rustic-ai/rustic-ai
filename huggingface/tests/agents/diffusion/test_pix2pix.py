import importlib
import os
import time

from fsspec import filesystem
import pytest

from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.filesystem import (
    FileSystem,
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.huggingface.agents.diffusion.pix2pix import Image2ImageAgent, ImageQuery


class TestPix2PixAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_response_is_generated(self, probe_spec, org_id):
        """
        Test that the agent responds to a message with a message containing the filepath of the generated image.
        """
        # Arrange
        agent_spec: AgentSpec = (
            AgentBuilder(Image2ImageAgent)
            .set_id("pix2pix_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
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
            GuildBuilder("pix2pix_guild", "Test Guild", "Guild to test Filesystem Dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )

        protocol = dep_map["filesystem"].properties["protocol"]
        protocol_props = dep_map["filesystem"].properties["storage_options"]

        fs = filesystem(protocol, **protocol_props)

        dfs = FileSystem(path=f"/tmp/{org_id}/pix2pix_guild/GUILD_GLOBAL/", fs=fs)

        image_name = "image_gen_prompt.png"
        data_file_path = importlib.resources.files("huggingface.tests.resources").joinpath(image_name)
        print(f"resource file is {data_file_path}")
        data_file_in_fs_path = f"/tmp/{org_id}/pix2pix_guild/GUILD_GLOBAL/"
        fs.mkdirs(data_file_in_fs_path, exist_ok=True)
        fs.copy(data_file_path, data_file_in_fs_path)
        assert fs.exists(data_file_in_fs_path)

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            {
                "image_path": image_name,
                "generation_prompt": "turn him into cyborg",
                "num_inference_steps": 10,
                "num_images": 2,
            },
            format=ImageQuery,
        )

        time.sleep(120)
        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(ImageGenerationResponse)
        image_gen_response = messages[0].payload
        assert len(image_gen_response["errors"]) == 0
        assert len(image_gen_response["files"]) == 2
        for image in image_gen_response["files"]:
            assert dfs.exists(image["name"])
        dfs.rm("", recursive=True)
        guild.shutdown()
