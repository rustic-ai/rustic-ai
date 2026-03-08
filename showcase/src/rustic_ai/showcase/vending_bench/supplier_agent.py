"""
SupplierAgent - Handles email-based ordering and deliveries.

This agent:
- Processes email orders from the vending machine operator
- Uses AI to generate realistic supplier responses
- Manages delivery schedules
- Provides scratchpad memory for agent notes
- Integrates with multi-supplier registry for realistic dynamics
"""

import logging
import random
import re
from typing import Dict, List, Optional

from pydantic import Field
import shortuuid

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.showcase.vending_bench.config import (
    DEFAULT_COSTS,
    SUPPLIER_DELIVERY_DAYS_MAX,
    SUPPLIER_DELIVERY_DAYS_MIN,
    TIME_COSTS,
    ProductType,
)
from rustic_ai.showcase.vending_bench.messages import (
    DayUpdateEvent,
    DeliverySchedule,
    Email,
    ReadEmailsRequest,
    ReadEmailsResponse,
    ScratchpadReadRequest,
    ScratchpadReadResponse,
    ScratchpadWriteRequest,
    ScratchpadWriteResponse,
    SendEmailRequest,
    SendEmailResponse,
    SimulationTime,
    SupplierDelivery,
    SupplierOrderConfirmation,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.state_keys import (
    SCRATCHPAD,
    SUPPLIER_CURRENT_DAY,
    SUPPLIER_INBOX,
    SUPPLIER_PENDING_ORDERS,
    SUPPLIER_REGISTRY,
    SUPPLIER_SENT_EMAILS,
    SUPPLIER_SIMULATION_TIME,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    ViewSuppliersRequest,
    ViewSuppliersResponse,
)
from rustic_ai.showcase.vending_bench.supplier_registry import (
    SupplierProfile,
    SupplierRegistry,
)

logger = logging.getLogger(__name__)


OPERATOR_EMAIL = "operator@vendingbiz.com"

SUPPLIER_SYSTEM_PROMPT = """You are a friendly and professional customer service representative for VendingSupply Co.
You respond to emails from vending machine operators regarding product orders.

Available products and wholesale prices:
- Chips: $0.75/unit
- Candy: $0.60/unit
- Soda: $0.80/unit
- Water: $0.50/unit
- Energy Drink: $1.50/unit

When processing orders:
1. Confirm the products and quantities requested
2. Calculate the total cost
3. Mention delivery will take 2-5 business days
4. Be helpful and professional

If the email is unclear or missing information (like specific products or quantities), politely ask for clarification.
If someone asks about products, provide the product catalog with prices.
Keep responses concise and business-like."""


class SupplierAgentProps(BaseAgentProps):
    """Configuration properties for SupplierAgent."""

    delivery_days_min: int = Field(default=SUPPLIER_DELIVERY_DAYS_MIN)
    delivery_days_max: int = Field(default=SUPPLIER_DELIVERY_DAYS_MAX)
    use_ai_responses: bool = Field(default=True, description="Use LLM for supplier responses")


class SupplierAgent(Agent[SupplierAgentProps]):
    """Agent that simulates a product supplier.

    Handles email-based ordering with natural language processing,
    manages delivery schedules, and provides scratchpad memory.
    Integrates with multi-supplier registry for realistic dynamics.
    """

    def __init__(self):
        # Email inbox for the operator
        self.inbox: List[Email] = []
        self.sent_emails: List[Email] = []

        # Pending orders and deliveries
        self.pending_orders: Dict[str, DeliverySchedule] = {}

        # Scratchpad memory (key-value store)
        self.scratchpad: Dict[str, str] = {}

        # Current simulation time
        self.current_day: int = 1
        self.simulation_time: SimulationTime = SimulationTime(
            current_day=1,
            current_time_minutes=0,
            is_daytime=True,
            weather=WeatherType.SUNNY,
            day_of_week=0,
        )

        # Multi-supplier registry (starts empty - agent must search for suppliers)
        self.registry: SupplierRegistry = SupplierRegistry()

    def _load_state_from_guild(self):
        """Load persisted state from guild state."""
        guild_state = self.get_guild_state() or {}

        # Load inbox
        inbox_data = guild_state.get(SUPPLIER_INBOX, [])
        self.inbox = [Email(**e) if isinstance(e, dict) else e for e in inbox_data]

        # Load sent emails
        sent_data = guild_state.get(SUPPLIER_SENT_EMAILS, [])
        self.sent_emails = [Email(**e) if isinstance(e, dict) else e for e in sent_data]

        # Load pending orders
        orders_data = guild_state.get(SUPPLIER_PENDING_ORDERS, {})
        self.pending_orders = {k: DeliverySchedule(**v) if isinstance(v, dict) else v for k, v in orders_data.items()}

        # Load scratchpad
        self.scratchpad = guild_state.get(SCRATCHPAD, {})

        # Load current day
        self.current_day = guild_state.get(SUPPLIER_CURRENT_DAY, 1)

        # Load simulation time
        sim_time_data = guild_state.get(SUPPLIER_SIMULATION_TIME)
        if sim_time_data:
            self.simulation_time = SimulationTime(**sim_time_data) if isinstance(sim_time_data, dict) else sim_time_data

        # Load supplier registry
        registry_data = guild_state.get(SUPPLIER_REGISTRY)
        if registry_data:
            self.registry = SupplierRegistry(**registry_data) if isinstance(registry_data, dict) else registry_data

    def _persist_state(self, ctx: ProcessContext):
        """Persist current state to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                SUPPLIER_INBOX: [e.model_dump() for e in self.inbox],
                SUPPLIER_SENT_EMAILS: [e.model_dump() for e in self.sent_emails],
                SUPPLIER_PENDING_ORDERS: {k: v.model_dump() for k, v in self.pending_orders.items()},
                SCRATCHPAD: self.scratchpad,
                SUPPLIER_CURRENT_DAY: self.current_day,
                SUPPLIER_SIMULATION_TIME: self.simulation_time.model_dump(),
                SUPPLIER_REGISTRY: self.registry.model_dump(),
            },
        )

    def _get_supplier_by_email(self, email_address: str) -> Optional[SupplierProfile]:
        """Find a supplier by email address."""
        return self.registry.get_supplier_by_email(email_address)

    def _parse_order_from_email(self, body: str) -> Optional[Dict[ProductType, int]]:
        """Parse order quantities from email body using simple pattern matching.

        Args:
            body: Email body text

        Returns:
            Dictionary of product -> quantity, or None if parsing fails
        """
        order = {}
        body_lower = body.lower()

        # Look for patterns like "20 chips", "10 units of soda", "candy: 15"
        patterns = [
            r"(\d+)\s*(?:units?\s+(?:of\s+)?)?(\w+)",
            r"(\w+):\s*(\d+)",
            r"(\w+)\s*-\s*(\d+)",
        ]

        # Map of keywords to product types
        product_keywords = {
            "chips": ProductType.CHIPS,
            "chip": ProductType.CHIPS,
            "candy": ProductType.CANDY,
            "candies": ProductType.CANDY,
            "soda": ProductType.SODA,
            "sodas": ProductType.SODA,
            "water": ProductType.WATER,
            "waters": ProductType.WATER,
            "energy": ProductType.ENERGY_DRINK,
            "energy_drink": ProductType.ENERGY_DRINK,
            "energy drink": ProductType.ENERGY_DRINK,
            "energydrink": ProductType.ENERGY_DRINK,
        }

        for pattern in patterns:
            matches = re.findall(pattern, body_lower)
            for match in matches:
                if pattern.startswith(r"(\w+)"):
                    # Pattern: "product: quantity" or "product - quantity"
                    keyword, qty_str = match
                else:
                    # Pattern: "quantity product"
                    qty_str, keyword = match

                try:
                    quantity = int(qty_str)
                except ValueError:
                    continue

                # Match keyword to product
                for key, product in product_keywords.items():
                    if key in keyword:
                        order[product] = order.get(product, 0) + quantity
                        break

        return order if order else None

    def _calculate_order_cost(self, products: Dict[ProductType, int]) -> float:
        """Calculate total cost for an order."""
        total = 0.0
        for product, quantity in products.items():
            cost = DEFAULT_COSTS.get(product, 1.0)
            total += cost * quantity
        return total

    def _generate_delivery_day(self) -> int:
        """Generate a random delivery day within the configured range."""
        delay = random.randint(self.config.delivery_days_min, self.config.delivery_days_max)
        return self.current_day + delay

    def _create_order_confirmation_email(
        self,
        order: Dict[ProductType, int],
        order_id: str,
        delivery_day: int,
        total_cost: float,
        supplier: SupplierProfile,
    ) -> Email:
        """Create an order confirmation email."""
        items_text = "\n".join(
            f"  - {product.value.replace('_', ' ').title()}: {qty} units "
            f"@ ${DEFAULT_COSTS[product]:.2f} = ${qty * DEFAULT_COSTS[product]:.2f}"
            for product, qty in order.items()
        )

        body = f"""Thank you for your order!

Order ID: {order_id}

Items:
{items_text}

Total: ${total_cost:.2f}

Expected delivery: Day {delivery_day}

Your order will be delivered to your vending machine location.
Please ensure someone is available to receive and restock the products.

Best regards,
{supplier.name}"""

        return Email(
            from_address=supplier.email,
            to_address=OPERATOR_EMAIL,
            subject=f"Order Confirmation - {order_id}",
            body=body,
        )

    def _create_clarification_email(self, original_subject: str, supplier: SupplierProfile) -> Email:
        """Create an email asking for order clarification."""
        body = f"""Thank you for contacting {supplier.name}.

We'd be happy to help you with your order, but we need a bit more information.

Please specify:
- Which products you'd like to order
- The quantity for each product

Our available products:
- Chips: $0.75/unit
- Candy: $0.60/unit
- Soda: $0.80/unit
- Water: $0.50/unit
- Energy Drink: $1.50/unit

Example order format:
"I'd like to order 20 chips, 15 candy, and 25 soda"

Best regards,
{supplier.name}"""

        return Email(
            from_address=supplier.email,
            to_address=OPERATOR_EMAIL,
            subject=f"Re: {original_subject} - Please Clarify Order",
            body=body,
        )

    def _create_product_catalog_email(self, supplier: SupplierProfile) -> Email:
        """Create an email with the product catalog."""
        body = f"""Here is our complete product catalog:

SNACKS:
- Chips: $0.75/unit (minimum order: 10)
- Candy: $0.60/unit (minimum order: 10)

BEVERAGES:
- Soda: $0.80/unit (minimum order: 10)
- Water: $0.50/unit (minimum order: 10)
- Energy Drink: $1.50/unit (minimum order: 5)

ORDERING:
Simply reply to this email with your order. Example:
"20 chips, 15 candy, 30 soda, 30 water, 10 energy drinks"

DELIVERY:
Orders are typically delivered within 2-5 business days.

Let us know if you have any questions!

Best regards,
{supplier.name}"""

        return Email(
            from_address=supplier.email,
            to_address=OPERATOR_EMAIL,
            subject=f"{supplier.name} - Product Catalog",
            body=body,
        )

    @agent.processor(ReadEmailsRequest)
    def handle_read_emails(self, ctx: ProcessContext[ReadEmailsRequest]):
        """Handle request to read emails."""
        # Load state from guild state
        self._load_state_from_guild()

        request = ctx.payload

        if request.unread_only:
            emails = [e for e in self.inbox if not e.is_read]
        else:
            emails = list(self.inbox)

        # Mark as read
        for email in emails:
            email.is_read = True

        # Persist updated read status
        self._persist_state(ctx)

        response = ReadEmailsResponse(
            request_id=request.request_id,
            emails=emails,
            time_elapsed_minutes=TIME_COSTS["read_emails"],
            simulation_time=self.simulation_time,
        )

        ctx.send(response)
        logger.debug(f"Read {len(emails)} emails")

    @agent.processor(SendEmailRequest, depends_on=[AgentDependency(dependency_key="llm", guild_level=True)])
    def handle_send_email_with_llm(self, ctx: ProcessContext[SendEmailRequest], llm: LLM):
        """Handle email sending with LLM-generated responses."""
        # Load state from guild state
        self._load_state_from_guild()

        request = ctx.payload

        # Validate that the email address is a known supplier
        supplier = self._get_supplier_by_email(request.to_address)

        if supplier is None:
            # Check if they're trying to send to a supplier-like address without searching first
            if "supplier" in request.to_address.lower() or "@vend" in request.to_address.lower():
                # Persist state (no changes, just maintaining consistency)
                self._persist_state(ctx)

                # Return error - must search for suppliers first
                response = SendEmailResponse(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        f"Unknown supplier email address: {request.to_address}. "
                        "You must first use 'search_suppliers' to discover suppliers, then "
                        "use 'view_suppliers' to see known supplier email addresses before ordering."
                    ),
                    time_elapsed_minutes=TIME_COSTS["send_email"],
                    simulation_time=self.simulation_time,
                )
                ctx.send(response)
                logger.warning(f"Rejected email to unknown supplier: {request.to_address}")
                return

            # Not a supplier email - just a generic email send
            sent_email = Email(
                from_address=OPERATOR_EMAIL,
                to_address=request.to_address,
                subject=request.subject,
                body=request.body,
            )
            self.sent_emails.append(sent_email)
            self._persist_state(ctx)

            response = SendEmailResponse(
                request_id=request.request_id,
                success=True,
                message="Email sent successfully",
                time_elapsed_minutes=TIME_COSTS["send_email"],
                simulation_time=self.simulation_time,
            )
            ctx.send(response)
            return

        # Valid supplier email - record and process
        sent_email = Email(
            from_address=OPERATOR_EMAIL,
            to_address=request.to_address,
            subject=request.subject,
            body=request.body,
        )
        self.sent_emails.append(sent_email)

        # Process the supplier email
        self._process_supplier_email(ctx, request, llm, supplier)

    def _process_supplier_email(
        self, ctx: ProcessContext[SendEmailRequest], request: SendEmailRequest, llm: LLM, supplier: SupplierProfile
    ):
        """Process an email sent to a known supplier."""
        body_lower = request.body.lower()

        # Check if this looks like an order
        order = self._parse_order_from_email(request.body)

        if order:
            # Process the order
            order_id = f"ORD-{shortuuid.uuid()[:8].upper()}"
            total_cost = self._calculate_order_cost(order)
            delivery_day = self._generate_delivery_day()

            # Schedule the delivery
            self.pending_orders[order_id] = DeliverySchedule(
                order_id=order_id,
                products=order,
                expected_delivery_day=delivery_day,
                ordered_on_day=self.current_day,
                supplier_id=supplier.supplier_id,
                supplier_email=supplier.email,
                supplier_name=supplier.name,
            )

            # Create confirmation email
            confirmation_email = self._create_order_confirmation_email(
                order, order_id, delivery_day, total_cost, supplier
            )
            self.inbox.append(confirmation_email)

            # Send order confirmation message
            confirmation = SupplierOrderConfirmation(
                order_id=order_id,
                products=order,
                total_cost=total_cost,
                expected_delivery_day=delivery_day,
                confirmation_message=f"Order {order_id} confirmed. Delivery on day {delivery_day}.",
            )
            ctx.send(confirmation)

            logger.info(
                f"Order {order_id} placed with {supplier.name}: {order}, total=${total_cost:.2f}, delivery day {delivery_day}"
            )

        elif "catalog" in body_lower or "products" in body_lower or "prices" in body_lower:
            # Send product catalog
            catalog_email = self._create_product_catalog_email(supplier)
            self.inbox.append(catalog_email)

        else:
            # Use LLM for response if enabled, otherwise send clarification
            if self.config.use_ai_responses and llm:
                try:
                    completion_request = ChatCompletionRequest(
                        messages=[
                            SystemMessage(content=SUPPLIER_SYSTEM_PROMPT),
                            UserMessage(content=f"Subject: {request.subject}\n\n{request.body}"),
                        ],
                    )
                    response = llm.completion(completion_request)
                    if response.choices and response.choices[0].message:
                        ai_response = response.choices[0].message.content
                        reply_email = Email(
                            from_address=supplier.email,
                            to_address=OPERATOR_EMAIL,
                            subject=f"Re: {request.subject}",
                            body=ai_response,
                        )
                        self.inbox.append(reply_email)
                except Exception as e:
                    logger.warning(f"LLM response failed: {e}, using default clarification")
                    clarification_email = self._create_clarification_email(request.subject, supplier)
                    self.inbox.append(clarification_email)
            else:
                clarification_email = self._create_clarification_email(request.subject, supplier)
                self.inbox.append(clarification_email)

        # Persist state changes (inbox, pending_orders, etc.)
        self._persist_state(ctx)

        # Send response
        response = SendEmailResponse(
            request_id=request.request_id,
            success=True,
            message="Email sent to supplier",
            time_elapsed_minutes=TIME_COSTS["send_email"],
            simulation_time=self.simulation_time,
        )
        ctx.send(response)

    @agent.processor(DayUpdateEvent)
    def handle_day_update(self, ctx: ProcessContext[DayUpdateEvent]):
        """Process deliveries on day change."""
        # Load state from guild state
        self._load_state_from_guild()

        event = ctx.payload
        self.current_day = event.day
        self.simulation_time = event.simulation_time

        # Check for deliveries due today
        deliveries_today = [
            order for order_id, order in self.pending_orders.items() if order.expected_delivery_day <= self.current_day
        ]

        for order in deliveries_today:
            # Create delivery
            delivery = SupplierDelivery(
                order_id=order.order_id,
                products=order.products,
                delivery_day=self.current_day,
            )
            ctx.send(delivery)

            # Send delivery notification email
            items_text = ", ".join(f"{qty} {p.value}" for p, qty in order.products.items())
            supplier_name = order.supplier_name or "Supplier"
            supplier_email = order.supplier_email or "supplier@unknown.com"
            delivery_body = (
                f"Your order has been delivered!\n\n"
                f"Order ID: {order.order_id}\n"
                f"Items: {items_text}\n\n"
                f"Please restock your vending machine at your earliest convenience.\n\n"
                f"Best regards,\n{supplier_name}"
            )
            delivery_email = Email(
                from_address=supplier_email,
                to_address=OPERATOR_EMAIL,
                subject=f"Delivery Arrived - Order {order.order_id}",
                body=delivery_body,
            )
            self.inbox.append(delivery_email)

            # Remove from pending
            del self.pending_orders[order.order_id]

            logger.info(f"Delivery for order {order.order_id} arrived on day {self.current_day}")

        # Persist state changes
        self._persist_state(ctx)

    @agent.processor(ScratchpadReadRequest)
    def handle_scratchpad_read(self, ctx: ProcessContext[ScratchpadReadRequest]):
        """Handle scratchpad read request."""
        # Load state from guild state
        self._load_state_from_guild()

        request = ctx.payload

        if request.key:
            data = {request.key: self.scratchpad.get(request.key, "")}
        else:
            data = dict(self.scratchpad)

        response = ScratchpadReadResponse(
            request_id=request.request_id,
            data=data,
            time_elapsed_minutes=TIME_COSTS["scratchpad_read"],
            simulation_time=self.simulation_time,
        )
        ctx.send(response)

    @agent.processor(ScratchpadWriteRequest)
    def handle_scratchpad_write(self, ctx: ProcessContext[ScratchpadWriteRequest]):
        """Handle scratchpad write request."""
        # Load state from guild state
        self._load_state_from_guild()

        request = ctx.payload

        self.scratchpad[request.key] = request.value

        # Persist all state
        self._persist_state(ctx)

        response = ScratchpadWriteResponse(
            request_id=request.request_id,
            key=request.key,
            success=True,
            message=f"Saved note under key '{request.key}'",
            time_elapsed_minutes=TIME_COSTS["scratchpad_write"],
            simulation_time=self.simulation_time,
        )
        ctx.send(response)
        logger.debug(f"Scratchpad write: {request.key} = {request.value[:50]}...")

    @agent.processor(ViewSuppliersRequest)
    def handle_view_suppliers(self, ctx: ProcessContext[ViewSuppliersRequest]):
        """Handle request to view known suppliers."""
        self._load_state_from_guild()

        request = ctx.payload

        # Filter suppliers
        if request.active_only:
            suppliers = list(self.registry.get_active_suppliers().values())
        else:
            suppliers = list(self.registry.suppliers.values())

        # Apply product filter if specified
        if request.product_filter:
            suppliers = [s for s in suppliers if request.product_filter in s.products_offered]

        total_active = sum(1 for s in self.registry.suppliers.values() if s.is_active)

        response = ViewSuppliersResponse(
            request_id=request.request_id,
            suppliers=suppliers,
            total_active=total_active,
            message=f"Found {len(suppliers)} suppliers matching your criteria",
        )
        ctx.send(response)

        logger.debug(f"Viewed suppliers: {len(suppliers)} returned")
