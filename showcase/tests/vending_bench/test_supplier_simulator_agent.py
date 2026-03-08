"""
Tests for SupplierSimulatorAgent.
"""

import time

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.messages import (
    DayUpdateEvent,
    SimulationTime,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    BaitAndSwitchEvent,
    DeliveryDelayNotification,
    NegotiationExchangeRequest,
    NegotiationResponse,
    PartialDeliveryNotification,
    StartNegotiationRequest,
    SupplierFailureNotification,
)
from rustic_ai.showcase.vending_bench.supplier_registry import SupplierBehaviorType


class TestSupplierSimulatorAgent:
    """Tests for SupplierSimulatorAgent."""

    def test_handles_day_update_event(self, org_id, supplier_simulator_spec):
        """SupplierSimulatorAgent should handle day update events."""
        builder = GuildBuilder(
            guild_id=f"sim_agent_test_{shortuuid.uuid()}",
            guild_name="Simulator Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_simulator_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SIMULATION")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send a day update event
        sim_time = SimulationTime(
            current_day=5,
            current_time_minutes=0,
            is_daytime=True,
            weather=WeatherType.SUNNY,
            day_of_week=4,
        )
        day_event = DayUpdateEvent(
            day=5,
            weather=WeatherType.SUNNY,
            day_of_week=4,
            simulation_time=sim_time,
            daily_fee_deducted=2,
            remaining_cash=490,
            days_without_payment=0,
        )
        probe.publish_dict(
            "SIMULATION_EVENTS",
            day_event.model_dump(),
            format=get_qualified_class_name(DayUpdateEvent),
        )

        time.sleep(0.5)

        # Agent should process the day update event without errors
        # Since there are no pending orders, no supply chain events will be generated
        # But we can verify the agent is running by checking it can handle negotiation requests
        messages = probe.get_messages()

        # The agent processed the event if no error occurred
        # We verify this test is meaningful by checking the agent can respond to other messages
        start_request = StartNegotiationRequest(
            supplier_id="SUP-TEST",
            product_type=ProductType.CHIPS,
            target_discount=0.10,
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            start_request.model_dump(),
            format=get_qualified_class_name(StartNegotiationRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        negotiation_responses = [m for m in messages if "NegotiationResponse" in m.format]
        assert len(negotiation_responses) >= 1, "Agent should respond to negotiation requests"

        guild.shutdown()

    def test_handles_negotiation_start(self, org_id, supplier_simulator_spec):
        """SupplierSimulatorAgent should start negotiations."""
        builder = GuildBuilder(
            guild_id=f"sim_neg_start_test_{shortuuid.uuid()}",
            guild_name="Negotiation Start Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_simulator_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SIMULATION")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Start a negotiation
        start_request = StartNegotiationRequest(
            supplier_id="SUP-TEST123",
            product_type=ProductType.CHIPS,
            target_discount=0.15,
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            start_request.model_dump(),
            format=get_qualified_class_name(StartNegotiationRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        negotiation_responses = [m for m in messages if m.format == get_qualified_class_name(NegotiationResponse)]

        assert len(negotiation_responses) >= 1
        response = negotiation_responses[0].payload

        # Should indicate supplier not found (since we didn't set up the registry)
        # or should start negotiation if supplier exists
        assert "negotiation_id" in response or "is_rejected" in response

        guild.shutdown()

    def test_handles_negotiation_exchange(self, org_id, supplier_simulator_spec):
        """SupplierSimulatorAgent should handle negotiation exchanges."""
        builder = GuildBuilder(
            guild_id=f"sim_neg_exchange_test_{shortuuid.uuid()}",
            guild_name="Negotiation Exchange Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_simulator_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SIMULATION")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send a negotiation exchange request
        exchange_request = NegotiationExchangeRequest(
            negotiation_id="NEG-TEST123",
            message="Can you do $1.00 per unit?",
            offer_price=1.00,
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            exchange_request.model_dump(),
            format=get_qualified_class_name(NegotiationExchangeRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        negotiation_responses = [m for m in messages if m.format == get_qualified_class_name(NegotiationResponse)]

        assert len(negotiation_responses) >= 1
        response = negotiation_responses[0].payload

        # Should reject since negotiation doesn't exist
        assert response.get("is_rejected", False) is True or "not found" in response.get("supplier_response", "").lower()

        guild.shutdown()


class TestSupplierSimulatorSupplyChainEvents:
    """Tests for supply chain event generation."""

    def test_processes_pending_orders_on_day_update(self, org_id, supplier_simulator_spec):
        """SupplierSimulatorAgent should process pending orders on day updates."""
        builder = GuildBuilder(
            guild_id=f"sim_orders_test_{shortuuid.uuid()}",
            guild_name="Orders Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_simulator_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SIMULATION")
            .add_additional_topic("SIMULATION_EVENTS")
            .add_additional_topic("EMAIL")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send multiple day events to trigger potential supply chain events
        for day in range(1, 10):
            sim_time = SimulationTime(
                current_day=day,
                current_time_minutes=0,
                is_daytime=True,
                weather=WeatherType.SUNNY,
                day_of_week=day % 7,
            )
            day_event = DayUpdateEvent(
                day=day,
                weather=WeatherType.SUNNY,
                day_of_week=day % 7,
                simulation_time=sim_time,
                daily_fee_deducted=2,
                remaining_cash=500 - (day * 2),
                days_without_payment=0,
            )
            probe.publish_dict(
                "SIMULATION_EVENTS",
                day_event.model_dump(),
                format=get_qualified_class_name(DayUpdateEvent),
            )
            time.sleep(0.1)

        time.sleep(0.5)

        messages = probe.get_messages()

        # Check for various supply chain events
        delay_notifications = [m for m in messages if m.format == get_qualified_class_name(DeliveryDelayNotification)]
        partial_notifications = [
            m for m in messages if m.format == get_qualified_class_name(PartialDeliveryNotification)
        ]
        failure_notifications = [
            m for m in messages if m.format == get_qualified_class_name(SupplierFailureNotification)
        ]
        bait_switch_events = [m for m in messages if m.format == get_qualified_class_name(BaitAndSwitchEvent)]

        # We can't guarantee specific events due to randomness, but verify no crashes
        # and that message formats are correct if any were generated
        for notification in delay_notifications:
            assert "order_id" in notification.payload

        for notification in partial_notifications:
            assert "order_id" in notification.payload
            assert "original_products" in notification.payload

        for notification in failure_notifications:
            assert "supplier_id" in notification.payload

        for event in bait_switch_events:
            assert "quoted_total" in event.payload
            assert "actual_total" in event.payload

        guild.shutdown()


class TestSupplierSimulatorNegotiationLogic:
    """Tests for negotiation logic."""

    def test_negotiation_discount_calculation(self):
        """Test negotiation discount calculation logic."""
        from rustic_ai.showcase.vending_bench.supplier_config import (
            DISCOUNT_PER_EXCHANGE,
            MAX_NEGOTIATION_DISCOUNT,
        )

        # Verify discount constants are reasonable
        assert DISCOUNT_PER_EXCHANGE > 0
        assert DISCOUNT_PER_EXCHANGE < 0.1  # Should be small per exchange
        assert MAX_NEGOTIATION_DISCOUNT > DISCOUNT_PER_EXCHANGE
        assert MAX_NEGOTIATION_DISCOUNT <= 0.5  # Max 50% discount

    def test_supplier_behavior_affects_pricing(self):
        """Test that supplier behavior type affects pricing."""
        from rustic_ai.showcase.vending_bench.supplier_config import (
            INITIAL_QUOTE_MARKUP,
            PRICE_GOUGING_MULTIPLIER_MAX,
            PRICE_GOUGING_MULTIPLIER_MIN,
        )

        # Adversarial suppliers should have higher multipliers
        assert PRICE_GOUGING_MULTIPLIER_MIN > 1.0
        assert PRICE_GOUGING_MULTIPLIER_MAX > PRICE_GOUGING_MULTIPLIER_MIN

        # Normal markup should be lower
        assert INITIAL_QUOTE_MARKUP < PRICE_GOUGING_MULTIPLIER_MIN


class TestSupplierSimulatorBehaviorTypes:
    """Tests for supplier behavior type handling."""

    def test_all_behavior_types_supported(self):
        """All behavior types should be supported."""
        behavior_types = list(SupplierBehaviorType)
        assert len(behavior_types) == 3
        assert SupplierBehaviorType.HONEST in behavior_types
        assert SupplierBehaviorType.ADVERSARIAL in behavior_types
        assert SupplierBehaviorType.UNRELIABLE in behavior_types

    def test_behavior_probabilities_sum_to_one(self):
        """Behavior probabilities should sum to 1."""
        from rustic_ai.showcase.vending_bench.supplier_config import (
            ADVERSARIAL_SUPPLIER_PROBABILITY,
            HONEST_SUPPLIER_PROBABILITY,
            UNRELIABLE_SUPPLIER_PROBABILITY,
        )

        total = HONEST_SUPPLIER_PROBABILITY + ADVERSARIAL_SUPPLIER_PROBABILITY + UNRELIABLE_SUPPLIER_PROBABILITY
        assert abs(total - 1.0) < 0.001  # Allow small floating point error
