import asyncio

import httpx
import pytest

from rustic_ai.core.agents.testutils import EchoAgent
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec, GuildSpec
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


class TestFilesystemAPI:
    @pytest.fixture
    def echo_agent(self) -> AgentSpec:
        name = "EchoAgent"
        description = "An echo agent"
        additional_topic = "echo_topic"
        return (
            AgentBuilder(EchoAgent)
            .set_id("echo_agent_id")
            .set_name(name)
            .set_description(description)
            .add_additional_topic(additional_topic)
            .listen_to_default_topic(False)
            .build_spec()
        )

    @pytest.fixture
    def guild(self, echo_agent: AgentSpec) -> GuildSpec:
        return (
            GuildBuilder(guild_name="guild_name_123", guild_description="Filesystem testing guild")
            .add_agent_spec(echo_agent)
            .add_dependency_resolver(
                "filesystem",
                DependencySpec(
                    class_name=FileSystemResolver.get_qualified_class_name(),
                    properties={
                        "path_base": "/tmp",
                        "protocol": "file",
                        "storage_options": {
                            "auto_mkdir": True,
                        },
                    },
                ),
            )
            .build_spec()
        )

    @pytest.fixture
    def generator(self):
        """
        Fixture that returns a GemstoneGenerator instance with a seed of 1.
        """
        return GemstoneGenerator(1)

    @pytest.mark.asyncio
    async def test_upload_file(self, guild: GuildSpec):
        server = "127.0.0.1:8880"

        async with httpx.AsyncClient(base_url=f"http://{server}") as ac:
            new_guild_resp = await ac.post("/api/guilds", json=guild.model_dump())

            assert new_guild_resp.status_code == 201
            guild_id = new_guild_resp.json()["id"]

            assert guild_id is not None

            await asyncio.sleep(0.2)

            # Test list of files for newly created guild should be empty
            guild_files_response0 = await ac.get(f"/api/guilds/{guild_id}/files/")
            assert guild_files_response0.status_code == 200
            gf_json0 = guild_files_response0.json()
            assert len(gf_json0) == 0

            # Create a file-like object to simulate file upload
            file_content = b"Hello, this is a test file."
            files = {"file": ("test.txt", file_content, "text/plain")}
            response = await ac.post(
                f"/api/guilds/{guild_id}/files/", files=files, data={"file_meta": '{"category":"test"}'}
            )

            assert response.status_code == 200
            json_response = response.json()
            assert json_response["filename"] == "test.txt"
            assert json_response["content_type"] == "text/plain"
            assert json_response["content_length"] == len(file_content)

            await asyncio.sleep(0.2)
            # Upload the file again should give 409
            response = await ac.post(f"/api/guilds/{guild_id}/files/", files=files)

            assert response.status_code == 409

            # Upload a file to a non-existing guild should give 404

            response = await ac.post("/api/guilds/non_existing_guild/files/", files=files)

            assert response.status_code == 404

            # Upload a file to a agent location
            response = await ac.post(f"/api/guilds/{guild_id}/agents/echo_agent_id/files/", files=files)

            assert response.status_code == 200

            json_response = response.json()
            assert json_response["filename"] == "test.txt"
            assert json_response["content_type"] == "text/plain"

            # Upload the file again should give 409
            response = await ac.post(f"/api/guilds/{guild_id}/agents/echo_agent_id/files/", files=files)

            assert response.status_code == 409

            # Test the files can be downloaded
            response = await ac.get(f"/api/guilds/{guild_id}/files/test.txt")

            assert response.status_code == 200
            assert response.content == file_content

            # Test the files can be downloaded from agent location
            response = await ac.get(f"/api/guilds/{guild_id}/agents/echo_agent_id/files/test.txt")

            assert response.status_code == 200
            assert response.content == file_content

            # Test list files response
            guild_files_response = await ac.get(f"/api/guilds/{guild_id}/files/")
            assert guild_files_response.status_code == 200
            gf_json = guild_files_response.json()
            assert len(gf_json) == 1
            assert gf_json[0]["name"] == "test.txt"
            assert gf_json[0]["metadata"]["category"] == "test"

            guild_files_response2 = await ac.get("/api/guilds/nonexistent/files/")
            assert guild_files_response2.status_code == 404

            # Test delete file and list files for agent
            delete_response = await ac.delete(f"/api/guilds/{guild_id}/agents/echo_agent_id/files/test.txt")
            assert delete_response.status_code == 204
            agent_file_response = await ac.get(f"/api/guilds/{guild_id}/agents/echo_agent_id/files/")
            assert agent_file_response.status_code == 200
            gf_json = agent_file_response.json()
            assert len(gf_json) == 0
