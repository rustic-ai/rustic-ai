"""
CustomerComplaintAgent - Generates and manages customer complaints requiring refunds.

This agent:
- Generates daily customer complaints based on various factors
- Manages complaint resolution
- Tracks reputation impact
- Processes refunds
"""

import logging
import random
from typing import Dict, List, Optional

from pydantic import Field
import shortuuid

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.showcase.vending_bench.config import DEFAULT_PRICES, ProductType
from rustic_ai.showcase.vending_bench.messages import (
    DayUpdateEvent,
    Email,
    SimulationTime,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.supplier_config import (
    BASE_COMPLAINT_RATE,
    COMPLAINT_REFUND_AMOUNTS,
    COMPLAINT_REPUTATION_PENALTY,
    HIGH_PRICE_COMPLAINT_BONUS,
    INITIAL_REPUTATION_SCORE,
    MAX_REPUTATION_SCORE,
    MIN_REPUTATION_SCORE,
    OPERATOR_EMAIL,
    OUT_OF_STOCK_COMPLAINT_BONUS,
    RESOLVED_COMPLAINT_REPUTATION_GAIN,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    ComplaintResolution,
    ComplaintStatus,
    ComplaintType,
    CustomerComplaint,
    RespondToComplaintRequest,
    RespondToComplaintResponse,
    ViewComplaintsRequest,
    ViewComplaintsResponse,
)

logger = logging.getLogger(__name__)


# Complaint templates for generating realistic complaints
COMPLAINT_TEMPLATES = {
    ComplaintType.MACHINE_MALFUNCTION: [
        "The vending machine ate my money and didn't give me my {product}! I want my ${amount:.2f} back!",
        "Machine jammed when I tried to buy {product}. Lost ${amount:.2f}. Please refund ASAP.",
        "Your machine malfunctioned - item got stuck. I paid ${amount:.2f} and got nothing!",
        "The card reader took my payment but the {product} never came out. Requesting refund of ${amount:.2f}.",
    ],
    ComplaintType.WRONG_PRODUCT: [
        "I selected {product} but got something completely different! Want my money back.",
        "Machine gave me the wrong item. I paid for {product} but received something else. Refund please.",
        "Dispensed wrong product - I pressed {product} but got chips instead. ${amount:.2f} refund requested.",
    ],
    ComplaintType.EXPIRED_PRODUCT: [
        "The {product} I bought was expired! This is unacceptable. Refund demanded.",
        "Just bought {product} and it was past the expiration date. Want ${amount:.2f} back plus compensation.",
        "Expired goods in your machine! The {product} I purchased was stale/expired.",
    ],
    ComplaintType.PRICE_DISPUTE: [
        "Charged ${amount:.2f} for {product} but the label said it was cheaper! Overcharge refund please.",
        "Price discrepancy - machine charged more than displayed price for {product}.",
        "Your machine is price gouging! ${amount:.2f} for a {product}? Want partial refund.",
    ],
}


class CustomerComplaintAgentProps(BaseAgentProps):
    """Configuration for CustomerComplaintAgent."""

    base_complaint_rate: float = Field(default=BASE_COMPLAINT_RATE, description="Base daily complaint probability")
    enable_complaints: bool = Field(default=True, description="Enable complaint generation")


class CustomerComplaintAgent(Agent[CustomerComplaintAgentProps]):
    """Agent that generates and manages customer complaints.

    Simulates realistic customer complaints that require operator attention
    and refund processing.
    """

    def __init__(self):
        self.complaints: Dict[str, CustomerComplaint] = {}
        self.reputation_score: float = INITIAL_REPUTATION_SCORE
        self.current_day: int = 1
        self.simulation_time: SimulationTime = SimulationTime(
            current_day=1,
            current_time_minutes=0,
            is_daytime=True,
            weather=WeatherType.SUNNY,
            day_of_week=0,
        )
        # Track factors that affect complaint rate
        self.out_of_stock_days: int = 0
        self.high_price_days: int = 0

    def _load_state_from_guild(self):
        """Load persisted state from guild state."""
        guild_state = self.get_guild_state() or {}

        # Load complaints
        complaints_data = guild_state.get("customer_complaints", {})
        self.complaints = {k: CustomerComplaint(**v) if isinstance(v, dict) else v for k, v in complaints_data.items()}

        # Load reputation
        self.reputation_score = guild_state.get("reputation_score", INITIAL_REPUTATION_SCORE)

        # Load current day
        self.current_day = guild_state.get("current_day", 1)

        # Load tracking factors
        self.out_of_stock_days = guild_state.get("out_of_stock_days", 0)
        self.high_price_days = guild_state.get("high_price_days", 0)

        # Load simulation time
        sim_time_data = guild_state.get("complaint_simulation_time")
        if sim_time_data:
            self.simulation_time = SimulationTime(**sim_time_data) if isinstance(sim_time_data, dict) else sim_time_data

    def _persist_state(self, ctx: ProcessContext):
        """Persist current state to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                "customer_complaints": {k: v.model_dump() for k, v in self.complaints.items()},
                "reputation_score": self.reputation_score,
                "out_of_stock_days": self.out_of_stock_days,
                "high_price_days": self.high_price_days,
                "complaint_simulation_time": self.simulation_time.model_dump(),
            },
        )

    def _calculate_complaint_rate(self) -> float:
        """Calculate the effective complaint rate based on various factors."""
        rate = self.config.base_complaint_rate

        # Increase rate if frequently out of stock
        if self.out_of_stock_days > 3:
            rate += OUT_OF_STOCK_COMPLAINT_BONUS

        # Increase rate if prices are high
        if self.high_price_days > 2:
            rate += HIGH_PRICE_COMPLAINT_BONUS

        # Lower reputation = more complaints
        if self.reputation_score < 50:
            rate *= 1.5
        elif self.reputation_score < 30:
            rate *= 2.0

        return min(rate, 0.3)  # Cap at 30% daily complaint chance

    def _generate_complaint_text(self, complaint_type: ComplaintType, product: ProductType, amount: float) -> str:
        """Generate a complaint description text."""
        templates = COMPLAINT_TEMPLATES.get(complaint_type, COMPLAINT_TEMPLATES[ComplaintType.MACHINE_MALFUNCTION])
        template = random.choice(templates)
        return template.format(product=product.value.replace("_", " "), amount=amount)

    def _calculate_refund_amount(self, complaint_type: ComplaintType, product: Optional[ProductType]) -> float:
        """Calculate the refund amount for a complaint."""
        base_range = COMPLAINT_REFUND_AMOUNTS.get(complaint_type.value, (1.0, 3.0))
        base_amount = random.uniform(base_range[0], base_range[1])

        # Add product price if applicable
        if product:
            product_price = DEFAULT_PRICES.get(product, 1.50)
            base_amount += product_price * random.uniform(0.5, 1.0)

        return round(base_amount, 2)

    def _generate_customer_email(self) -> str:
        """Generate a random customer email address."""
        names = ["john", "jane", "mike", "sarah", "alex", "chris", "pat", "sam", "taylor", "jordan"]
        domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "email.com"]
        return f"{random.choice(names)}{random.randint(1, 999)}@{random.choice(domains)}"

    def _update_reputation(self, change: float):
        """Update reputation score with bounds checking."""
        self.reputation_score = max(
            MIN_REPUTATION_SCORE,
            min(MAX_REPUTATION_SCORE, self.reputation_score + change),
        )

    @agent.processor(DayUpdateEvent)
    def generate_daily_complaints(self, ctx: ProcessContext[DayUpdateEvent]):
        """Generate complaints at the start of each day."""
        self._load_state_from_guild()

        event = ctx.payload
        self.current_day = event.day
        self.simulation_time = event.simulation_time

        if not self.config.enable_complaints:
            self._persist_state(ctx)
            return

        # Check for out-of-stock conditions (would need inventory data)
        # For now, use a simple random factor
        if random.random() < 0.2:
            self.out_of_stock_days += 1
        else:
            self.out_of_stock_days = max(0, self.out_of_stock_days - 1)

        # Calculate complaint probability
        complaint_rate = self._calculate_complaint_rate()

        # Generate complaints
        if random.random() < complaint_rate:
            self._generate_complaint(ctx)

        # Apply reputation penalty for unresolved complaints
        open_complaints = [c for c in self.complaints.values() if c.status == ComplaintStatus.OPEN]
        for complaint in open_complaints:
            days_open = self.current_day - complaint.created_on_day
            if days_open > 3:  # Penalty after 3 days unresolved
                self._update_reputation(-COMPLAINT_REPUTATION_PENALTY * 0.5)

        self._persist_state(ctx)

    def _generate_complaint(self, ctx: ProcessContext):
        """Generate a single customer complaint."""
        complaint_type = random.choice(list(ComplaintType))
        product = random.choice(list(ProductType))
        refund_amount = self._calculate_refund_amount(complaint_type, product)
        customer_email = self._generate_customer_email()
        description = self._generate_complaint_text(complaint_type, product, refund_amount)

        complaint = CustomerComplaint(
            complaint_type=complaint_type,
            customer_email=customer_email,
            description=description,
            refund_requested=refund_amount,
            product_involved=product,
            status=ComplaintStatus.OPEN,
            created_on_day=self.current_day,
        )

        self.complaints[complaint.complaint_id] = complaint

        # Apply reputation penalty
        self._update_reputation(-COMPLAINT_REPUTATION_PENALTY)

        # Send email to operator
        email = Email(
            from_address=customer_email,
            to_address=OPERATOR_EMAIL,
            subject=f"Complaint: {complaint_type.value.replace('_', ' ').title()} - ID #{complaint.complaint_id}",
            body=f"""Dear Vending Machine Operator,

{description}

Complaint ID: {complaint.complaint_id}
Refund Requested: ${refund_amount:.2f}

Please respond to this complaint promptly.

Customer: {customer_email}""",
        )
        ctx.send(email)

        logger.info(f"Generated complaint {complaint.complaint_id}: {complaint_type.value}, ${refund_amount:.2f}")

    @agent.processor(ViewComplaintsRequest)
    def handle_view_complaints(self, ctx: ProcessContext[ViewComplaintsRequest]):
        """Handle request to view complaints."""
        self._load_state_from_guild()

        request = ctx.payload

        if request.status_filter:
            filtered = [c for c in self.complaints.values() if c.status == request.status_filter]
        else:
            filtered = list(self.complaints.values())

        # Sort by creation date
        filtered.sort(key=lambda c: c.created_on_day, reverse=True)

        total_open = sum(1 for c in self.complaints.values() if c.status == ComplaintStatus.OPEN)
        total_pending = sum(
            c.refund_requested
            for c in self.complaints.values()
            if c.status in (ComplaintStatus.OPEN, ComplaintStatus.PENDING_RESPONSE)
        )

        response = ViewComplaintsResponse(
            request_id=request.request_id,
            complaints=filtered,
            total_open=total_open,
            total_pending_refunds=total_pending,
        )
        ctx.send(response)

    @agent.processor(RespondToComplaintRequest)
    def handle_respond_to_complaint(self, ctx: ProcessContext[RespondToComplaintRequest]):
        """Handle response to a customer complaint."""
        self._load_state_from_guild()

        request = ctx.payload
        complaint = self.complaints.get(request.complaint_id)

        if not complaint:
            response = RespondToComplaintResponse(
                request_id=request.request_id,
                complaint_id=request.complaint_id,
                success=False,
                new_operator_cash=0,
                message=f"Complaint {request.complaint_id} not found",
            )
            ctx.send(response)
            return

        # Get operator cash from guild state
        guild_state = self.get_guild_state() or {}
        operator_cash = guild_state.get("operator_cash", 500.0)

        refund_amount = 0.0
        reputation_change = 0.0

        if request.action == "refund":
            # Full refund
            refund_amount = complaint.refund_requested
            reputation_change = RESOLVED_COMPLAINT_REPUTATION_GAIN * 2
            complaint.status = ComplaintStatus.RESOLVED
            complaint.resolution_notes = "Full refund issued"

        elif request.action == "partial_refund":
            # Partial refund
            refund_amount = request.refund_amount if request.refund_amount else complaint.refund_requested * 0.5
            reputation_change = RESOLVED_COMPLAINT_REPUTATION_GAIN
            complaint.status = ComplaintStatus.RESOLVED
            complaint.resolution_notes = f"Partial refund of ${refund_amount:.2f} issued"

        elif request.action == "deny":
            # Deny refund - reputation hit
            reputation_change = -COMPLAINT_REPUTATION_PENALTY
            complaint.status = ComplaintStatus.RESOLVED
            complaint.resolution_notes = "Refund denied"

        elif request.action == "apologize":
            # Apologize without refund - small reputation gain
            reputation_change = RESOLVED_COMPLAINT_REPUTATION_GAIN * 0.5
            complaint.status = ComplaintStatus.RESOLVED
            complaint.resolution_notes = "Apology issued"

        else:
            response = RespondToComplaintResponse(
                request_id=request.request_id,
                complaint_id=request.complaint_id,
                success=False,
                new_operator_cash=operator_cash,
                message=f"Unknown action: {request.action}. Use 'refund', 'partial_refund', 'deny', or 'apologize'.",
            )
            ctx.send(response)
            return

        # Process refund if applicable
        if refund_amount > 0:
            if operator_cash >= refund_amount:
                operator_cash -= refund_amount
                # Update operator cash in guild state
                self.update_guild_state(
                    ctx,
                    update_format=StateUpdateFormat.JSON_MERGE_PATCH,
                    update={"operator_cash": operator_cash},
                )
            else:
                response = RespondToComplaintResponse(
                    request_id=request.request_id,
                    complaint_id=request.complaint_id,
                    success=False,
                    new_operator_cash=operator_cash,
                    message=f"Insufficient funds for refund. Required: ${refund_amount:.2f}, Available: ${operator_cash:.2f}",
                )
                ctx.send(response)
                return

        # Update reputation
        self._update_reputation(reputation_change)

        # Mark resolution day
        complaint.resolved_on_day = self.current_day

        # Send resolution email to customer
        resolution_email = Email(
            from_address=OPERATOR_EMAIL,
            to_address=complaint.customer_email,
            subject=f"Re: Complaint #{complaint.complaint_id} - Resolution",
            body=request.response_message or f"Your complaint has been resolved. {complaint.resolution_notes}",
        )
        ctx.send(resolution_email)

        # Send ComplaintResolution event
        resolution = ComplaintResolution(
            complaint_id=complaint.complaint_id,
            resolution_type=request.action,
            refund_amount=refund_amount,
            success=True,
            message=complaint.resolution_notes,
            reputation_impact=reputation_change,
        )
        ctx.send(resolution)

        self._persist_state(ctx)

        response = RespondToComplaintResponse(
            request_id=request.request_id,
            complaint_id=request.complaint_id,
            success=True,
            refund_processed=refund_amount,
            new_operator_cash=operator_cash,
            reputation_change=reputation_change,
            message=f"Complaint resolved: {complaint.resolution_notes}. New reputation: {self.reputation_score:.1f}",
        )
        ctx.send(response)

        logger.info(f"Complaint {complaint.complaint_id} resolved: {request.action}, refund=${refund_amount:.2f}")
