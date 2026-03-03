"""
Tests for VendingMachineAgent.
"""

import time

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.vending_bench.config import (
    DEFAULT_PRICES,
    DEFAULT_STOCK,
    STARTING_CAPITAL,
    ProductType,
)
from rustic_ai.showcase.vending_bench.messages import (
    CheckBalanceRequest,
    CheckBalanceResponse,
    CheckInventoryRequest,
    CheckInventoryResponse,
    CollectCashRequest,
    CollectCashResponse,
    CustomerPurchaseEvent,
    SetPriceRequest,
    SetPriceResponse,
)


class TestVendingMachineAgent:
    """Tests for VendingMachineAgent."""

    def test_check_inventory(self, org_id, vending_machine_spec):
        """VendingMachineAgent should respond to inventory checks."""
        builder = GuildBuilder(
            guild_id=f"vm_test_{shortuuid.uuid()}",
            guild_name="VM Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(vending_machine_spec)
        guild = builder.launch(org_id)

        # Add probe agent
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send inventory check request
        request = CheckInventoryRequest()
        probe.publish_dict(
            "VENDING_STATE",
            request.model_dump(),
            format=get_qualified_class_name(CheckInventoryRequest),
        )

        time.sleep(0.5)

        # Check for response
        messages = probe.get_messages()
        inventory_responses = [m for m in messages if m.format == get_qualified_class_name(CheckInventoryResponse)]

        assert len(inventory_responses) >= 1
        response_payload = inventory_responses[0].payload
        assert "inventory" in response_payload

        guild.shutdown()

    def test_check_balance(self, org_id, vending_machine_spec):
        """VendingMachineAgent should respond to balance checks."""
        builder = GuildBuilder(
            guild_id=f"vm_test_{shortuuid.uuid()}",
            guild_name="VM Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(vending_machine_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        request = CheckBalanceRequest()
        probe.publish_dict(
            "VENDING_STATE",
            request.model_dump(),
            format=get_qualified_class_name(CheckBalanceRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        balance_responses = [m for m in messages if m.format == get_qualified_class_name(CheckBalanceResponse)]

        assert len(balance_responses) >= 1
        response_payload = balance_responses[0].payload
        assert response_payload["operator_cash"] == STARTING_CAPITAL
        assert response_payload["machine_cash"] == 0.0
        assert "net_worth" in response_payload

        guild.shutdown()

    def test_set_price(self, org_id, vending_machine_spec):
        """VendingMachineAgent should handle price changes."""
        builder = GuildBuilder(
            guild_id=f"vm_test_{shortuuid.uuid()}",
            guild_name="VM Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(vending_machine_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Set new price for chips
        old_price = DEFAULT_PRICES[ProductType.CHIPS]
        new_price = 2.25
        request = SetPriceRequest(product=ProductType.CHIPS, new_price=new_price)
        probe.publish_dict(
            "VENDING_STATE",
            request.model_dump(),
            format=get_qualified_class_name(SetPriceRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        price_responses = [m for m in messages if m.format == get_qualified_class_name(SetPriceResponse)]

        assert len(price_responses) >= 1
        response_payload = price_responses[0].payload
        assert response_payload["old_price"] == old_price
        assert response_payload["new_price"] == new_price
        assert response_payload["success"] is True

        guild.shutdown()

    def test_collect_cash(self, org_id, vending_machine_spec):
        """VendingMachineAgent should handle cash collection."""
        builder = GuildBuilder(
            guild_id=f"vm_test_{shortuuid.uuid()}",
            guild_name="VM Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(vending_machine_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .add_additional_topic("PURCHASES")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # First simulate a purchase to put cash in the machine
        purchase = CustomerPurchaseEvent(
            product=ProductType.SODA,
            quantity=5,
            price_paid=2.0,
            day=1,
            time_of_day_minutes=100,
        )
        probe.publish_dict(
            "PURCHASES",
            purchase.model_dump(),
            format=get_qualified_class_name(CustomerPurchaseEvent),
        )

        time.sleep(0.3)

        # Now collect cash
        request = CollectCashRequest()
        probe.publish_dict(
            "VENDING_STATE",
            request.model_dump(),
            format=get_qualified_class_name(CollectCashRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        collect_responses = [m for m in messages if m.format == get_qualified_class_name(CollectCashResponse)]

        assert len(collect_responses) >= 1
        response_payload = collect_responses[0].payload
        # Cash collected should be 5 * 2.0 = 10.0
        assert response_payload["amount_collected"] == 10.0
        assert response_payload["new_machine_balance"] == 0.0
        assert response_payload["new_operator_balance"] == STARTING_CAPITAL + 10.0

        guild.shutdown()

    def test_process_purchase(self, org_id, vending_machine_spec):
        """VendingMachineAgent should process customer purchases."""
        builder = GuildBuilder(
            guild_id=f"vm_test_{shortuuid.uuid()}",
            guild_name="VM Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(vending_machine_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("VENDING_STATE")
            .add_additional_topic("PURCHASES")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Simulate purchase
        purchase = CustomerPurchaseEvent(
            product=ProductType.CHIPS,
            quantity=3,
            price_paid=1.50,
            day=1,
            time_of_day_minutes=200,
        )
        probe.publish_dict(
            "PURCHASES",
            purchase.model_dump(),
            format=get_qualified_class_name(CustomerPurchaseEvent),
        )

        time.sleep(0.3)

        # Check balance to verify purchase was processed
        balance_request = CheckBalanceRequest()
        probe.publish_dict(
            "VENDING_STATE",
            balance_request.model_dump(),
            format=get_qualified_class_name(CheckBalanceRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        balance_responses = [m for m in messages if m.format == get_qualified_class_name(CheckBalanceResponse)]

        assert len(balance_responses) >= 1
        response_payload = balance_responses[0].payload
        # Machine cash should be 3 * 1.50 = 4.50
        assert response_payload["machine_cash"] == 4.50

        # Also check inventory decreased
        inv_request = CheckInventoryRequest()
        probe.publish_dict(
            "VENDING_STATE",
            inv_request.model_dump(),
            format=get_qualified_class_name(CheckInventoryRequest),
        )

        time.sleep(0.5)

        messages = probe.get_messages()
        inv_responses = [m for m in messages if m.format == get_qualified_class_name(CheckInventoryResponse)]

        # Should have the original inventory minus 3 chips
        # Find the latest inventory response
        latest_inv = inv_responses[-1].payload
        expected_chips = DEFAULT_STOCK[ProductType.CHIPS] - 3
        assert latest_inv["inventory"]["chips"] == expected_chips

        guild.shutdown()
