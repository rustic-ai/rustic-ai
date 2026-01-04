import time
from typing import Optional
import uuid

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    GUILD_GLOBAL,
    ORG_GLOBAL,
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


class AgentWithOrgDependency(Agent):
    """Agent that uses an org-level dependency."""

    @processor(clz=JsonDict, depends_on=["shared_resource:org"])
    def process_with_org_dep(self, ctx: ProcessContext, shared_resource: str):
        ctx.send_dict({"shared_resource": shared_resource, "guild_id": self.guild_id, "agent_id": self.id})


class AgentWithGuildDependency(Agent):
    """Agent that uses a guild-level dependency."""

    @processor(clz=JsonDict, depends_on=["guild_resource:guild"])
    def process_with_guild_dep(self, ctx: ProcessContext, guild_resource: str):
        ctx.send_dict({"guild_resource": guild_resource, "guild_id": self.guild_id, "agent_id": self.id})


class AgentWithBothOrgAndGuildDependency(Agent):
    """Agent that has both org_level and guild_level set to True (org_level should take precedence)."""

    @processor(clz=JsonDict, depends_on=["precedence_resource:precedence_var:org"])
    def process_with_precedence_dep(self, ctx: ProcessContext, precedence_var: str):
        ctx.send_dict({"precedence_resource": precedence_var, "guild_id": self.guild_id, "agent_id": self.id})


class AgentWithAllScopes(Agent):
    """Agent that uses dependencies at all three scopes."""

    @processor(clz=JsonDict, depends_on=["org_dep:org", "guild_dep:guild", "agent_dep"])
    def process_all_scopes(self, ctx: ProcessContext, org_dep: str, guild_dep: str, agent_dep: str):
        ctx.send_dict(
            {
                "org_dep": org_dep,
                "guild_dep": guild_dep,
                "agent_dep": agent_dep,
                "guild_id": self.guild_id,
                "agent_id": self.id,
            }
        )


class FilepathDependencyResolver(DependencyResolver):

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> str:
        return f"{self.prefix}/filepath_{guild_id}_{agent_id}"


class SearchIndexDependencyResolver(DependencyResolver):

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> str:
        return f"searchindex_{guild_id}_{agent_id}"


class ScopeTrackingResolver(DependencyResolver):
    """
    A resolver that returns a string showing exactly what scope parameters were passed.
    This allows tests to verify org_level, guild_level, and agent_level scoping.
    """

    def __init__(self, prefix: str = "resource") -> None:
        super().__init__()
        self.prefix = prefix

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> str:
        return f"{self.prefix}|org={org_id}|guild={guild_id}|agent={agent_id}"


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


