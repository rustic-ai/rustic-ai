"""
Integration tests for VendingBench simulation flow.
"""

import time

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.customer_simulator_agent import (
    CustomerSimulatorAgent,
)
from rustic_ai.showcase.vending_bench.economics import calculate_demand
from rustic_ai.showcase.vending_bench.evaluator_agent import EvaluatorAgent
from rustic_ai.showcase.vending_bench.messages import (
    CustomerPurchaseEvent,
    DayUpdateEvent,
    SimulationControlCommand,
    SimulationControlRequest,
    SimulationControlResponse,
    SimulationStatus,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.simulation_controller_agent import (
    SimulationControllerAgent,
)
from rustic_ai.showcase.vending_bench.vending_machine_agent import VendingMachineAgent


class TestEconomics:
    """Tests for economic calculations."""

    def test_calculate_demand_default(self):
        """Demand calculation should return positive values."""
        demand = calculate_demand(
            product=ProductType.SODA,
            current_price=2.0,
            day_of_week=0,
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )
        assert demand >= 0
        assert isinstance(demand, int)

    def test_calculate_demand_price_effect(self):
        """Higher prices should reduce demand."""
        low_price_demand = calculate_demand(
            product=ProductType.CHIPS,
            current_price=1.0,
            day_of_week=0,
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )

        high_price_demand = calculate_demand(
            product=ProductType.CHIPS,
            current_price=3.0,
            day_of_week=0,
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )

        # Higher price should mean lower demand
        assert high_price_demand < low_price_demand

    def test_calculate_demand_hot_weather_drinks(self):
        """Hot weather should increase drink demand."""
        normal_demand = calculate_demand(
            product=ProductType.SODA,
            current_price=2.0,
            day_of_week=0,
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )

        hot_demand = calculate_demand(
            product=ProductType.SODA,
            current_price=2.0,
            day_of_week=0,
            weather=WeatherType.HOT,
            add_randomness=False,
        )

        # Hot weather should increase drink demand
        assert hot_demand > normal_demand

    def test_calculate_demand_weekend_effect(self):
        """Weekend should have higher demand."""
        weekday_demand = calculate_demand(
            product=ProductType.CHIPS,
            current_price=1.5,
            day_of_week=0,  # Monday
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )

        weekend_demand = calculate_demand(
            product=ProductType.CHIPS,
            current_price=1.5,
            day_of_week=5,  # Saturday
            weather=WeatherType.SUNNY,
            add_randomness=False,
        )

        # Weekend should have higher demand
        assert weekend_demand > weekday_demand


class TestSimulationController:
    """Tests for SimulationControllerAgent."""

    def test_simulation_start(self, org_id, simulation_controller_spec):
        """SimulationControllerAgent should handle start command."""
        builder = GuildBuilder(
            guild_id=f"sim_test_{shortuuid.uuid()}",
            guild_name="Sim Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(simulation_controller_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SIMULATION_CONTROL")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send start command
        request = SimulationControlRequest(command=SimulationControlCommand.START)
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            request.model_dump(),
            format=get_qualified_class_name(SimulationControlRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()

        # Should receive SimulationControlResponse
        control_responses = [m for m in messages if m.format == get_qualified_class_name(SimulationControlResponse)]
        assert len(control_responses) >= 1
        response = control_responses[0].payload
        assert response["simulation_status"] == SimulationStatus.RUNNING.value

        # Should also receive DayUpdateEvent for day 1
        day_events = [m for m in messages if m.format == get_qualified_class_name(DayUpdateEvent)]
        assert len(day_events) >= 1
        day_event = day_events[0].payload
        assert day_event["day"] == 1

        guild.shutdown()

    def test_simulation_pause_resume(self, org_id, simulation_controller_spec):
        """SimulationControllerAgent should handle pause and resume."""
        builder = GuildBuilder(
            guild_id=f"sim_test_{shortuuid.uuid()}",
            guild_name="Sim Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(simulation_controller_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SIMULATION_CONTROL")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Start
        start_request = SimulationControlRequest(command=SimulationControlCommand.START)
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            start_request.model_dump(),
            format=get_qualified_class_name(SimulationControlRequest),
        )
        time.sleep(0.3)

        # Pause
        pause_request = SimulationControlRequest(command=SimulationControlCommand.PAUSE)
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            pause_request.model_dump(),
            format=get_qualified_class_name(SimulationControlRequest),
        )
        time.sleep(0.3)

        # Resume
        resume_request = SimulationControlRequest(command=SimulationControlCommand.RESUME)
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            resume_request.model_dump(),
            format=get_qualified_class_name(SimulationControlRequest),
        )
        time.sleep(0.5)

        messages = probe.get_messages()
        control_responses = [m for m in messages if m.format == get_qualified_class_name(SimulationControlResponse)]

        # Should have responses for start, pause, and resume
        assert len(control_responses) >= 3

        # Last response should be RUNNING (resumed)
        statuses = [r.payload["simulation_status"] for r in control_responses]
        assert SimulationStatus.RUNNING.value in statuses
        assert SimulationStatus.PAUSED.value in statuses

        guild.shutdown()


