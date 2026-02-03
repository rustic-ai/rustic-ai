import pytest

from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    RoutingDestination,
    RoutingRule,
)


class CollectorAgent(Agent):
    """Simple agent for testing that collects messages."""

    @agent.processor(JsonDict)
    def collect(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        pass


class TestGuildManagement:

    exec_engine_clz: str = (
        "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine"
    )

    @pytest.fixture
    def org_id(self):
        return "test_org"

    def test_guild_remove_agent_logic(self, org_id):
        # 1. Setup Guild
        guild = (
            GuildBuilder("test_guild", "Test Guild", "Test Guild for remove agent")
            .set_execution_engine(TestGuildManagement.exec_engine_clz)
            .launch(organization_id=org_id)
        )

        # 2. Add an Agent
        agent_spec = (
            AgentBuilder(CollectorAgent)
            .set_name("TestAgent")
            .set_description("Test agent for removal test")
            .build_spec()
        )
        guild.register_or_launch_agent(agent_spec)

        assert guild.get_agent_count() == 1
        assert guild.is_agent_running(agent_spec.id)

        # 3. Remove Agent
        guild.remove_agent(agent_spec.id)

        # 4. Verify Removal
        assert guild.get_agent_count() == 0
        assert not guild.is_agent_running(agent_spec.id)
        assert guild.get_agent(agent_spec.id) is None

        guild.shutdown()

    def test_routing_rule_management_logic(self, org_id):
        # 1. Setup Guild
        guild = (
            GuildBuilder("test_routes", "Test Routes", "Test Guild for routes")
            .set_execution_engine(TestGuildManagement.exec_engine_clz)
            .launch(organization_id=org_id)
        )

        assert len(guild.routes.steps) == 0

        # 2. Add Rule
        rule = RoutingRule(
            agent=AgentTag(id="agent1", name="Agent One"),
            method_name="test_method",
            destination=RoutingDestination(topics=["test.topic"])
        )

        guild.routes.add_step(rule)
        assert len(guild.routes.steps) == 1
        assert guild.routes.steps[0].hashid == rule.hashid

        # 3. Remove Rule (Simulate Manager Logic)
        target_hashid = rule.hashid
        guild.routes.steps = [
            step for step in guild.routes.steps if step.hashid != target_hashid
        ]

        assert len(guild.routes.steps) == 0

        guild.shutdown()
