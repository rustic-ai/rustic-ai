"""
Integration tests for G2G Saga session state preservation.

Tests the saga pattern with different combinations of messaging backends
and state managers to ensure session_state is preserved across guild
boundaries in production-like configurations.
"""

import os
import time

from flaky import flaky
import pytest

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import KeyConstants as GSKC
from rustic_ai.core.guild.g2g import (
    EnvoyAgent,
    EnvoyAgentProps,
    GatewayAgent,
    GatewayAgentProps,
)
from rustic_ai.core.guild.metastore.database import Metastore
from rustic_ai.core.utils import JsonDict


class SagaResponderAgent(Agent):
    """Agent that processes requests with saga state and sends responses.

    Used for testing session_state preservation across guild boundaries.
    """

    def __init__(self):
        self.received_messages = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyStateRequest")
    def handle_request(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Process request and send response."""
        self.received_messages.append(ctx.message)
        ctx.send_dict(
            payload={
                "response_to": ctx.payload.get("request_id"),
                "result": "success",
            },
            format="MyStateResponse",
        )


class SagaInitiatorAgent(Agent):
    """Agent that sends requests with session_state and captures responses.

    Used for testing session_state preservation across guild boundaries.
    """

    def __init__(self):
        self.responses_with_session_state = []

    @agent.processor(JsonDict, predicate=lambda self, msg: msg.format == "MyStateResponse")
    def handle_response(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        """Capture response with session_state."""
        self.responses_with_session_state.append(
            {
                "payload": ctx.payload,
                "session_state": ctx.message.session_state,
            }
        )


class TestSagaIntegration:
    """Integration tests for G2G saga session state preservation."""

    @pytest.fixture
    def database(self, request):
        """Database fixture with test-name-derived filename."""
        test_name = request.node.name.replace(":", "_").replace("[", "_").replace("]", "_").replace("/", "_")
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
        db_file = f"test_saga_integration_{test_name}_{worker_id}.db"
        db = f"sqlite:///{db_file}"

        if os.path.exists(db_file):
            os.remove(db_file)

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()

        yield db

        try:
            Metastore.drop_db()
        except Exception:
            pass
        finally:
            try:
                if os.path.exists(db_file):
                    os.remove(db_file)
            except Exception:
                pass

    @pytest.mark.parametrize(
        "messaging_module,messaging_class,messaging_config,state_manager_class,state_manager_config",
        [
            # In-Memory messaging + In-Memory state
            (
                "rustic_ai.core.messaging.backend",
                "InMemoryMessagingBackend",
                {},
                "rustic_ai.core.state.manager.in_memory_state_manager.InMemoryStateManager",
                {},
            ),
            # Redis messaging + Redis state
            (
                "rustic_ai.redis.messaging.backend",
                "RedisMessagingBackend",
                {"redis_client": {"host": "localhost", "port": 6379}},
                "rustic_ai.redis.state.manager.RedisStateManager",
                {"host": "localhost", "port": 6379},
            ),
        ],
        ids=["inmemory-inmemory", "redis-redis"],
    )
    @flaky(max_runs=4, min_passes=1)
    def test_saga_session_state_preservation(
        self,
        database,
        org_id,
        messaging_module: str,
        messaging_class: str,
        messaging_config: dict,
        state_manager_class: str,
        state_manager_config: dict,
    ):
        """Test that session_state is preserved across guild boundaries via saga pattern.

        When a message with session_state is forwarded to another guild:
        1. EnvoyAgent saves session_state to guild_state with a saga_id
        2. The saga_id is recorded in the GuildStackEntry
        3. When the response returns, GatewayAgent restores session_state from guild_state
        4. The restored session_state is available for continuation processing

        Setup:
        - Source guild sends a request WITH session_state
        - Target guild has a responder that processes and responds
        - Source guild verifies session_state is restored in the response
        """
        from rustic_ai.core.messaging import GuildStackEntry

        # Create source guild with state manager
        source_guild = (
            GuildBuilder(
                guild_name=f"source_guild_{int(time.time())}",
                guild_description="Source with session state",
            )
            .set_messaging(messaging_module, messaging_class, messaging_config)
            .set_property(GSKC.STATE_MANAGER, state_manager_class)
            .set_property(GSKC.STATE_MANAGER_CONFIG, state_manager_config)
            .bootstrap(database, org_id)
        )

        # Create target guild with state manager
        target_guild = (
            GuildBuilder(
                guild_name=f"target_guild_{int(time.time())}",
                guild_description="Target for session state test",
            )
            .set_messaging(messaging_module, messaging_class, messaging_config)
            .set_property(GSKC.STATE_MANAGER, state_manager_class)
            .set_property(GSKC.STATE_MANAGER_CONFIG, state_manager_config)
            .bootstrap(database, org_id)
        )

        try:
            # Configure target guild with gateway
            gateway_spec = (
                AgentBuilder(GatewayAgent)
                .set_id("gateway")
                .set_name("Gateway")
                .set_description("Gateway for target guild")
                .set_properties(
                    GatewayAgentProps(
                        input_formats=["MyStateRequest"],
                        output_formats=["MyStateResponse"],
                        returned_formats=["MyStateResponse"],
                    )
                )
                .build_spec()
            )
            target_guild._add_local_agent(gateway_spec)

            # Add responder to target guild
            responder_spec = (
                AgentBuilder(SagaResponderAgent)
                .set_id("responder")
                .set_name("SagaResponder")
                .set_description("Responder in target guild")
                .build_spec()
            )
            responder: SagaResponderAgent = target_guild._add_local_agent(responder_spec)  # type: ignore

            # Configure source guild with gateway for receiving responses
            source_gateway_spec = (
                AgentBuilder(GatewayAgent)
                .set_id("gateway")
                .set_name("Gateway")
                .set_description("Gateway for source guild")
                .set_properties(
                    GatewayAgentProps(
                        input_formats=["*"],
                        output_formats=["*"],
                        returned_formats=["MyStateResponse"],
                    )
                )
                .build_spec()
            )
            source_guild._add_local_agent(source_gateway_spec)

            # Add envoy to source guild for sending requests
            envoy_spec = (
                AgentBuilder(EnvoyAgent)
                .set_id("envoy")
                .set_name("EnvoyToTarget")
                .set_description("Envoy to target guild")
                .set_properties(
                    EnvoyAgentProps(
                        target_guild=target_guild.id,
                        formats_to_forward=["MyStateRequest"],
                    )
                )
                .add_additional_topic("outbound")
                .build_spec()
            )
            source_guild._add_local_agent(envoy_spec)

            # Add initiator to source guild to handle response
            initiator_spec = (
                AgentBuilder(SagaInitiatorAgent)
                .set_id("initiator")
                .set_name("SagaInitiator")
                .set_description("Initiator in source guild")
                .build_spec()
            )
            initiator: SagaInitiatorAgent = source_guild._add_local_agent(initiator_spec)  # type: ignore

            # Create probe to send the request directly
            probe_spec = (
                AgentBuilder(ProbeAgent)
                .set_id("probe")
                .set_name("Probe")
                .set_description("Probe in source guild")
                .build_spec()
            )
            probe: ProbeAgent = source_guild._add_local_agent(probe_spec)  # type: ignore

            # Allow agents to start (longer for Redis)
            time.sleep(2.0)

            # Send request directly from probe with session_state
            probe.publish_dict(
                topic="outbound",
                payload={"request_id": "saga_test_001", "action": "process"},
                format="MyStateRequest",
                session_state={
                    "user_context": "important_data",
                    "step": 1,
                    "correlation_id": "saga_test_001",
                },
            )

            # Wait for the round-trip (longer for Redis)
            max_wait = 10.0
            wait_interval = 0.5
            elapsed = 0.0
            while elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval
                if len(initiator.responses_with_session_state) >= 1:
                    break

            # Verify the responder in target guild received the request
            assert len(responder.received_messages) >= 1, "Target guild responder should receive request"
            received_msg = responder.received_messages[0]

            # Verify the session_state was NOT passed to the target guild (security)
            assert (
                not received_msg.session_state
            ), "Session state should NOT be passed across guild boundaries in the request"

            # Verify the origin_guild_stack has a GuildStackEntry with saga_id
            assert len(received_msg.origin_guild_stack) == 1, "Should have one entry in origin_guild_stack"
            stack_entry = received_msg.origin_guild_stack[0]
            assert isinstance(stack_entry, GuildStackEntry), "Stack entry should be GuildStackEntry"
            assert stack_entry.guild_id == source_guild.id, "Stack entry should have source guild ID"
            assert stack_entry.saga_id is not None, "Stack entry should have saga_id for session state preservation"

            # Verify the initiator received the response with session_state restored
            assert (
                len(initiator.responses_with_session_state) >= 1
            ), "Initiator should receive response with restored session_state"
            response_data = initiator.responses_with_session_state[0]

            # Verify payload
            assert response_data["payload"]["response_to"] == "saga_test_001"
            assert response_data["payload"]["result"] == "success"

            # Verify session_state was restored!
            restored_session_state = response_data["session_state"]
            assert restored_session_state is not None, "Session state should be restored when response returns"
            assert (
                restored_session_state.get("user_context") == "important_data"
            ), "Restored session_state should contain original user_context"
            assert restored_session_state.get("step") == 1, "Restored session_state should contain original step"
            assert (
                restored_session_state.get("correlation_id") == "saga_test_001"
            ), "Restored session_state should contain original correlation_id"

        finally:
            source_guild.shutdown()
            target_guild.shutdown()
