from typing import Dict, Optional

from fsspec import filesystem
from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, AgentMode, AgentType, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec


class WriteToFile(BaseModel):
    filename: str
    content: str
    guild_path: bool = False


class FileWriteResponse(BaseModel):
    filename: str
    result: str = "success"
    error: Optional[str] = None


class ReadFromFile(BaseModel):
    filename: str
    guild_path: bool = False


class FileReadResponse(BaseModel):
    filename: str
    content: Optional[str] = None
    result: str = "success"
    error: Optional[str] = None


class FileManagerAgent(Agent):
    """
    The File Manager Reads/Writes/Deletes files
    """

    def __init__(self, agent_spec: AgentSpec):
        super().__init__(
            agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )

    @agent.processor(WriteToFile, depends_on=["filesystem:agent_fs", "filesystem:guild_fs:True"])
    def write_file(
        self,
        ctx: ProcessContext[WriteToFile],
        agent_fs: FileSystem,
        guild_fs: FileSystem,
    ):
        """
        Handles messages of type WriteToFile, doing cool things with the data
        """
        data: WriteToFile = ctx.payload

        if data.guild_path:
            try:
                with guild_fs.open(data.filename, "wb") as f:
                    f.write(data.content.encode("utf-8"))

                ctx.send(FileWriteResponse(filename=data.filename, result="success"))

            except Exception as e:
                ctx.send(FileWriteResponse(filename=data.filename, result="failed", error=str(e)))
        else:
            try:
                with agent_fs.open(data.filename, "wb") as f:
                    f.write(data.content.encode("utf-8"))

                ctx.send(FileWriteResponse(filename=data.filename, result="success"))

            except Exception as e:
                ctx.send(FileWriteResponse(filename=data.filename, result="failed", error=str(e)))

    @agent.processor(ReadFromFile, depends_on=["filesystem:agent_fs", "filesystem:guild_fs:True"])
    def read_file(
        self,
        ctx: ProcessContext[ReadFromFile],
        agent_fs: FileSystem,
        guild_fs: FileSystem,
    ):
        """
        Handles messages of type ReadFromFile, doing cool things with the data
        """
        data: ReadFromFile = ctx.payload

        if data.guild_path:
            try:
                with guild_fs.open(data.filename, "rb") as f:
                    content = f.read()

                ctx.send(
                    FileReadResponse(
                        filename=data.filename,
                        content=content.decode("utf-8"),
                        result="success",
                    )
                )

            except Exception as e:
                ctx.send(FileReadResponse(filename=data.filename, result="failed", error=str(e)))
        else:
            try:
                with agent_fs.open(data.filename, "rb") as f:
                    content = f.read()

                ctx.send(
                    FileReadResponse(
                        filename=data.filename,
                        content=content.decode("utf-8"),
                        result="success",
                    )
                )

            except Exception as e:
                ctx.send(FileReadResponse(filename=data.filename, result="failed", error=str(e)))


class TestFileSystem:

    @pytest.mark.parametrize(
        "dep_map",
        [
            pytest.param(
                {
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
                },
                id="file",
            ),
        ],
    )
    def test_filesystem(self, probe_agent: ProbeAgent, dep_map: Dict[str, DependencySpec], org_id):
        agent_spec: AgentSpec = (
            AgentBuilder(FileManagerAgent)
            .set_id("file_manager")
            .set_name("file_manager")
            .set_description("Manages files")
            .build_spec()
        )

        guild_builder = (
            GuildBuilder("test_guild", "Test Guild", "Guild to test Filesystem Dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )

        protocol = dep_map["filesystem"].properties["protocol"]
        protocol_props = dep_map["filesystem"].properties["storage_options"]

        fs = filesystem(protocol, **protocol_props)

        dfs = FileSystem(path="/tmp/test_guild/file_manager", fs=fs)
        guild = guild_builder.launch(organization_id=org_id)

        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(
            topic="default_topic",
            payload=WriteToFile(filename="test_file", content="test content"),
            format=WriteToFile,
        )

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].payload["filename"] == "test_file"
        assert messages[0].payload["result"] == "success"

        probe_agent.clear_messages()

        with dfs.open("test_file", "rb") as f:
            content = f.readline()
            assert content == b"test content"

        probe_agent.publish_dict(
            topic="default_topic",
            payload=ReadFromFile(filename="test_file"),
            format=ReadFromFile,
        )

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].payload["filename"] == "test_file"
        assert messages[0].payload["content"] == "test content"
        assert messages[0].payload["result"] == "success"

        probe_agent.clear_messages()

        probe_agent.publish_dict(
            topic="default_topic",
            payload=WriteToFile(content="Guild file content", filename="test_file", guild_path=True),
            format=WriteToFile,
        )

        messages = probe_agent.get_messages()

        assert len(messages) == 1

        assert messages[0].payload["filename"] == "test_file"
        assert messages[0].payload["result"] == "success"

        probe_agent.clear_messages()

        gdfs = FileSystem(path="/tmp/test_guild/GUILD_GLOBAL", fs=fs)

        with gdfs.open("test_file", "rb") as f:
            content = f.readline()
            assert content == b"Guild file content"

        probe_agent.publish_dict(
            topic="default_topic",
            payload=ReadFromFile(filename="test_file", guild_path=True),
            format=ReadFromFile,
        )

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].payload["filename"] == "test_file"
        assert messages[0].payload["content"] == "Guild file content"
        assert messages[0].payload["result"] == "success"

        probe_agent.clear_messages()

        dfs.rm("test_file")
        gdfs.rm("test_file")
        dfs.rmdir("")
        gdfs.rmdir("")

        guild.shutdown()