class TestOrganizationScopedDependencies:
    """Tests for organization-level dependency scoping."""

    def _wait_for_messages(self, probe_agent: ProbeAgent, expected_count: int = 1, max_wait: float = 5.0):
        """Helper to wait for messages with timeout."""
        slept = 0.0
        while len(probe_agent.get_messages()) < expected_count and slept < max_wait:
            time.sleep(0.1)
            slept += 0.1
        return probe_agent.get_messages()

    def test_org_level_dependency_uses_org_global_for_guild_and_agent(self, probe_spec, org_id):
        """
        Test that org-level dependencies resolve with ORG_GLOBAL for guild_id and agent_id.
        This ensures the dependency is shared across all guilds in the organization.
        """
        agent_spec = (
            AgentBuilder(AgentWithOrgDependency)
            .set_description("Agent with org-level dependency")
            .set_name("OrgDepAgent")
            .build_spec()
        )

        guild_id = f"test_org_dep_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test Org Dep Guild", "Guild to test org-level dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {
                    "shared_resource": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "org_resource"},
                    )
                }
            )
        )

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test org dependency"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages = self._wait_for_messages(probe_agent)
        assert len(messages) == 1

        data = messages[0].payload
        # Org-level dependency should use ORG_GLOBAL for both guild_id and agent_id
        expected_resource = f"org_resource|org={org_id}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"
        assert data["shared_resource"] == expected_resource

        probe_agent.clear_messages()
        guild.shutdown()

    def test_guild_level_dependency_uses_guild_global_for_agent(self, probe_spec, org_id):
        """
        Test that guild-level dependencies resolve with GUILD_GLOBAL for agent_id.
        This ensures the dependency is shared across all agents in the guild.
        """
        agent_spec = (
            AgentBuilder(AgentWithGuildDependency)
            .set_description("Agent with guild-level dependency")
            .set_name("GuildDepAgent")
            .build_spec()
        )

        guild_id = f"test_guild_dep_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test Guild Dep Guild", "Guild to test guild-level dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {
                    "guild_resource": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "guild_resource"},
                    )
                }
            )
        )

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test guild dependency"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages = self._wait_for_messages(probe_agent)
        assert len(messages) == 1

        data = messages[0].payload
        # Guild-level dependency should use actual guild_id and GUILD_GLOBAL for agent_id
        expected_resource = f"guild_resource|org={org_id}|guild={guild_id}|agent={GUILD_GLOBAL}"
        assert data["guild_resource"] == expected_resource

        probe_agent.clear_messages()
        guild.shutdown()

    def test_agent_level_dependency_uses_actual_agent_id(self, probe_spec, org_id):
        """
        Test that agent-level dependencies resolve with the actual agent_id.
        """
        agent_spec = (
            AgentBuilder(DemoAgent1)
            .set_description("Agent with agent-level dependency")
            .set_name("AgentDepAgent")
            .build_spec()
        )
        agent_id = agent_spec.id

        guild_id = f"test_agent_dep_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test Agent Dep Guild", "Guild to test agent-level dependency")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {
                    "filepath": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "agent_resource"},
                    ),
                    "searchindex": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "search"},
                    ),
                }
            )
        )

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test agent dependency"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages = self._wait_for_messages(probe_agent)
        assert len(messages) == 1

        data = messages[0].payload
        # Agent-level dependency should use actual guild_id and agent_id
        expected_filepath = f"agent_resource|org={org_id}|guild={guild_id}|agent={agent_id}"
        expected_searchindex = f"search|org={org_id}|guild={guild_id}|agent={agent_id}"
        assert data["filepath"] == expected_filepath
        assert data["searchindex"] == expected_searchindex

        probe_agent.clear_messages()
        guild.shutdown()

    def test_all_three_scopes_in_same_agent(self, probe_spec, org_id):
        """
        Test that an agent can have dependencies at all three scopes (org, guild, agent)
        and each resolves correctly.
        """
        agent_spec = (
            AgentBuilder(AgentWithAllScopes)
            .set_description("Agent with all scope levels")
            .set_name("AllScopesAgent")
            .build_spec()
        )
        agent_id = agent_spec.id

        guild_id = f"test_all_scopes_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test All Scopes Guild", "Guild to test all scope levels")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {
                    "org_dep": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "org"},
                    ),
                    "guild_dep": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "guild"},
                    ),
                    "agent_dep": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "agent"},
                    ),
                }
            )
        )

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test all scopes"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages = self._wait_for_messages(probe_agent)
        assert len(messages) == 1

        data = messages[0].payload

        # Verify each scope resolves with the correct parameters
        assert data["org_dep"] == f"org|org={org_id}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"
        assert data["guild_dep"] == f"guild|org={org_id}|guild={guild_id}|agent={GUILD_GLOBAL}"
        assert data["agent_dep"] == f"agent|org={org_id}|guild={guild_id}|agent={agent_id}"

        probe_agent.clear_messages()
        guild.shutdown()

    def test_org_level_dependency_shared_across_guilds(self, probe_spec, org_id):
        """
        Test that org-level dependencies resolve to the same value across different guilds
        in the same organization.
        """
        # Create two different guilds with the same org-level dependency
        agent_spec1 = (
            AgentBuilder(AgentWithOrgDependency)
            .set_id("org_dep_agent_1")
            .set_description("Agent 1 with org-level dependency")
            .set_name("OrgDepAgent1")
            .build_spec()
        )

        agent_spec2 = (
            AgentBuilder(AgentWithOrgDependency)
            .set_id("org_dep_agent_2")
            .set_description("Agent 2 with org-level dependency")
            .set_name("OrgDepAgent2")
            .build_spec()
        )

        guild_id_1 = f"test_org_shared_guild_1_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        guild_id_2 = f"test_org_shared_guild_2_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        dep_map = {
            "shared_resource": DependencySpec(
                class_name=ScopeTrackingResolver.get_qualified_class_name(),
                properties={"prefix": "shared"},
            )
        }

        guild_builder_1 = (
            GuildBuilder(guild_id_1, "Test Org Shared Guild 1", "First guild for org sharing test")
            .add_agent_spec(agent_spec1)
            .set_dependency_map(dep_map)
        )

        guild_builder_2 = (
            GuildBuilder(guild_id_2, "Test Org Shared Guild 2", "Second guild for org sharing test")
            .add_agent_spec(agent_spec2)
            .set_dependency_map(dep_map)
        )

        guild1 = guild_builder_1.launch(organization_id=org_id)
        guild2 = guild_builder_2.launch(organization_id=org_id)

        probe_agent1: ProbeAgent = guild1._add_local_agent(probe_spec)  # type: ignore

        # Create a new probe spec for guild2
        probe_spec2 = (
            AgentBuilder(ProbeAgent)
            .set_id(f"test_agent_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}")
            .set_name("Test Agent 2")
            .set_description("A test agent")
            .build_spec()
        )
        probe_agent2: ProbeAgent = guild2._add_local_agent(probe_spec2)  # type: ignore

        # Send messages to both guilds
        probe_agent1.publish_dict(
            topic="default_topic",
            payload={"message": "Test org dependency guild 1"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        probe_agent2.publish_dict(
            topic="default_topic",
            payload={"message": "Test org dependency guild 2"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages1 = self._wait_for_messages(probe_agent1)
        messages2 = self._wait_for_messages(probe_agent2)

        assert len(messages1) == 1
        assert len(messages2) == 1

        # Both should resolve to the same value since it's org-scoped
        expected_resource = f"shared|org={org_id}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"
        assert messages1[0].payload["shared_resource"] == expected_resource
        assert messages2[0].payload["shared_resource"] == expected_resource

        # But they should be from different guilds
        assert messages1[0].payload["guild_id"] == guild_id_1
        assert messages2[0].payload["guild_id"] == guild_id_2

        probe_agent1.clear_messages()
        probe_agent2.clear_messages()
        guild1.shutdown()
        guild2.shutdown()

    def test_different_orgs_get_different_org_level_dependencies(self, probe_spec):
        """
        Test that different organizations get different org-level dependency values.
        """
        agent_spec1 = (
            AgentBuilder(AgentWithOrgDependency)
            .set_id("org_dep_agent_org1")
            .set_description("Agent with org-level dependency for org1")
            .set_name("OrgDepAgentOrg1")
            .build_spec()
        )

        agent_spec2 = (
            AgentBuilder(AgentWithOrgDependency)
            .set_id("org_dep_agent_org2")
            .set_description("Agent with org-level dependency for org2")
            .set_name("OrgDepAgentOrg2")
            .build_spec()
        )

        org_id_1 = f"test_org_1_{uuid.uuid4().hex[:8]}"
        org_id_2 = f"test_org_2_{uuid.uuid4().hex[:8]}"

        guild_id_1 = f"test_diff_org_guild_1_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        guild_id_2 = f"test_diff_org_guild_2_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        dep_map = {
            "shared_resource": DependencySpec(
                class_name=ScopeTrackingResolver.get_qualified_class_name(),
                properties={"prefix": "isolated"},
            )
        }

        guild_builder_1 = (
            GuildBuilder(guild_id_1, "Test Diff Org Guild 1", "Guild for org1")
            .add_agent_spec(agent_spec1)
            .set_dependency_map(dep_map)
        )

        guild_builder_2 = (
            GuildBuilder(guild_id_2, "Test Diff Org Guild 2", "Guild for org2")
            .add_agent_spec(agent_spec2)
            .set_dependency_map(dep_map)
        )

        guild1 = guild_builder_1.launch(organization_id=org_id_1)
        guild2 = guild_builder_2.launch(organization_id=org_id_2)

        probe_agent1: ProbeAgent = guild1._add_local_agent(probe_spec)  # type: ignore

        probe_spec2 = (
            AgentBuilder(ProbeAgent)
            .set_id(f"test_agent_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}")
            .set_name("Test Agent 2")
            .set_description("A test agent")
            .build_spec()
        )
        probe_agent2: ProbeAgent = guild2._add_local_agent(probe_spec2)  # type: ignore

        probe_agent1.publish_dict(
            topic="default_topic",
            payload={"message": "Test org1 dependency"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        probe_agent2.publish_dict(
            topic="default_topic",
            payload={"message": "Test org2 dependency"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages1 = self._wait_for_messages(probe_agent1)
        messages2 = self._wait_for_messages(probe_agent2)

        assert len(messages1) == 1
        assert len(messages2) == 1

        # Each org should get a different resolved value
        expected_resource_org1 = f"isolated|org={org_id_1}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"
        expected_resource_org2 = f"isolated|org={org_id_2}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"

        assert messages1[0].payload["shared_resource"] == expected_resource_org1
        assert messages2[0].payload["shared_resource"] == expected_resource_org2
        assert messages1[0].payload["shared_resource"] != messages2[0].payload["shared_resource"]

        probe_agent1.clear_messages()
        probe_agent2.clear_messages()
        guild1.shutdown()
        guild2.shutdown()


class TestDependencyScopePrecedence:
    """Tests for dependency scope precedence when multiple scope flags are set."""

    def _wait_for_messages(self, probe_agent: ProbeAgent, expected_count: int = 1, max_wait: float = 5.0):
        """Helper to wait for messages with timeout."""
        slept = 0.0
        while len(probe_agent.get_messages()) < expected_count and slept < max_wait:
            time.sleep(0.1)
            slept += 0.1
        return probe_agent.get_messages()

    def test_org_level_takes_precedence_over_guild_level(self, probe_spec, org_id):
        """
        Test that when both org_level and guild_level are True, org_level takes precedence.
        The dependency should be resolved at org scope (using ORG_GLOBAL for guild_id and agent_id).
        """
        from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency

        # Verify the precedence in AgentDependency parsing
        # When org_level is True, it should take precedence
        dep_org = AgentDependency(dependency_key="test", org_level=True, guild_level=True)
        assert dep_org.org_level is True
        assert dep_org.guild_level is True
        assert dep_org.agent_level is False  # computed field: not guild_level and not org_level

        # Create an agent spec with manually constructed AgentDependency
        # to test the runtime precedence behavior
        agent_spec = (
            AgentBuilder(AgentWithOrgDependency)
            .set_description("Agent testing org precedence over guild")
            .set_name("PrecedenceTestAgent")
            .build_spec()
        )

        guild_id = f"test_precedence_guild_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        guild_builder = (
            GuildBuilder(guild_id, "Test Precedence Guild", "Guild to test scope precedence")
            .add_agent_spec(agent_spec)
            .set_dependency_map(
                {
                    "shared_resource": DependencySpec(
                        class_name=ScopeTrackingResolver.get_qualified_class_name(),
                        properties={"prefix": "precedence"},
                    )
                }
            )
        )

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        probe_agent.publish_dict(
            topic="default_topic",
            payload={"message": "Test precedence"},
            format=MessageConstants.RAW_JSON_FORMAT,
            priority=Priority.NORMAL,
        )

        messages = self._wait_for_messages(probe_agent)
        assert len(messages) == 1

        data = messages[0].payload
        # Since org_level takes precedence, we should see ORG_GLOBAL for both guild and agent
        expected_resource = f"precedence|org={org_id}|guild={ORG_GLOBAL}|agent={ORG_GLOBAL}"
        assert data["shared_resource"] == expected_resource

        probe_agent.clear_messages()
        guild.shutdown()

    def test_agent_dependency_scope_precedence_logic(self):
        """
        Unit test for AgentDependency scope precedence logic.
        Verifies that agent_level computed property correctly reflects the precedence.
        """
        from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency

        # Only org_level set
        dep_org_only = AgentDependency(dependency_key="test", org_level=True, guild_level=False)
        assert dep_org_only.org_level is True
        assert dep_org_only.guild_level is False
        assert dep_org_only.agent_level is False

        # Only guild_level set
        dep_guild_only = AgentDependency(dependency_key="test", org_level=False, guild_level=True)
        assert dep_guild_only.org_level is False
        assert dep_guild_only.guild_level is True
        assert dep_guild_only.agent_level is False

        # Neither set (agent_level)
        dep_agent_only = AgentDependency(dependency_key="test", org_level=False, guild_level=False)
        assert dep_agent_only.org_level is False
        assert dep_agent_only.guild_level is False
        assert dep_agent_only.agent_level is True

        # Both set - org_level should take precedence at runtime
        dep_both = AgentDependency(dependency_key="test", org_level=True, guild_level=True)
        assert dep_both.org_level is True
        assert dep_both.guild_level is True
        # agent_level is False because at least one of org_level or guild_level is True
        assert dep_both.agent_level is False

    def test_agent_dependency_from_string_parsing(self):
        """
        Test that AgentDependency.from_string correctly parses scope specifiers.
        """
        from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency

        # "key:org" format
        dep_org = AgentDependency.from_string("mykey:org")
        assert dep_org.dependency_key == "mykey"
        assert dep_org.org_level is True
        assert dep_org.guild_level is False

        # "key:guild" format
        dep_guild = AgentDependency.from_string("mykey:guild")
        assert dep_guild.dependency_key == "mykey"
        assert dep_guild.org_level is False
        assert dep_guild.guild_level is True

        # "key:var:org" format
        dep_var_org = AgentDependency.from_string("mykey:myvar:org")
        assert dep_var_org.dependency_key == "mykey"
        assert dep_var_org.dependency_var == "myvar"
        assert dep_var_org.org_level is True
        assert dep_var_org.guild_level is False

        # "key:var:guild" format
        dep_var_guild = AgentDependency.from_string("mykey:myvar:guild")
        assert dep_var_guild.dependency_key == "mykey"
        assert dep_var_guild.dependency_var == "myvar"
        assert dep_var_guild.org_level is False
        assert dep_var_guild.guild_level is True

        # "key" format (agent-level)
        dep_agent = AgentDependency.from_string("mykey")
        assert dep_agent.dependency_key == "mykey"
        assert dep_agent.org_level is False
        assert dep_agent.guild_level is False
        assert dep_agent.agent_level is True
