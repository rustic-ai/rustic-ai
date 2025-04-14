import time

from fsspec import filesystem

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import GenerationPromptRequest
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.filesystem import (
    FileSystem,
    FileSystemResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.huggingface.agents.text_to_speech.speecht5_tts_agent import (
    SpeechT5TTSAgent,
)


class TestSpeechT5TtsAgent:

    def test_response_is_generated(self, probe_agent: ProbeAgent):
        """
        Test that the agent responds to a message with a message containing the filepath of the generated audio.
        """
        # Arrange
        agent_spec: AgentSpec = (
            AgentBuilder(SpeechT5TTSAgent)
            .set_id("speecht5_tts_agent")
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
            GuildBuilder("speecht5_tts_guild", "Test Guild", "Guild to test Filesystem Dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(dep_map)
        )

        protocol = dep_map["filesystem"].properties["protocol"]
        protocol_props = dep_map["filesystem"].properties["storage_options"]

        fs = filesystem(protocol, **protocol_props)

        dfs = FileSystem(path="/tmp/speecht5_tts_guild/GUILD_GLOBAL", fs=fs)

        guild = guild_builder.launch()
        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC, {"generation_prompt": "Long live the dragons"}, GenerationPromptRequest
        )

        time.sleep(5)
        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(MediaLink)
        assert dfs.exists(f"{messages[0].payload['name']}")
        dfs.rm("", recursive=True)
        guild.shutdown()
