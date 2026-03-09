"""
VendingMachineAgent - Manages the vending machine state.

This agent handles:
- Inventory management
- Cash collection
- Price adjustments
- Processing customer purchases
- Daily fee deductions
"""

import logging
from typing import Dict, Optional

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.showcase.vending_bench.config import (
    DAILY_FEE,
    DEFAULT_COSTS,
    DEFAULT_PRICES,
    DEFAULT_STOCK,
    MAX_INVENTORY_PER_PRODUCT,
    STARTING_CAPITAL,
    TIME_COSTS,
    ProductType,
)
from rustic_ai.showcase.vending_bench.economics import (
    calculate_inventory_value,
    calculate_net_worth,
)
from rustic_ai.showcase.vending_bench.messages import (
    CheckBalanceRequest,
    CheckBalanceResponse,
    CheckInventoryRequest,
    CheckInventoryResponse,
    CollectCashRequest,
    CollectCashResponse,
    CustomerPurchaseEvent,
    DayUpdateEvent,
    RestockRequest,
    RestockResponse,
    SetPriceRequest,
    SetPriceResponse,
    SimulationTime,
    SupplierDelivery,
    VendingMachineState,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.state_keys import (
    MACHINE_CASH,
    OPERATOR_CASH,
    VM_INVENTORY,
    VM_PENDING_DELIVERIES,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    BaitAndSwitchEvent,
    ComplaintResolution,
    PartialDeliveryNotification,
)

logger = logging.getLogger(__name__)


class VendingMachineAgentProps(BaseAgentProps):
    """Configuration properties for VendingMachineAgent."""

    starting_capital: float = Field(default=STARTING_CAPITAL)
    daily_fee: float = Field(default=DAILY_FEE)
    initial_prices: Optional[Dict[str, float]] = Field(default=None)
    initial_stock: Optional[Dict[str, int]] = Field(default=None)


class VendingMachineAgent(Agent[VendingMachineAgentProps]):
    """Agent managing the vending machine state.

    Maintains inventory, cash, and prices. Processes customer purchases
    and handles daily fee deductions.
    """

    def __init__(self):
        # Initialize inventory with defaults or config
        self.inventory: Dict[ProductType, int] = {}
        self.prices: Dict[ProductType, float] = {}

        for product in ProductType:
            if self.config.initial_stock:
                self.inventory[product] = self.config.initial_stock.get(product.value, DEFAULT_STOCK[product])
            else:
                self.inventory[product] = DEFAULT_STOCK[product]

            if self.config.initial_prices:
                self.prices[product] = self.config.initial_prices.get(product.value, DEFAULT_PRICES[product])
            else:
                self.prices[product] = DEFAULT_PRICES[product]

        # Cash state
        self.machine_cash: float = 0.0
        self.operator_cash: float = self.config.starting_capital

        # Track statistics
        self.total_sales: int = 0
        self.total_revenue: float = 0.0
        self.current_day: int = 1

        # Pending deliveries that have arrived but not yet restocked
        self.pending_deliveries: Dict[str, SupplierDelivery] = {}

        # Current simulation time (updated by simulation controller)
        self.simulation_time: SimulationTime = SimulationTime(
            current_day=1,
            current_time_minutes=0,
            is_daytime=True,
            weather=WeatherType.SUNNY,
            day_of_week=0,
        )

    def _load_state_from_guild(self):
        """Load persisted state from guild state."""
        guild_state = self.get_guild_state() or {}

        # Load pending deliveries
        deliveries_data = guild_state.get(VM_PENDING_DELIVERIES, {})
        self.pending_deliveries = {
            k: SupplierDelivery(**v) if isinstance(v, dict) else v for k, v in deliveries_data.items()
        }

    def _persist_pending_deliveries(self, ctx: ProcessContext):
        """Persist pending deliveries to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                VM_PENDING_DELIVERIES: {k: v.model_dump() for k, v in self.pending_deliveries.items()},
            },
        )

    def _persist_inventory_to_guild(self, ctx: ProcessContext):
        """Persist inventory to guild state so other agents can read it."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                VM_INVENTORY: {p.value: q for p, q in self.inventory.items()},
            },
        )

    def get_state(self) -> VendingMachineState:
        """Get the current vending machine state."""
        return VendingMachineState(
            inventory={p: q for p, q in self.inventory.items()},
            machine_cash=self.machine_cash,
            operator_cash=self.operator_cash,
            prices={p: pr for p, pr in self.prices.items()},
            day=self.current_day,
            total_sales=self.total_sales,
            total_revenue=self.total_revenue,
        )

    def _update_simulation_time(self, new_time: SimulationTime):
        """Update the current simulation time."""
        self.simulation_time = new_time
        self.current_day = new_time.current_day

    @agent.processor(CheckInventoryRequest)
    def handle_check_inventory(self, ctx: ProcessContext[CheckInventoryRequest]):
        """Handle inventory check request."""
        request = ctx.payload

        response = CheckInventoryResponse(
            request_id=request.request_id,
            inventory={p: q for p, q in self.inventory.items()},
            time_elapsed_minutes=TIME_COSTS["check_inventory"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.debug(f"Inventory check: {self.inventory}")

    @agent.processor(CheckBalanceRequest)
    def handle_check_balance(self, ctx: ProcessContext[CheckBalanceRequest]):
        """Handle balance check request."""
        request = ctx.payload

        inventory_value = calculate_inventory_value(self.inventory, DEFAULT_COSTS)
        net_worth = calculate_net_worth(self.machine_cash, self.operator_cash, self.inventory, DEFAULT_COSTS)

        response = CheckBalanceResponse(
            request_id=request.request_id,
            machine_cash=self.machine_cash,
            operator_cash=self.operator_cash,
            inventory_value=inventory_value,
            net_worth=net_worth,
            time_elapsed_minutes=TIME_COSTS["check_balance"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.debug(f"Balance check: machine={self.machine_cash}, operator={self.operator_cash}, nw={net_worth}")

    @agent.processor(SetPriceRequest)
    def handle_set_price(self, ctx: ProcessContext[SetPriceRequest]):
        """Handle price change request."""
        request = ctx.payload

        old_price = self.prices.get(request.product, DEFAULT_PRICES[request.product])
        self.prices[request.product] = request.new_price

        # Persist state change
        self.update_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={"prices": {p.value: pr for p, pr in self.prices.items()}},
        )

        response = SetPriceResponse(
            request_id=request.request_id,
            product=request.product,
            old_price=old_price,
            new_price=request.new_price,
            success=True,
            message=f"Price for {request.product.value} changed from ${old_price:.2f} to ${request.new_price:.2f}",
            time_elapsed_minutes=TIME_COSTS["set_price"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.info(f"Price changed: {request.product.value} ${old_price:.2f} -> ${request.new_price:.2f}")

    @agent.processor(CollectCashRequest)
    def handle_collect_cash(self, ctx: ProcessContext[CollectCashRequest]):
        """Handle cash collection request."""
        request = ctx.payload

        amount_collected = self.machine_cash
        self.operator_cash += amount_collected
        self.machine_cash = 0.0

        # Persist state change to guild state so all agents see consistent balances
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={MACHINE_CASH: self.machine_cash, OPERATOR_CASH: self.operator_cash},
        )

        response = CollectCashResponse(
            request_id=request.request_id,
            amount_collected=amount_collected,
            new_machine_balance=self.machine_cash,
            new_operator_balance=self.operator_cash,
            time_elapsed_minutes=TIME_COSTS["collect_cash"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.info(f"Collected ${amount_collected:.2f} from machine")

    @agent.processor(SupplierDelivery)
    def handle_delivery(self, ctx: ProcessContext[SupplierDelivery]):
        """Handle a supplier delivery arrival."""
        # Load state from guild state
        self._load_state_from_guild()

        delivery = ctx.payload

        # Store delivery for later restocking - key by order_id since that's what
        # the operator sees in delivery emails and uses to restock
        self.pending_deliveries[delivery.order_id] = delivery

        # Persist the pending deliveries
        self._persist_pending_deliveries(ctx)

        logger.info(f"Delivery for order {delivery.order_id} arrived with {delivery.products}")

    @agent.processor(RestockRequest)
    def handle_restock(self, ctx: ProcessContext[RestockRequest]):
        """Handle restock request from a pending delivery."""
        # Load state from guild state
        self._load_state_from_guild()

        request = ctx.payload

        # The delivery_id parameter is actually the order_id from the delivery email
        # (e.g., "ORD-ABC123") since that's what the operator sees and uses
        order_id = request.delivery_id

        if order_id not in self.pending_deliveries:
            response = RestockResponse(
                request_id=request.request_id,
                delivery_id=order_id,
                products_restocked={},
                success=False,
                message=f"Order {order_id} not found or already restocked",
                time_elapsed_minutes=TIME_COSTS["restock"],
                simulation_time=self.simulation_time,
            )
            ctx.send(response)
            return

        delivery = self.pending_deliveries.pop(order_id)
        products_restocked: Dict[ProductType, int] = {}

        for product, quantity in delivery.products.items():
            current = self.inventory.get(product, 0)
            # Cap at max inventory
            can_add = min(quantity, MAX_INVENTORY_PER_PRODUCT - current)
            self.inventory[product] = current + can_add
            products_restocked[product] = can_add

        # Persist state change (inventory) to agent state
        self.update_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={"inventory": {p.value: q for p, q in self.inventory.items()}},
        )

        # Persist inventory to guild state so other agents can track it
        self._persist_inventory_to_guild(ctx)

        # Persist pending deliveries (after removing the restocked one)
        self._persist_pending_deliveries(ctx)

        response = RestockResponse(
            request_id=request.request_id,
            delivery_id=order_id,
            products_restocked=products_restocked,
            success=True,
            message=f"Restocked {sum(products_restocked.values())} items from order {order_id}",
            time_elapsed_minutes=TIME_COSTS["restock"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.info(f"Restocked from order {order_id}: {products_restocked}")

    @agent.processor(CustomerPurchaseEvent)
    def handle_purchase(self, ctx: ProcessContext[CustomerPurchaseEvent]):
        """Process a customer purchase."""
        purchase = ctx.payload

        product = purchase.product
        quantity = purchase.quantity

        # Check inventory
        available = self.inventory.get(product, 0)
        actual_quantity = min(quantity, available)

        if actual_quantity > 0:
            # Process the sale
            self.inventory[product] = available - actual_quantity
            revenue = actual_quantity * self.prices.get(product, DEFAULT_PRICES[product])
            self.machine_cash += revenue
            self.total_sales += actual_quantity
            self.total_revenue += revenue

            # Persist inventory and machine cash to guild state so other agents can track it
            self._persist_inventory_to_guild(ctx)
            self.update_guild_state(
                ctx,
                update_format=StateUpdateFormat.JSON_MERGE_PATCH,
                update={MACHINE_CASH: self.machine_cash},
            )

            logger.debug(f"Sale: {actual_quantity}x {product.value} @ ${self.prices[product]:.2f} = ${revenue:.2f}")

    @agent.processor(DayUpdateEvent)
    def handle_day_update(self, ctx: ProcessContext[DayUpdateEvent]):
        """Handle day change - update time and deduct daily fee."""
        event = ctx.payload

        self._update_simulation_time(event.simulation_time)

        # Persist inventory to guild state at start of each day
        # This ensures other agents have access to current inventory
        self._persist_inventory_to_guild(ctx)

        # Daily fee is already deducted by simulation controller before this event
        # Just log the update
        logger.info(
            f"Day {event.day} started. Weather: {event.weather.value}. Remaining cash: ${event.remaining_cash:.2f}"
        )

    @agent.processor(BaitAndSwitchEvent)
    def handle_bait_and_switch(self, ctx: ProcessContext[BaitAndSwitchEvent]):
        """Handle bait-and-switch pricing from adversarial suppliers.

        Deducts the extra amount charged from operator cash.
        """
        event = ctx.payload
        extra_charge = event.difference

        if self.operator_cash >= extra_charge:
            self.operator_cash -= extra_charge
            logger.warning(
                f"Bait-and-switch: Charged extra ${extra_charge:.2f} for order {event.order_id}. "
                f"New operator cash: ${self.operator_cash:.2f}"
            )
        else:
            # Use machine cash if operator cash insufficient
            remaining = extra_charge - self.operator_cash
            self.operator_cash = 0.0
            if self.machine_cash >= remaining:
                self.machine_cash -= remaining
            else:
                # Not enough cash - go into debt (negative balance)
                self.operator_cash = -(remaining - self.machine_cash)
                self.machine_cash = 0.0
            logger.warning(
                f"Bait-and-switch: Insufficient funds for extra ${extra_charge:.2f}. "
                f"Operator cash now: ${self.operator_cash:.2f}"
            )

        # Persist state change to guild state so all agents see consistent balances
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={OPERATOR_CASH: self.operator_cash, MACHINE_CASH: self.machine_cash},
        )

    @agent.processor(PartialDeliveryNotification)
    def handle_partial_delivery(self, ctx: ProcessContext[PartialDeliveryNotification]):
        """Handle notification of partial delivery.

        Log the event - actual inventory update happens via SupplierDelivery.
        """
        notification = ctx.payload
        missing_items = ", ".join(f"{qty} {p.value}" for p, qty in notification.missing_products.items())
        logger.warning(f"Partial delivery for order {notification.order_id}: Missing items - {missing_items}")

    @agent.processor(ComplaintResolution)
    def handle_complaint_resolution(self, ctx: ProcessContext[ComplaintResolution]):
        """Handle complaint resolution - refund is processed by CustomerComplaintAgent.

        This is mainly for logging and tracking.
        """
        resolution = ctx.payload
        logger.info(
            f"Complaint {resolution.complaint_id} resolved: {resolution.resolution_type}, "
            f"refund=${resolution.refund_amount:.2f}"
        )
