"""
Tests for CustomerComplaintAgent.
"""

import time

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.vending_bench.messages import (
    DayUpdateEvent,
    Email,
    SimulationTime,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    RespondToComplaintRequest,
    RespondToComplaintResponse,
    ViewComplaintsRequest,
    ViewComplaintsResponse,
)


class TestCustomerComplaintAgent:
    """Tests for CustomerComplaintAgent."""

    def test_generates_complaints_on_day_event(self, org_id, customer_complaint_spec):
        """CustomerComplaintAgent should generate complaints on day events."""
        builder = GuildBuilder(
            guild_id=f"complaint_test_{shortuuid.uuid()}",
            guild_name="Complaint Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_complaint_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("COMPLAINTS")
            .add_additional_topic("EMAIL")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Simulate a day start event
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

        # Send multiple day events to increase chance of complaint generation
        for day in range(2, 10):  # Send 8 events for higher probability
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
            time.sleep(0.2)

        time.sleep(1.0)

        messages = probe.get_messages()

        # With 50% complaint rate over 8+ days, we should have at least one email
        email_messages = [m for m in messages if m.format == get_qualified_class_name(Email)]
        assert len(email_messages) >= 1, "Agent should generate at least one complaint email"

        # Verify the agent is working by requesting to view complaints
        view_request = ViewComplaintsRequest()
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            view_request.model_dump(),
            format=get_qualified_class_name(ViewComplaintsRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        view_responses = [m for m in messages if m.format == get_qualified_class_name(ViewComplaintsResponse)]
        assert len(view_responses) >= 1, "Agent should respond to view complaints request"

        guild.shutdown()

    def test_view_complaints(self, org_id, customer_complaint_spec):
        """CustomerComplaintAgent should return complaints list."""
        builder = GuildBuilder(
            guild_id=f"complaint_view_test_{shortuuid.uuid()}",
            guild_name="Complaint View Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_complaint_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("COMPLAINTS")
            .add_additional_topic("EMAIL")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # First, generate a complaint by sending a day event multiple times
        for day in range(1, 5):
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
            time.sleep(0.3)

        # Now request to view complaints
        view_request = ViewComplaintsRequest()
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            view_request.model_dump(),
            format=get_qualified_class_name(ViewComplaintsRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        view_responses = [m for m in messages if m.format == get_qualified_class_name(ViewComplaintsResponse)]

        assert len(view_responses) >= 1
        response = view_responses[-1].payload
        assert "complaints" in response
        assert "total_open" in response
        assert "total_pending_refunds" in response

        guild.shutdown()

    def test_respond_to_complaint_refund(self, org_id, customer_complaint_spec):
        """CustomerComplaintAgent should process refund for complaint."""
        builder = GuildBuilder(
            guild_id=f"complaint_refund_test_{shortuuid.uuid()}",
            guild_name="Complaint Refund Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_complaint_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("COMPLAINTS")
            .add_additional_topic("EMAIL")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Generate complaints
        for day in range(1, 6):
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
            time.sleep(0.2)

        # Get complaints
        view_request = ViewComplaintsRequest()
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            view_request.model_dump(),
            format=get_qualified_class_name(ViewComplaintsRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        view_responses = [m for m in messages if m.format == get_qualified_class_name(ViewComplaintsResponse)]

        if view_responses and view_responses[-1].payload.get("complaints"):
            complaint_id = view_responses[-1].payload["complaints"][0]["complaint_id"]

            # Respond with refund
            respond_request = RespondToComplaintRequest(
                complaint_id=complaint_id,
                action="refund",
                response_message="We apologize for the inconvenience.",
            )
            probe.publish_dict(
                guild.DEFAULT_TOPIC,
                respond_request.model_dump(),
                format=get_qualified_class_name(RespondToComplaintRequest),
            )

            time.sleep(0.5)

            messages = probe.get_messages()
            respond_responses = [
                m for m in messages if m.format == get_qualified_class_name(RespondToComplaintResponse)
            ]

            assert len(respond_responses) >= 1
            response = respond_responses[-1].payload
            assert response["success"] is True
            assert response["complaint_id"] == complaint_id

        guild.shutdown()

    def test_respond_to_complaint_deny(self, org_id, customer_complaint_spec):
        """CustomerComplaintAgent should handle denied complaints."""
        builder = GuildBuilder(
            guild_id=f"complaint_deny_test_{shortuuid.uuid()}",
            guild_name="Complaint Deny Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_complaint_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("COMPLAINTS")
            .add_additional_topic("EMAIL")
            .add_additional_topic("SIMULATION_EVENTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Generate complaints
        for day in range(1, 6):
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
            time.sleep(0.2)

        # Get complaints
        view_request = ViewComplaintsRequest()
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            view_request.model_dump(),
            format=get_qualified_class_name(ViewComplaintsRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        view_responses = [m for m in messages if m.format == get_qualified_class_name(ViewComplaintsResponse)]

        if view_responses and view_responses[-1].payload.get("complaints"):
            complaint_id = view_responses[-1].payload["complaints"][0]["complaint_id"]

            # Respond with deny
            respond_request = RespondToComplaintRequest(
                complaint_id=complaint_id,
                action="deny",
                response_message="We cannot process your request.",
            )
            probe.publish_dict(
                guild.DEFAULT_TOPIC,
                respond_request.model_dump(),
                format=get_qualified_class_name(RespondToComplaintRequest),
            )

            time.sleep(0.5)

            messages = probe.get_messages()
            respond_responses = [
                m for m in messages if m.format == get_qualified_class_name(RespondToComplaintResponse)
            ]

            assert len(respond_responses) >= 1
            response = respond_responses[-1].payload
            assert response["success"] is True
            assert response["refund_processed"] == 0.0

        guild.shutdown()

    def test_complaint_not_found(self, org_id, customer_complaint_spec):
        """CustomerComplaintAgent should handle invalid complaint ID."""
        builder = GuildBuilder(
            guild_id=f"complaint_notfound_test_{shortuuid.uuid()}",
            guild_name="Complaint NotFound Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(customer_complaint_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("COMPLAINTS")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Try to respond to non-existent complaint
        respond_request = RespondToComplaintRequest(
            complaint_id="CMP-NOTFOUND",
            action="refund",
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            respond_request.model_dump(),
            format=get_qualified_class_name(RespondToComplaintRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        respond_responses = [m for m in messages if m.format == get_qualified_class_name(RespondToComplaintResponse)]

        assert len(respond_responses) >= 1
        response = respond_responses[0].payload
        assert response["success"] is False
        assert "not found" in response["message"].lower()

        guild.shutdown()
