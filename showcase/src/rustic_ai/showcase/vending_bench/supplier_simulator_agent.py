"""
SupplierSimulatorAgent - Simulates individual supplier behaviors with adversarial elements.

This agent:
- Handles emails to/from different suppliers
- Implements adversarial pricing and bait-and-switch tactics
- Manages negotiation mechanics
- Generates supply chain events (delays, partial deliveries, bankruptcy)
"""

import logging
import random
from typing import Dict

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.showcase.vending_bench.config import DEFAULT_COSTS, ProductType
from rustic_ai.showcase.vending_bench.messages import (
    DayUpdateEvent,
    Email,
    SimulationTime,
    SupplierDelivery,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.state_keys import (
    CURRENT_DAY,
    SUPPLIER_REGISTRY,
    SUPPLIER_SIMULATION_TIME,
)
from rustic_ai.showcase.vending_bench.supplier_config import (
    BAIT_AND_SWITCH_PROBABILITY,
    DELAY_DURATION_MAX,
    DELAY_DURATION_MIN,
    DELIVERY_DELAY_PROBABILITY,
    DISCOUNT_PER_EXCHANGE,
    MAX_LOYALTY_DISCOUNT,
    MAX_NEGOTIATION_DISCOUNT,
    MAX_NEGOTIATION_EXCHANGES,
    OPERATOR_EMAIL,
    PARTIAL_DELIVERY_FRACTION_MAX,
    PARTIAL_DELIVERY_FRACTION_MIN,
    PARTIAL_DELIVERY_PROBABILITY,
    SUPPLIER_BANKRUPTCY_PROBABILITY,
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
from rustic_ai.showcase.vending_bench.supplier_registry import (
    NegotiationState,
    PendingSupplierOrder,
    SupplierBehaviorType,
    SupplierProfile,
    SupplierRegistry,
)

logger = logging.getLogger(__name__)


class SupplierSimulatorAgentProps(BaseAgentProps):
    """Configuration for SupplierSimulatorAgent."""

    delivery_days_min: int = Field(default=2, description="Minimum delivery days")
    delivery_days_max: int = Field(default=5, description="Maximum delivery days")


class SupplierSimulatorAgent(Agent[SupplierSimulatorAgentProps]):
    """Agent that simulates supplier behaviors with adversarial elements.

    Handles emails to different suppliers, manages negotiations,
    and generates supply chain events.
    """

    def __init__(self):
        self.registry: SupplierRegistry = SupplierRegistry()
        self.current_day: int = 1
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

        # Load registry
        registry_data = guild_state.get(SUPPLIER_REGISTRY)
        if registry_data:
            self.registry = SupplierRegistry(**registry_data) if isinstance(registry_data, dict) else registry_data

        # Load current day
        self.current_day = guild_state.get(CURRENT_DAY, 1)

        # Load simulation time
        sim_time_data = guild_state.get(SUPPLIER_SIMULATION_TIME)
        if sim_time_data:
            self.simulation_time = SimulationTime(**sim_time_data) if isinstance(sim_time_data, dict) else sim_time_data

    def _persist_state(self, ctx: ProcessContext):
        """Persist current state to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                SUPPLIER_REGISTRY: self.registry.model_dump(),
            },
        )

    def _calculate_order_total(
        self, supplier: SupplierProfile, products: Dict[ProductType, int], apply_discounts: bool = True
    ) -> float:
        """Calculate order total based on supplier pricing."""
        total = 0.0
        for product, quantity in products.items():
            if product in supplier.products_offered:
                price = supplier.products_offered[product].current_quoted_price
            else:
                # Fall back to base cost with markup
                price = DEFAULT_COSTS.get(product, 1.0) * 1.3
            total += price * quantity

        # Apply loyalty discount if applicable
        if apply_discounts and supplier.loyalty_discount > 0:
            total *= 1 - supplier.loyalty_discount

        return round(total, 2)

    def _apply_bait_and_switch(
        self, ctx: ProcessContext, order: PendingSupplierOrder, supplier: SupplierProfile
    ) -> float:
        """Apply bait-and-switch pricing for adversarial suppliers."""
        if supplier.behavior_type != SupplierBehaviorType.ADVERSARIAL:
            return order.quoted_total

        if random.random() >= BAIT_AND_SWITCH_PROBABILITY:
            return order.quoted_total

        # Calculate inflated price
        markup = random.uniform(1.15, 1.35)  # 15-35% more than quoted
        actual_total = round(order.quoted_total * markup, 2)

        # Mark the order
        order.bait_and_switch_applied = True
        order.actual_total = actual_total

        # Send bait-and-switch notification
        event = BaitAndSwitchEvent(
            order_id=order.order_id,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.name,
            quoted_total=order.quoted_total,
            actual_total=actual_total,
            difference=actual_total - order.quoted_total,
            reason_given=random.choice(
                [
                    "Market price adjustment",
                    "Supply chain cost increase",
                    "Currency fluctuation",
                    "Updated shipping costs",
                ]
            ),
            day_occurred=self.current_day,
        )
        ctx.send(event)

        logger.warning(
            f"Bait-and-switch: Order {order.order_id} charged ${actual_total:.2f} instead of ${order.quoted_total:.2f}"
        )

        return actual_total

    def _check_delivery_delay(
        self, ctx: ProcessContext, order: PendingSupplierOrder, supplier: SupplierProfile
    ) -> bool:
        """Check if a delivery should be delayed for unreliable suppliers."""
        if supplier.behavior_type != SupplierBehaviorType.UNRELIABLE:
            return False

        if random.random() >= DELIVERY_DELAY_PROBABILITY:
            return False

        # Calculate delay
        delay_days = random.randint(DELAY_DURATION_MIN, DELAY_DURATION_MAX)
        original_day = order.expected_delivery_day
        new_day = original_day + delay_days

        order.is_delayed = True
        order.delay_days = delay_days
        order.expected_delivery_day = new_day

        # Send delay notification
        notification = DeliveryDelayNotification(
            order_id=order.order_id,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.name,
            original_delivery_day=original_day,
            new_delivery_day=new_day,
            delay_days=delay_days,
            reason=random.choice(
                [
                    "Supply chain disruption",
                    "Warehouse inventory issues",
                    "Shipping delays",
                    "Weather-related delays",
                    "High order volume",
                ]
            ),
            day_notified=self.current_day,
        )
        ctx.send(notification)

        logger.info(f"Delivery delayed: Order {order.order_id} delayed by {delay_days} days")
        return True

    def _check_partial_delivery(
        self, ctx: ProcessContext, order: PendingSupplierOrder, supplier: SupplierProfile
    ) -> bool:
        """Check if a delivery should be partial for unreliable suppliers."""
        if supplier.behavior_type != SupplierBehaviorType.UNRELIABLE:
            return False

        if random.random() >= PARTIAL_DELIVERY_PROBABILITY:
            return False

        # Calculate partial fraction
        fraction = random.uniform(PARTIAL_DELIVERY_FRACTION_MIN, PARTIAL_DELIVERY_FRACTION_MAX)
        order.is_partial = True
        order.partial_fraction = fraction

        # Calculate delivered vs missing products
        delivered = {}
        missing = {}
        for product, quantity in order.products.items():
            delivered_qty = int(quantity * fraction)
            missing_qty = quantity - delivered_qty
            if delivered_qty > 0:
                delivered[product] = delivered_qty
            if missing_qty > 0:
                missing[product] = missing_qty

        # Send partial delivery notification
        notification = PartialDeliveryNotification(
            order_id=order.order_id,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.name,
            original_products=order.products,
            delivered_products=delivered,
            missing_products=missing,
            reason=random.choice(
                [
                    "Partial stock availability",
                    "Warehouse shortage",
                    "Supplier allocation limits",
                ]
            ),
            day_notified=self.current_day,
        )
        ctx.send(notification)

        logger.info(f"Partial delivery: Order {order.order_id} - only {fraction:.0%} delivered")
        return True

    def _check_supplier_bankruptcy(self, ctx: ProcessContext, supplier: SupplierProfile) -> bool:
        """Check if an unreliable supplier goes bankrupt."""
        if supplier.behavior_type != SupplierBehaviorType.UNRELIABLE:
            return False

        if random.random() >= SUPPLIER_BANKRUPTCY_PROBABILITY:
            return False

        # Mark supplier as inactive
        supplier.is_active = False
        self.registry.mark_supplier_bankrupt(supplier.supplier_id)

        # Get affected orders
        affected_orders = list(self.registry.get_pending_orders_for_supplier(supplier.supplier_id).keys())

        # Send failure notification
        notification = SupplierFailureNotification(
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.name,
            affected_orders=affected_orders,
            message=f"{supplier.name} has ceased operations. Any pending orders have been cancelled.",
            day_notified=self.current_day,
        )
        ctx.send(notification)

        # Send email notification
        email = Email(
            from_address="notice@business-registry.com",
            to_address=OPERATOR_EMAIL,
            subject=f"URGENT: {supplier.name} - Business Closure Notice",
            body=f"""Dear Valued Customer,

We regret to inform you that {supplier.name} has ceased business operations effective immediately.

Any pending orders with this supplier have been cancelled. We recommend:
1. Finding alternative suppliers for your product needs
2. Reviewing any outstanding payments

Affected order IDs: {', '.join(affected_orders) if affected_orders else 'None'}

We apologize for any inconvenience.

Business Registry Service""",
        )
        ctx.send(email)

        logger.warning(f"Supplier bankruptcy: {supplier.name} has gone out of business")
        return True

    @agent.processor(DayUpdateEvent)
    def handle_day_update(self, ctx: ProcessContext[DayUpdateEvent]):
        """Process daily supply chain events."""
        self._load_state_from_guild()

        event = ctx.payload
        self.current_day = event.day
        self.simulation_time = event.simulation_time

        # Check each pending order for supply chain events
        orders_to_deliver = []
        for order_id, order in list(self.registry.pending_orders.items()):
            if order.is_delivered:
                continue

            supplier = self.registry.suppliers.get(order.supplier_id)
            if not supplier or not supplier.is_active:
                continue

            # Check for delays (only on first check after ordering)
            if not order.is_delayed and order.ordered_on_day == self.current_day - 1:
                self._check_delivery_delay(ctx, order, supplier)

            # Check for partial delivery (only on first check after ordering)
            if not order.is_partial and order.ordered_on_day == self.current_day - 1:
                self._check_partial_delivery(ctx, order, supplier)

            # Check if delivery is due
            if order.expected_delivery_day <= self.current_day:
                orders_to_deliver.append((order_id, order, supplier))

        # Process deliveries
        for order_id, order, supplier in orders_to_deliver:
            self._process_delivery(ctx, order, supplier)

        # Check for supplier bankruptcies (monthly check - roughly every 30 days)
        if self.current_day % 30 == 0:
            for supplier_id, supplier in list(self.registry.suppliers.items()):
                if supplier.is_active:
                    self._check_supplier_bankruptcy(ctx, supplier)

        # Persist state changes
        self._persist_state(ctx)

    def _process_delivery(self, ctx: ProcessContext, order: PendingSupplierOrder, supplier: SupplierProfile):
        """Process a delivery for an order."""
        # Apply bait-and-switch if applicable
        actual_total = self._apply_bait_and_switch(ctx, order, supplier)

        # Calculate actual delivered products
        if order.is_partial:
            delivered_products = {}
            for product, quantity in order.products.items():
                delivered_qty = int(quantity * order.partial_fraction)
                if delivered_qty > 0:
                    delivered_products[product] = delivered_qty
        else:
            delivered_products = order.products

        # Mark order as delivered
        order.is_delivered = True
        order.actual_total = actual_total

        # Update supplier stats
        supplier.orders_completed += 1
        if supplier.loyalty_discount < MAX_LOYALTY_DISCOUNT:
            supplier.loyalty_discount = min(MAX_LOYALTY_DISCOUNT, supplier.loyalty_discount + 0.01)

        # Create delivery
        delivery = SupplierDelivery(
            order_id=order.order_id,
            products=delivered_products,
            delivery_day=self.current_day,
        )
        ctx.send(delivery)

        # Send delivery notification email
        items_text = ", ".join(f"{qty} {p.value}" for p, qty in delivered_products.items())

        body = f"""Your order has been delivered!

Order ID: {order.order_id}
Supplier: {supplier.name}
Items: {items_text}
"""
        if order.bait_and_switch_applied:
            body += f"""
Note: Due to {order.actual_total - order.quoted_total:.2f} in additional charges,
your final total was ${order.actual_total:.2f} (originally quoted ${order.quoted_total:.2f}).
"""
        if order.is_partial:
            body += """
Note: This was a partial delivery. Some items were unavailable.
"""

        body += (
            """
Please restock your vending machine at your earliest convenience.

Best regards,
"""
            + supplier.name
        )

        delivery_email = Email(
            from_address=supplier.email,
            to_address=OPERATOR_EMAIL,
            subject=f"Delivery Arrived - Order {order.order_id}",
            body=body,
        )
        ctx.send(delivery_email)

        logger.info(f"Delivery processed: Order {order.order_id} from {supplier.name}")

    @agent.processor(StartNegotiationRequest)
    def handle_start_negotiation(self, ctx: ProcessContext[StartNegotiationRequest]):
        """Handle request to start price negotiation."""
        self._load_state_from_guild()

        request = ctx.payload
        supplier = self.registry.suppliers.get(request.supplier_id)

        if not supplier or not supplier.is_active:
            response = NegotiationResponse(
                request_id=request.request_id,
                negotiation_id="",
                supplier_response="Supplier not found or no longer in business.",
                current_offer=0,
                discount_achieved=0,
                exchanges_remaining=0,
                is_rejected=True,
            )
            ctx.send(response)
            return

        # Calculate initial offer
        if request.product_type and request.product_type in supplier.products_offered:
            initial_price = supplier.products_offered[request.product_type].current_quoted_price
        else:
            # Use average price
            prices = [p.current_quoted_price for p in supplier.products_offered.values()]
            initial_price = sum(prices) / len(prices) if prices else 1.0

        # Create negotiation state
        negotiation = NegotiationState(
            supplier_id=supplier.supplier_id,
            product_type=request.product_type,
            initial_quote=initial_price,
            current_quote=initial_price,
            started_on_day=self.current_day,
        )
        self.registry.negotiations[negotiation.negotiation_id] = negotiation

        # Generate initial response
        if supplier.behavior_type == SupplierBehaviorType.ADVERSARIAL:
            response_text = (
                f"Our price of ${initial_price:.2f} is already very competitive. What were you looking to pay?"
            )
        else:
            response_text = f"We're currently offering ${initial_price:.2f}. We may have some flexibility for valued customers. What's your counter-offer?"

        self._persist_state(ctx)

        response = NegotiationResponse(
            request_id=request.request_id,
            negotiation_id=negotiation.negotiation_id,
            supplier_response=response_text,
            current_offer=initial_price,
            discount_achieved=0,
            exchanges_remaining=MAX_NEGOTIATION_EXCHANGES,
            is_accepted=False,
            is_rejected=False,
        )
        ctx.send(response)

    @agent.processor(NegotiationExchangeRequest)
    def handle_negotiation_exchange(self, ctx: ProcessContext[NegotiationExchangeRequest]):
        """Handle negotiation exchange."""
        self._load_state_from_guild()

        request = ctx.payload
        negotiation = self.registry.negotiations.get(request.negotiation_id)

        if not negotiation or not negotiation.is_active:
            response = NegotiationResponse(
                request_id=request.request_id,
                negotiation_id=request.negotiation_id,
                supplier_response="This negotiation has ended.",
                current_offer=0,
                discount_achieved=0,
                exchanges_remaining=0,
                is_rejected=True,
            )
            ctx.send(response)
            return

        supplier = self.registry.suppliers.get(negotiation.supplier_id)
        if not supplier:
            return

        negotiation.exchange_count += 1
        negotiation.last_exchange_content = request.message

        # Check if max exchanges reached
        exchanges_remaining = MAX_NEGOTIATION_EXCHANGES - negotiation.exchange_count
        if exchanges_remaining <= 0:
            negotiation.is_active = False
            response = NegotiationResponse(
                request_id=request.request_id,
                negotiation_id=negotiation.negotiation_id,
                supplier_response="I'm sorry, but this is our final offer. Take it or leave it.",
                current_offer=negotiation.current_quote,
                discount_achieved=(negotiation.initial_quote - negotiation.current_quote) / negotiation.initial_quote,
                exchanges_remaining=0,
                is_rejected=True,
            )
            ctx.send(response)
            self._persist_state(ctx)
            return

        # Calculate new discount based on exchanges and supplier flexibility
        base_discount = negotiation.exchange_count * DISCOUNT_PER_EXCHANGE
        max_discount = min(supplier.negotiation_flexibility + supplier.loyalty_discount, MAX_NEGOTIATION_DISCOUNT)
        achieved_discount = min(base_discount, max_discount)

        # Adversarial suppliers are less flexible
        if supplier.behavior_type == SupplierBehaviorType.ADVERSARIAL:
            achieved_discount *= 0.5

        new_price = negotiation.initial_quote * (1 - achieved_discount)
        negotiation.current_quote = round(new_price, 2)

        # Check if they accept a counter-offer
        is_accepted = False
        if request.offer_price:
            # Check if offer is acceptable
            min_acceptable = negotiation.initial_quote * (1 - max_discount)
            if request.offer_price >= min_acceptable:
                is_accepted = True
                negotiation.current_quote = request.offer_price
                negotiation.is_active = False

        # Generate response
        if is_accepted:
            response_text = f"We have a deal! ${negotiation.current_quote:.2f} is acceptable."
        elif supplier.behavior_type == SupplierBehaviorType.ADVERSARIAL:
            response_text = f"The best I can do is ${negotiation.current_quote:.2f}. Our margins are very tight."
        else:
            response_text = f"I can offer ${negotiation.current_quote:.2f}. That's a {achieved_discount:.0%} discount."

        self._persist_state(ctx)

        response = NegotiationResponse(
            request_id=request.request_id,
            negotiation_id=negotiation.negotiation_id,
            supplier_response=response_text,
            current_offer=negotiation.current_quote,
            discount_achieved=achieved_discount,
            exchanges_remaining=exchanges_remaining,
            is_accepted=is_accepted,
            is_rejected=False,
        )
        ctx.send(response)