class TestCustomerSimulator:
    """Tests for CustomerSimulatorAgent."""

    def test_generates_purchases_on_day_event(self, org_id, customer_simulator_spec):
        """CustomerSimulatorAgent should generate purchases on day events."""
        builder = GuildBuilder(
            guild_id=f"cust_test_{shortuuid.uuid()}",
            guild_name="Customer Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_simulator_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SIMULATION_EVENTS")
            .add_additional_topic("PURCHASES")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Simulate a day start event
        from rustic_ai.showcase.vending_bench.messages import SimulationTime

        sim_time = SimulationTime(
            current_day=1,
            current_time_minutes=0,
            is_daytime=True,
            weather=WeatherType.SUNNY,
            day_of_week=0,
        )
        day_event = DayUpdateEvent(
            day=1,
            weather=WeatherType.SUNNY,
            day_of_week=0,
            simulation_time=sim_time,
            daily_fee_deducted=0,
            remaining_cash=500,
            days_without_payment=0,
        )
        probe.publish_dict(
            "SIMULATION_EVENTS",
            day_event.model_dump(),
            format=get_qualified_class_name(DayUpdateEvent),
        )

        time.sleep(1.0)  # Allow time for purchase generation

        messages = probe.get_messages()
        purchase_events = [m for m in messages if m.format == get_qualified_class_name(CustomerPurchaseEvent)]

        # Should generate multiple purchases
        assert len(purchase_events) > 0

        # Verify purchase structure
        for purchase in purchase_events:
            payload = purchase.payload
            assert "product" in payload
            assert "quantity" in payload
            assert payload["quantity"] >= 1

        guild.shutdown()


class TestIntegrationFlow:
    """Integration tests for full simulation flow."""

    def test_full_simulation_flow(self, org_id):
        """Test a complete simulation flow with all agents."""
        # Build guild with all agents
        builder = GuildBuilder(
            guild_id=f"full_test_{shortuuid.uuid()}",
            guild_name="Full Test Guild",
            guild_description="Full integration test",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        # Add agents
        vm_spec = (
            AgentBuilder(VendingMachineAgent)
            .set_id("vending_machine")
            .set_name("VendingMachine")
            .set_description("Vending machine")
            .listen_to_default_topic(True)  # Required to receive SupplierDelivery messages
            .add_additional_topic("VENDING_STATE")
            .add_additional_topic("PURCHASES")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )

        cust_spec = (
            AgentBuilder(CustomerSimulatorAgent)
            .set_id("customer_simulator")
            .set_name("CustomerSimulator")
            .set_description("Customer simulator")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )

        sim_spec = (
            AgentBuilder(SimulationControllerAgent)
            .set_id("simulation_controller")
            .set_name("SimController")
            .set_description("Simulation controller")
            .listen_to_default_topic(True)
            .add_additional_topic("SIMULATION_CONTROL")
            .build_spec()
        )

        eval_spec = (
            AgentBuilder(EvaluatorAgent)
            .set_id("evaluator")
            .set_name("Evaluator")
            .set_description("Evaluator")
            .add_additional_topic("EVALUATION")
            .add_additional_topic("SIMULATION_EVENTS")
            .add_additional_topic("PURCHASES")
            .build_spec()
        )

        builder.add_agent_spec(vm_spec)
        builder.add_agent_spec(cust_spec)
        builder.add_agent_spec(sim_spec)
        builder.add_agent_spec(eval_spec)

        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .add_additional_topic("PURCHASES")
            .add_additional_topic("SIMULATION_EVENTS")
            .add_additional_topic("SIMULATION_CONTROL")
            .add_additional_topic("EVALUATION")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Start simulation
        start_request = SimulationControlRequest(command=SimulationControlCommand.START)
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            start_request.model_dump(),
            format=get_qualified_class_name(SimulationControlRequest),
        )

        # Allow time for messages to flow
        time.sleep(2.0)

        messages = probe.get_messages()

        # Verify we got all expected message types
        message_formats = {m.format for m in messages}

        # Should have control response
        assert get_qualified_class_name(SimulationControlResponse) in message_formats

        # Should have day event
        assert get_qualified_class_name(DayUpdateEvent) in message_formats

        # Should have purchases (from customer simulator)
        assert get_qualified_class_name(CustomerPurchaseEvent) in message_formats

        guild.shutdown()
