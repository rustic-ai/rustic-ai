import os
from textwrap import dedent
import time

from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.agent import (
    Agent,
    AgentMode,
    AgentType,
    ProcessContext,
    processor,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics, SimpleRuntimePredicate
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    RoutingRule,
    RoutingSlip,
    StateTransformer,
)
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.json_utils import JsonDict


class EchoGuildState(BaseModel):
    guild_id: str


class EchoAgentState(BaseModel):
    guild_id: str
    agent_id: str


class PublishedData(BaseModel):
    data: JsonDict


class ReceivedData(BaseModel):
    data: JsonDict


class StateAwareAgent(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @processor(EchoGuildState)
    def echo_guild_state(self, ctx: ProcessContext[EchoGuildState]) -> None:
        ctx.send(PublishedData(data=self.get_guild_state()))

    @processor(EchoAgentState)
    def echo_agent_state(self, ctx: ProcessContext[EchoAgentState]) -> None:
        ctx.send(PublishedData(data=self.get_agent_state()))


class StateFreeAgent(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)

    @processor(PublishedData)
    def echo_data(self, ctx: ProcessContext[PublishedData]) -> None:
        ctx.send(ReceivedData(data=ctx.payload.data))


class TestStateMgmt:

    @pytest.fixture
    def state_aware_agent(self):
        return (
            AgentBuilder(StateAwareAgent)
            .set_name("state_aware_agent")
            .set_id("state_aware_agent")
            .set_description("State Aware Agent")
            .build_spec()
        )

    @pytest.fixture
    def state_free_agent(self):
        return (
            AgentBuilder(StateFreeAgent)
            .set_name("state_free_agent")
            .set_id("state_free_agent")
            .set_description("State Free Agent")
            .add_predicate("echo_data", SimpleRuntimePredicate(expression="$count($keys(message.payload.data)) != 0"))
            .build_spec()
        )

    @pytest.fixture
    def database(self):
        db = "sqlite:///test_rustic_state.db"

        if os.path.exists("test_rustic_state.db"):
            os.remove("test_rustic_state.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    def test_state_mgmt(self, state_aware_agent: AgentSpec, state_free_agent: AgentSpec, database, org_id):
        builder = (
            GuildBuilder("state_guild", "State Guild", "Guild to test state management")
            .add_agent_spec(state_aware_agent)
            .add_agent_spec(state_free_agent)
            .set_messaging(
                backend_module="rustic_ai.redis.messaging.backend",
                backend_class="RedisMessagingBackend",
                backend_config={"redis_client": {"host": "localhost", "port": 6379}},
            )
        )

        engine = Metastore.get_engine(database)  # noqa: F841
        guild = builder.bootstrap(database, org_id)

        probe_agent: ProbeAgent = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(GuildTopics.GUILD_STATUS_TOPIC)
            .add_additional_topic("echo_topic")
            .build()
        )

        guild._add_local_agent(probe_agent)

        guild_update_routing_rule = RoutingRule(
            agent=AgentTag(id=state_aware_agent.id),
            method_name="echo_guild_state",
            guild_state_update=StateTransformer(
                state_update=dedent(
                    """
                    {
                    "new_key": "new_value",
                    "call_count": 1
                }
                """
                )
            ),
        )

        # Get the guild state and trigger the state update
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoGuildState(guild_id=guild.id),
            routing_slip=RoutingSlip(steps=[guild_update_routing_rule]),
        )

        time.sleep(0.1)

        messages = probe_agent.get_messages()
        assert len(messages) == 1  # Second agent should not publish as data is empty

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {}

        probe_agent.clear_messages()

        # Get the updated guild state
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoGuildState(guild_id=guild.id),
        )

        time.sleep(0.1)

        messages = probe_agent.get_messages()
        assert len(messages) == 2

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {"new_key": "new_value", "call_count": 1}

        assert messages[1].format == get_qualified_class_name(ReceivedData)
        assert messages[1].payload["data"] == {"new_key": "new_value", "call_count": 1}

        probe_agent.clear_messages()

        # Get Agent state and trigger the state update
        agent_update_routing_rule = RoutingRule(
            agent=AgentTag(id=state_aware_agent.id),
            method_name="echo_agent_state",
            agent_state_update=StateTransformer(
                update_format=StateUpdateFormat.JSON_PATCH,
                state_update=dedent(
                    """
                    {
                    "operations": [
                    {"op": "add", "path": "/new_key", "value": "new_value"},
                    {"op": "add", "path": "/call_count", "value": 1}
                ]}
                """
                ),
            ),
        )

        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoAgentState(guild_id=guild.id, agent_id=state_aware_agent.id),
            routing_slip=RoutingSlip(steps=[agent_update_routing_rule]),
        )

        time.sleep(0.1)

        messages = probe_agent.get_messages()

        assert len(messages) == 1

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {}

        probe_agent.clear_messages()

        # Get the updated agent state
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoAgentState(guild_id=guild.id, agent_id=state_aware_agent.id),
        )

        time.sleep(0.1)

        messages = probe_agent.get_messages()
        assert len(messages) == 2

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {"new_key": "new_value", "call_count": 1}
