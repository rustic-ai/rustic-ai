import time
from typing import Optional
import uuid

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import MessageConstants
from rustic_ai.core.utils.priority import Priority


class DemoAgent1(Agent):

    @processor(clz=JsonDict, depends_on=["filepath", "searchindex"])
    def process_demo(self, ctx: ProcessContext, filepath: str, searchindex: str):
        # do things with the message, filepath and searchindex
        ctx.send_dict({"filepath": filepath, "searchindex": searchindex})


class FilepathDependencyResolver(DependencyResolver):

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def resolve(self, guild_id: str, agent_id: Optional[str] = None) -> str:
        return f"{self.prefix}/filepath_{guild_id}_{agent_id}"


class SearchIndexDependencyResolver(DependencyResolver):

    def resolve(self, guild_id: str, agent_id: Optional[str] = None) -> str:
        return f"searchindex_{guild_id}_{agent_id}"


class TestAgentDependencyInjection:

    def test_agent_di(self, probe_spec, org_id):
        agent_spec: AgentSpec = (
            AgentBuilder(DemoAgent1).set_description("Demo agent with dependencies").set_name("DemoAgent1").build_spec()
        )

        agent_id = agent_spec.id

        # Use unique guild name to avoid interference between tests
        guild_id = f"test_di_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test DI Guild", "Guild to test agent dependency injection")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {"searchindex": DependencySpec(class_name=SearchIndexDependencyResolver.get_qualified_class_name())}
            )
            .add_dependency_resolver(
                "filepath",
                DependencySpec(
                    class_name=FilepathDependencyResolver.get_qualified_class_name(),
                    properties={"prefix": "rustic-files"},
                ),
            )
        )

        gspec = guild_builder.build_spec()

        dep_keys = gspec.dependency_map.keys()

        assert "searchindex" in dep_keys
        assert "filepath" in dep_keys

        assert (
            gspec.dependency_map["searchindex"].class_name == SearchIndexDependencyResolver.get_qualified_class_name()
        )
        assert gspec.dependency_map["filepath"].class_name == FilepathDependencyResolver.get_qualified_class_name()
        assert gspec.dependency_map["filepath"].properties["prefix"] == "rustic-files"

        guild = guild_builder.launch(organization_id=org_id)

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test message"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        slept = 1
        while len(probe_agent.get_messages()) == 0 and slept < 50:
            time.sleep(0.1)
            slept += 1

        messages = probe_agent.get_messages()

        assert len(messages) == 1

        data = messages[0].payload

        assert data["filepath"] == f"rustic-files/filepath_{guild_id}_{agent_id}"
        assert data["searchindex"] == f"searchindex_{guild_id}_{agent_id}"

        probe_agent.clear_messages()

        guild.shutdown()
