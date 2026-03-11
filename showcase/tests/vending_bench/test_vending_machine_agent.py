"""
Tests for VendingMachineAgent.
"""

import time
from typing import Callable, List, Optional

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.messaging.core.message import Message
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
from rustic_ai.showcase.vending_bench.supplier_messages import BaitAndSwitchEvent


def wait_for_message(
    probe: ProbeAgent,
    format_name: str,
    timeout: float = 2.0,
    poll_interval: float = 0.05,
    predicate: Optional[Callable[[Message], bool]] = None,
) -> List[Message]:
    """Poll for messages matching the expected format with a timeout.

    Args:
        probe: The probe agent to get messages from.
        format_name: The message format to filter for.
        timeout: Maximum time to wait in seconds.
        poll_interval: Time between polls in seconds.
        predicate: Optional additional filter function.

    Returns:
        List of matching messages.

    Raises:
        TimeoutError: If no matching message is found within the timeout.
    """
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        messages = probe.get_messages()
        matching = [m for m in messages if m.format == format_name]
        if predicate:
            matching = [m for m in matching if predicate(m)]
        if matching:
            return matching
        time.sleep(poll_interval)
    raise TimeoutError(f"No message with format '{format_name}' received within {timeout}s")


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

        try:
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

            # Poll for response
            inventory_responses = wait_for_message(probe, get_qualified_class_name(CheckInventoryResponse))
            response_payload = inventory_responses[0].payload
            assert "inventory" in response_payload
        finally:
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

        try:
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

            # Poll for response
            balance_responses = wait_for_message(probe, get_qualified_class_name(CheckBalanceResponse))
            response_payload = balance_responses[0].payload
            assert response_payload["operator_cash"] == STARTING_CAPITAL
            assert response_payload["machine_cash"] == 0.0
            assert "net_worth" in response_payload
        finally:
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

        try:
            # Set new price for chips
            old_price = DEFAULT_PRICES[ProductType.CHIPS]
            new_price = 2.25
            request = SetPriceRequest(product=ProductType.CHIPS, new_price=new_price)
            probe.publish_dict(
                "VENDING_STATE",
                request.model_dump(),
                format=get_qualified_class_name(SetPriceRequest),
            )

            # Poll for response
            price_responses = wait_for_message(probe, get_qualified_class_name(SetPriceResponse))
            response_payload = price_responses[0].payload
            assert response_payload["old_price"] == old_price
            assert response_payload["new_price"] == new_price
            assert response_payload["success"] is True
        finally:
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

        try:
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

            # Wait briefly for purchase to be processed (no response expected)
            time.sleep(0.1)

            # Now collect cash
            request = CollectCashRequest()
            probe.publish_dict(
                "VENDING_STATE",
                request.model_dump(),
                format=get_qualified_class_name(CollectCashRequest),
            )

            # Poll for response
            collect_responses = wait_for_message(probe, get_qualified_class_name(CollectCashResponse))
            response_payload = collect_responses[0].payload
            # Cash collected should be 5 * 2.0 = 10.0
            assert response_payload["amount_collected"] == 10.0
            assert response_payload["new_machine_balance"] == 0.0
            assert response_payload["new_operator_balance"] == STARTING_CAPITAL + 10.0
        finally:
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

        try:
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

            # Wait briefly for purchase to be processed (no response expected)
            time.sleep(0.1)

            # Check balance to verify purchase was processed
            balance_request = CheckBalanceRequest()
            probe.publish_dict(
                "VENDING_STATE",
                balance_request.model_dump(),
                format=get_qualified_class_name(CheckBalanceRequest),
            )

            # Poll for balance response
            balance_responses = wait_for_message(probe, get_qualified_class_name(CheckBalanceResponse))
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

            # Poll for inventory response
            inv_responses = wait_for_message(probe, get_qualified_class_name(CheckInventoryResponse))
            # Should have the original inventory minus 3 chips
            # Find the latest inventory response
            latest_inv = inv_responses[-1].payload
            expected_chips = DEFAULT_STOCK[ProductType.CHIPS] - 3
            assert latest_inv["inventory"]["chips"] == expected_chips
        finally:
            guild.shutdown()

    def test_bait_and_switch_partial_funds(self, org_id, vending_machine_spec):
        """VendingMachineAgent should use machine cash when operator cash is insufficient for bait-and-switch."""
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

        try:
            # First, add some machine cash via purchases
            purchase = CustomerPurchaseEvent(
                product=ProductType.SODA,
                quantity=10,
                price_paid=2.0,  # $20 in machine
                day=1,
                time_of_day_minutes=100,
            )
            probe.publish_dict(
                "PURCHASES",
                purchase.model_dump(),
                format=get_qualified_class_name(CustomerPurchaseEvent),
            )

            # Wait briefly for purchase to be processed (no response expected)
            time.sleep(0.1)

            # Send bait-and-switch event with amount greater than operator cash
            # Starting capital is $500, so charge $510 extra to use some machine cash
            bait_switch = BaitAndSwitchEvent(
                order_id="test_order_1",
                supplier_id="supplier_1",
                supplier_name="Shady Supplier",
                quoted_total=100.0,
                actual_total=610.0,
                difference=510.0,  # $510 extra - more than $500 operator cash
                day_occurred=1,
            )
            probe.publish_dict(
                guild.DEFAULT_TOPIC,
                bait_switch.model_dump(),
                format=get_qualified_class_name(BaitAndSwitchEvent),
            )

            # Wait briefly for bait-and-switch to be processed (no response expected)
            time.sleep(0.1)

            # Check balance
            balance_request = CheckBalanceRequest()
            probe.publish_dict(
                "VENDING_STATE",
                balance_request.model_dump(),
                format=get_qualified_class_name(CheckBalanceRequest),
            )

            # Poll for balance response
            balance_responses = wait_for_message(probe, get_qualified_class_name(CheckBalanceResponse))
            latest_balance = balance_responses[-1].payload

            # Operator cash should be 0 (depleted)
            assert latest_balance["operator_cash"] == 0.0
            # Machine cash should be reduced: $20 - ($510 - $500) = $20 - $10 = $10
            assert latest_balance["machine_cash"] == 10.0
        finally:
            guild.shutdown()

    def test_bait_and_switch_creates_debt(self, org_id, vending_machine_spec):
        """VendingMachineAgent should go into debt (negative operator cash) when funds are exhausted."""
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

        try:
            # Add some machine cash via purchases
            purchase = CustomerPurchaseEvent(
                product=ProductType.SODA,
                quantity=5,
                price_paid=2.0,  # $10 in machine
                day=1,
                time_of_day_minutes=100,
            )
            probe.publish_dict(
                "PURCHASES",
                purchase.model_dump(),
                format=get_qualified_class_name(CustomerPurchaseEvent),
            )

            # Wait briefly for purchase to be processed (no response expected)
            time.sleep(0.1)

            # Send bait-and-switch that exceeds all available funds
            # Starting capital $500 + machine cash $10 = $510 total
            # Charge $600 extra to create $90 debt
            bait_switch = BaitAndSwitchEvent(
                order_id="test_order_2",
                supplier_id="supplier_2",
                supplier_name="Very Shady Supplier",
                quoted_total=50.0,
                actual_total=650.0,
                difference=600.0,  # $600 extra - more than total available
                day_occurred=1,
            )
            probe.publish_dict(
                guild.DEFAULT_TOPIC,
                bait_switch.model_dump(),
                format=get_qualified_class_name(BaitAndSwitchEvent),
            )

            # Wait briefly for bait-and-switch to be processed (no response expected)
            time.sleep(0.1)

            # Check balance
            balance_request = CheckBalanceRequest()
            probe.publish_dict(
                "VENDING_STATE",
                balance_request.model_dump(),
                format=get_qualified_class_name(CheckBalanceRequest),
            )

            # Poll for balance response
            balance_responses = wait_for_message(probe, get_qualified_class_name(CheckBalanceResponse))
            latest_balance = balance_responses[-1].payload

            # Machine cash should be 0 (depleted)
            assert latest_balance["machine_cash"] == 0.0
            # Operator cash should be negative (debt): -($600 - $500 - $10) = -$90
            assert latest_balance["operator_cash"] == -90.0
            # Net worth should reflect the debt
            assert latest_balance["net_worth"] < 0
        finally:
            guild.shutdown()
