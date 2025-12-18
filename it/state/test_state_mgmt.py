import os
import time

from flaky import flaky
from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.agent import (
    Agent,
    ProcessContext,
    processor,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.dsl import AgentSpec, GuildTopics, JSONataPredicate
from rustic_ai.core.guild.dsl import KeyConstants as GSKC
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    RoutingSlip,
)
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.jexpr import JArray, JObj, JxScript
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
    @processor(EchoGuildState)
    def echo_guild_state(self, ctx: ProcessContext[EchoGuildState]) -> None:
        ctx.send(PublishedData(data=self.get_guild_state()))

    @processor(EchoAgentState)
    def echo_agent_state(self, ctx: ProcessContext[EchoAgentState]) -> None:
        ctx.send(PublishedData(data=self.get_agent_state()))


class StateFreeAgent(Agent):
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
            .add_predicate("echo_data", JSONataPredicate(expression="$count($keys(message.payload.data)) != 0"))
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

    @pytest.mark.parametrize(
        "state_manager_class,state_manager_config",
        [
            ("rustic_ai.core.state.manager.in_memory_state_manager.InMemoryStateManager", {}),
            ("rustic_ai.redis.state.manager.RedisStateManager", {"host": "localhost", "port": 6379}),
        ],
    )
    @flaky(max_runs=3, min_passes=1)
    def test_state_mgmt(
        self,
        state_aware_agent: AgentSpec,
        state_free_agent: AgentSpec,
        database,
        org_id,
        state_manager_class: str,
        state_manager_config: dict,
    ):
        builder = (
            GuildBuilder(f"state_guild_{int(time.time())}", "State Guild", "Guild to test state management")
            .add_agent_spec(state_aware_agent)
            .add_agent_spec(state_free_agent)
            .set_messaging(
                backend_module="rustic_ai.redis.messaging.backend",
                backend_class="RedisMessagingBackend",
                backend_config={"redis_client": {"host": "localhost", "port": 6379}},
            )
            .set_property(GSKC.STATE_MANAGER, state_manager_class)
            .set_property(GSKC.STATE_MANAGER_CONFIG, state_manager_config)
        )

        engine = Metastore.get_engine(database)  # noqa: F841
        guild = builder.bootstrap(database, org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("ProbeAgent")
            .set_description("A probe agent")
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(GuildTopics.GUILD_STATUS_TOPIC)
            .add_additional_topic("echo_topic")
            .add_additional_topic(GuildTopics.STATE_TOPIC)
            .build_spec()
        )

        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        guild_update_routing_rule = (
            RouteBuilder(AgentTag(id=state_aware_agent.id))
            .from_method("echo_guild_state")
            .set_guild_state_update(JxScript(JObj({"new_key": "new_value", "call_count": 1})))
            .build()
        )

        # Get the guild state and trigger the state update
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoGuildState(guild_id=guild.id),
            routing_slip=RoutingSlip(steps=[guild_update_routing_rule]),
        )

        # Increased initial wait time for Redis message processing
        time.sleep(2)

        loop_count = 0
        messages = []
        while loop_count < 20:  # Increased from 10 to 20 iterations
            time.sleep(0.5)
            # Check if the agent has processed the request and sent the state
            messages = probe_agent.get_messages()
            if len(messages) > 0:
                break
            loop_count += 1

        assert (
            len(messages) == 1
        ), f"Expected 1 message, got {len(messages)}"  # Second agent should not publish as data is empty

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {}

        probe_agent.clear_messages()

        # Get the updated guild state
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoGuildState(guild_id=guild.id),
        )

        loop_count = 0
        while loop_count < 20:  # Increased from 10 to 20 iterations
            time.sleep(0.5)
            messages = probe_agent.get_messages()
            if len(messages) == 2:
                break
            loop_count += 1

        messages = probe_agent.get_messages()
        assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

        assert messages[0].format == get_qualified_class_name(PublishedData)

        # Check that the custom state is present in the guild state
        guild_state_data = messages[0].payload["data"]
        expected_custom_state = {"new_key": "new_value", "call_count": 1}

        # Verify all expected keys are present with correct values
        for key, expected_value in expected_custom_state.items():
            assert key in guild_state_data, f"Expected key '{key}' not found in guild state"
            assert (
                guild_state_data[key] == expected_value
            ), f"Expected {key}={expected_value}, got {guild_state_data[key]}"

        assert messages[1].format == get_qualified_class_name(ReceivedData)

        # Check that the custom state is present in the received data (from StateFreeAgent)
        received_state_data = messages[1].payload["data"]

        # Verify all expected keys are present with correct values
        for key, expected_value in expected_custom_state.items():
            assert key in received_state_data, f"Expected key '{key}' not found in received state"
            assert (
                received_state_data[key] == expected_value
            ), f"Expected {key}={expected_value}, got {received_state_data[key]}"

        probe_agent.clear_messages()

        agent_update_routing_rule = (
            RouteBuilder(AgentTag(id=state_aware_agent.id))
            .from_method("echo_agent_state")
            .set_agent_state_update(
                update_agent_state=JxScript(
                    JObj(
                        {
                            "operations": JArray(
                                [
                                    JObj({"op": "add", "path": "/new_key", "value": "new_value"}),
                                    JObj({"op": "add", "path": "/call_count", "value": 1}),
                                ]
                            )
                        }
                    )
                ),
                update_format=StateUpdateFormat.JSON_PATCH,
            )
            .build()
        )

        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoAgentState(guild_id=guild.id, agent_id=state_aware_agent.id),
            routing_slip=RoutingSlip(steps=[agent_update_routing_rule]),
        )

        # Increased initial wait time for Redis message processing
        time.sleep(2)

        loop_count = 0
        messages = []
        while loop_count < 20:  # Increased from implicit 1 to 20 iterations
            time.sleep(0.5)
            messages = probe_agent.get_messages()
            if len(messages) > 0:
                break
            loop_count += 1

        assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"

        assert messages[0].format == get_qualified_class_name(PublishedData)
        assert messages[0].payload["data"] == {}

        probe_agent.clear_messages()

        # Get the updated agent state
        probe_agent.publish(
            topic=GuildTopics.DEFAULT_TOPICS[0],
            payload=EchoAgentState(guild_id=guild.id, agent_id=state_aware_agent.id),
        )

        loop_count = 0
        while loop_count < 20:  # Increased wait iterations
            time.sleep(0.5)
            messages = probe_agent.get_messages()
            if len(messages) == 2:
                break
            loop_count += 1

        messages = probe_agent.get_messages()
        assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

        assert messages[0].format == get_qualified_class_name(PublishedData)

        # Check that the custom state is present in the agent state
        agent_state_data = messages[0].payload["data"]
        expected_custom_state = {"new_key": "new_value", "call_count": 1}

        # Verify all expected keys are present with correct values
        for key, expected_value in expected_custom_state.items():
            assert key in agent_state_data, f"Expected key '{key}' not found in agent state"
            assert (
                agent_state_data[key] == expected_value
            ), f"Expected {key}={expected_value}, got {agent_state_data[key]}"
