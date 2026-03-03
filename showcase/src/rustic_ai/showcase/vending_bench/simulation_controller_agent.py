"""
SimulationControllerAgent - Controls the simulation lifecycle.

This agent:
- Manages simulation start/pause/reset
- Tracks time progression
- Handles day/night cycles
- Checks termination conditions (bankruptcy)
- Deducts daily fees
"""

import logging
import random
from typing import Dict

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.showcase.vending_bench.config import (
    BANKRUPTCY_DAYS,
    DAILY_FEE,
    DAY_DURATION_MINUTES,
    DEFAULT_PRICES,
    DEFAULT_STOCK,
    NIGHT_DURATION_MINUTES,
    STARTING_CAPITAL,
    TIME_COSTS,
    ProductType,
)
from rustic_ai.showcase.vending_bench.messages import (
    ActionType,
    AgentActionRequest,
    AgentActionResponse,
    CheckBalanceRequest,
    CheckBalanceResponse,
    CheckInventoryRequest,
    CheckInventoryResponse,
    CollectCashRequest,
    CollectCashResponse,
    CustomerPurchaseEvent,
    DayUpdateEvent,
    EndDayRequest,
    EndDayResponse,
    NightUpdateEvent,
    ReadEmailsRequest,
    ReadEmailsResponse,
    RestockRequest,
    RestockResponse,
    ScratchpadReadRequest,
    ScratchpadReadResponse,
    ScratchpadWriteRequest,
    ScratchpadWriteResponse,
    SendEmailRequest,
    SendEmailResponse,
    SetPriceRequest,
    SetPriceResponse,
    SimulationControlCommand,
    SimulationControlRequest,
    SimulationControlResponse,
    SimulationStatus,
    SimulationTime,
    TimeAdvanceRequest,
    TimeAdvanceResponse,
    VendingMachineState,
    WaitRequest,
    WaitResponse,
    WeatherType,
)

logger = logging.getLogger(__name__)


class SimulationControllerAgentProps(BaseAgentProps):
    """Configuration properties for SimulationControllerAgent."""

    starting_capital: float = Field(default=STARTING_CAPITAL)
    daily_fee: float = Field(default=DAILY_FEE)
    bankruptcy_days: int = Field(default=BANKRUPTCY_DAYS)
    day_duration_minutes: int = Field(default=DAY_DURATION_MINUTES)
    night_duration_minutes: int = Field(default=NIGHT_DURATION_MINUTES)
    auto_advance_time: bool = Field(default=True, description="Automatically advance time on actions")


class SimulationControllerAgent(Agent[SimulationControllerAgentProps]):
    """Agent controlling the simulation lifecycle.

    Manages time progression, day/night cycles, and termination conditions.
    Each agent action advances simulation time according to TIME_COSTS.
    """

    def __init__(self):
        # Simulation state
        self.status: SimulationStatus = SimulationStatus.PAUSED
        self.current_day: int = 1
        self.current_time_minutes: int = 0  # Minutes since day start
        self.day_of_week: int = 0  # 0 = Monday
        self.weather: WeatherType = WeatherType.SUNNY

        # Financial tracking
        self.operator_cash: float = self.config.starting_capital
        self.machine_cash: float = 0.0
        self.inventory: Dict[ProductType, int] = {p: DEFAULT_STOCK[p] for p in ProductType}
        self.prices: Dict[ProductType, float] = {p: DEFAULT_PRICES[p] for p in ProductType}

        # Bankruptcy tracking
        self.days_without_payment: int = 0

        # Statistics
        self.total_sales: int = 0
        self.total_revenue: float = 0.0
        self.action_counts: Dict[str, int] = {}

        # Daily tracking
        self.daily_sales: int = 0
        self.daily_revenue: float = 0.0

    @property
    def is_daytime(self) -> bool:
        """Check if it's currently daytime (business hours)."""
        return self.current_time_minutes < self.config.day_duration_minutes

    def get_simulation_time(self) -> SimulationTime:
        """Get current simulation time state."""
        return SimulationTime(
            current_day=self.current_day,
            current_time_minutes=self.current_time_minutes,
            is_daytime=self.is_daytime,
            weather=self.weather,
            day_of_week=self.day_of_week,
        )

    def get_vending_state(self) -> VendingMachineState:
        """Get current vending machine state."""
        return VendingMachineState(
            inventory=self.inventory,
            machine_cash=self.machine_cash,
            operator_cash=self.operator_cash,
            prices=self.prices,
            day=self.current_day,
            total_sales=self.total_sales,
            total_revenue=self.total_revenue,
        )

    def _generate_weather(self) -> WeatherType:
        """Generate random weather for a new day."""
        return random.choice(list(WeatherType))

    def _advance_time(self, minutes: int, ctx: ProcessContext) -> bool:
        """Advance simulation time and handle day transitions.

        Args:
            minutes: Minutes to advance
            ctx: Process context for sending events

        Returns:
            True if a day transition occurred
        """
        if self.status != SimulationStatus.RUNNING:
            return False

        self.current_time_minutes += minutes
        day_changed = False

        # Check for day transition
        total_day_minutes = self.config.day_duration_minutes + self.config.night_duration_minutes

        while self.current_time_minutes >= total_day_minutes:
            self.current_time_minutes -= total_day_minutes
            day_changed = True
            self._transition_to_new_day(ctx)

        # Check for night transition (end of business hours)
        if not day_changed and self.current_time_minutes >= self.config.day_duration_minutes:
            # Just entered night - but don't emit NightUpdateEvent multiple times
            pass

        # Persist current time to guild state so other agents can read it
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                "current_day": self.current_day,
                "current_time_minutes": self.current_time_minutes,
            },
        )

        return day_changed

    def _transition_to_new_day(self, ctx: ProcessContext):
        """Handle transition to a new day."""
        # Emit night update for the ending day
        night_event = NightUpdateEvent(
            day=self.current_day,
            total_sales_today=self.daily_sales,
            total_revenue_today=self.daily_revenue,
            ending_inventory=self.inventory.copy(),
            machine_cash=self.machine_cash,
            operator_cash=self.operator_cash,
            simulation_time=self.get_simulation_time(),
        )
        ctx.send(night_event)

        # Reset daily counters
        self.daily_sales = 0
        self.daily_revenue = 0.0

        # Advance to new day
        self.current_day += 1
        self.day_of_week = (self.day_of_week + 1) % 7
        self.weather = self._generate_weather()

        # Deduct daily fee
        fee = self.config.daily_fee
        if self.operator_cash >= fee:
            self.operator_cash -= fee
            self.days_without_payment = 0
        elif self.machine_cash >= fee:
            self.machine_cash -= fee
            self.days_without_payment = 0
        else:
            # Can't pay fee
            self.days_without_payment += 1
            logger.warning(
                f"Day {self.current_day}: Unable to pay daily fee. Days without payment: {self.days_without_payment}"
            )

        # Check bankruptcy
        if self.days_without_payment >= self.config.bankruptcy_days:
            self.status = SimulationStatus.BANKRUPT
            logger.info(f"BANKRUPT on day {self.current_day} after {self.days_without_payment} days without payment")
            return

        # Emit day update event
        day_event = DayUpdateEvent(
            day=self.current_day,
            weather=self.weather,
            day_of_week=self.day_of_week,
            simulation_time=self.get_simulation_time(),
            daily_fee_deducted=fee if self.days_without_payment == 0 else 0,
            remaining_cash=self.operator_cash + self.machine_cash,
            days_without_payment=self.days_without_payment,
        )
        ctx.send(day_event)

        # Persist state
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                "current_day": self.current_day,
                "operator_cash": self.operator_cash,
                "machine_cash": self.machine_cash,
                "days_without_payment": self.days_without_payment,
            },
        )

        logger.info(f"Day {self.current_day} started. Weather: {self.weather.value}")

    def _record_action(self, action: str):
        """Record an action in the statistics."""
        self.action_counts[action] = self.action_counts.get(action, 0) + 1

    @agent.processor(SimulationControlRequest)
    def handle_simulation_control(self, ctx: ProcessContext[SimulationControlRequest]):
        """Handle simulation control commands."""
        request = ctx.payload
        command = request.command

        if command == SimulationControlCommand.START:
            if self.status == SimulationStatus.PAUSED:
                self.status = SimulationStatus.RUNNING
                # Emit initial day event
                self.weather = self._generate_weather()
                day_event = DayUpdateEvent(
                    day=self.current_day,
                    weather=self.weather,
                    day_of_week=self.day_of_week,
                    simulation_time=self.get_simulation_time(),
                    daily_fee_deducted=0,  # No fee on first day
                    remaining_cash=self.operator_cash + self.machine_cash,
                    days_without_payment=0,
                )
                ctx.send(day_event)
                message = "Simulation started"
            else:
                message = f"Cannot start: simulation is {self.status.value}"

        elif command == SimulationControlCommand.PAUSE:
            if self.status == SimulationStatus.RUNNING:
                self.status = SimulationStatus.PAUSED
                message = "Simulation paused"
            else:
                message = f"Cannot pause: simulation is {self.status.value}"

        elif command == SimulationControlCommand.RESUME:
            if self.status == SimulationStatus.PAUSED:
                self.status = SimulationStatus.RUNNING
                message = "Simulation resumed"
            else:
                message = f"Cannot resume: simulation is {self.status.value}"

        elif command == SimulationControlCommand.RESET:
            self._reset_simulation()
            message = "Simulation reset"

        elif command == SimulationControlCommand.GET_STATUS:
            message = f"Status: {self.status.value}, Day: {self.current_day}"

        elif command == SimulationControlCommand.STEP:
            # Advance by one action's worth of time (use medium action time)
            if self.status == SimulationStatus.RUNNING:
                self._advance_time(25, ctx)
                message = "Advanced simulation by 25 minutes"
            else:
                message = f"Cannot step: simulation is {self.status.value}"

        else:
            message = f"Unknown command: {command}"

        response = SimulationControlResponse(
            request_id=request.request_id,
            command=command,
            success=True,
            message=message,
            simulation_status=self.status,
            simulation_time=self.get_simulation_time(),
            vending_machine_state=self.get_vending_state(),
        )
        ctx.send(response)

    def _reset_simulation(self):
        """Reset simulation to initial state."""
        self.status = SimulationStatus.PAUSED
        self.current_day = 1
        self.current_time_minutes = 0
        self.day_of_week = 0
        self.weather = WeatherType.SUNNY
        self.operator_cash = self.config.starting_capital
        self.machine_cash = 0.0
        self.inventory = {p: DEFAULT_STOCK[p] for p in ProductType}
        self.prices = {p: DEFAULT_PRICES[p] for p in ProductType}
        self.days_without_payment = 0
        self.total_sales = 0
        self.total_revenue = 0.0
        self.daily_sales = 0
        self.daily_revenue = 0.0
        self.action_counts = {}

    @agent.processor(AgentActionRequest)
    def handle_agent_action(self, ctx: ProcessContext[AgentActionRequest]):
        """Handle generic action requests from external agents via G2G.

        Routes the action to the appropriate handler and advances time.
        """
        request = ctx.payload
        action_type = request.action_type

        # Record the action
        self._record_action(action_type.value)

        # Route to appropriate internal message
        if action_type == ActionType.CHECK_INVENTORY:
            internal_request = CheckInventoryRequest(request_id=request.request_id)
            ctx.send(internal_request)

        elif action_type == ActionType.CHECK_BALANCE:
            internal_request = CheckBalanceRequest(request_id=request.request_id)
            ctx.send(internal_request)

        elif action_type == ActionType.SET_PRICE:
            product = ProductType(request.parameters.get("product"))
            new_price = float(request.parameters.get("new_price", 0))
            internal_request = SetPriceRequest(request_id=request.request_id, product=product, new_price=new_price)
            ctx.send(internal_request)

        elif action_type == ActionType.COLLECT_CASH:
            internal_request = CollectCashRequest(request_id=request.request_id)
            ctx.send(internal_request)

        elif action_type == ActionType.RESTOCK:
            delivery_id = request.parameters.get("delivery_id", "")
            internal_request = RestockRequest(request_id=request.request_id, delivery_id=delivery_id)
            ctx.send(internal_request)

        elif action_type == ActionType.READ_EMAILS:
            unread_only = request.parameters.get("unread_only", True)
            internal_request = ReadEmailsRequest(request_id=request.request_id, unread_only=unread_only)
            ctx.send(internal_request)

        elif action_type == ActionType.SEND_EMAIL:
            internal_request = SendEmailRequest(
                request_id=request.request_id,
                to_address=request.parameters.get("to_address", ""),
                subject=request.parameters.get("subject", ""),
                body=request.parameters.get("body", ""),
            )
            ctx.send(internal_request)

        elif action_type == ActionType.SCRATCHPAD_READ:
            key = request.parameters.get("key")
            internal_request = ScratchpadReadRequest(request_id=request.request_id, key=key)
            ctx.send(internal_request)

        elif action_type == ActionType.SCRATCHPAD_WRITE:
            internal_request = ScratchpadWriteRequest(
                request_id=request.request_id,
                key=request.parameters.get("key", ""),
                value=request.parameters.get("value", ""),
            )
            ctx.send(internal_request)

        elif action_type == ActionType.WAIT:
            hours = request.parameters.get("hours", 1)
            internal_request = WaitRequest(request_id=request.request_id, hours=hours)
            ctx.send(internal_request)

        elif action_type == ActionType.END_DAY:
            internal_request = EndDayRequest(request_id=request.request_id)
            ctx.send(internal_request)

        # Advance time based on action (skip for wait and end_day which handle their own time)
        if self.config.auto_advance_time and action_type not in (ActionType.WAIT, ActionType.END_DAY):
            time_cost = TIME_COSTS.get(action_type.value, 5)
            self._advance_time(time_cost, ctx)

    @agent.processor(TimeAdvanceRequest)
    def handle_time_advance(self, ctx: ProcessContext[TimeAdvanceRequest]):
        """Handle explicit time advance requests."""
        request = ctx.payload

        day_changed = self._advance_time(request.minutes, ctx)

        response = TimeAdvanceResponse(
            new_time=self.get_simulation_time(),
            day_changed=day_changed,
            events_generated=["DayUpdateEvent"] if day_changed else [],
        )
        ctx.send(response)

    @agent.processor(WaitRequest)
    def handle_wait(self, ctx: ProcessContext[WaitRequest]):
        """Handle wait requests - let time pass."""
        request = ctx.payload
        hours = min(max(request.hours, 1), 12)  # Clamp between 1 and 12
        minutes_to_wait = hours * 60

        events = []
        starting_day = self.current_day

        day_changed = self._advance_time(minutes_to_wait, ctx)
        if day_changed:
            events.append("DayUpdateEvent")

        response = WaitResponse(
            request_id=request.request_id,
            hours_waited=hours,
            time_elapsed_minutes=minutes_to_wait,
            simulation_time=self.get_simulation_time(),
            events_during_wait=events,
        )
        ctx.send(response)

    @agent.processor(EndDayRequest)
    def handle_end_day(self, ctx: ProcessContext[EndDayRequest]):
        """Handle end day requests - skip to the next day."""
        request = ctx.payload
        previous_day = self.current_day

        # Calculate minutes remaining until end of day (1440 minutes total)
        total_day_minutes = self.config.day_duration_minutes + self.config.night_duration_minutes
        minutes_to_end = total_day_minutes - self.current_time_minutes

        # If already past the day, just advance a small amount to trigger transition
        if minutes_to_end <= 0:
            minutes_to_end = 1

        self._advance_time(minutes_to_end, ctx)

        day_summary = (
            f"Day {previous_day} ended. Sales: {self.daily_sales} items, "
            f"Revenue: ${self.daily_revenue:.2f}. Now starting Day {self.current_day}."
        )

        response = EndDayResponse(
            request_id=request.request_id,
            previous_day=previous_day,
            new_day=self.current_day,
            time_elapsed_minutes=minutes_to_end,
            simulation_time=self.get_simulation_time(),
            day_summary=day_summary,
        )
        ctx.send(response)

    # Forward responses back to G2G gateway
    @agent.processor(CheckInventoryResponse)
    def forward_inventory_response(self, ctx: ProcessContext[CheckInventoryResponse]):
        """Forward inventory response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.CHECK_INVENTORY,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(CheckBalanceResponse)
    def forward_balance_response(self, ctx: ProcessContext[CheckBalanceResponse]):
        """Forward balance response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.CHECK_BALANCE,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(SetPriceResponse)
    def forward_price_response(self, ctx: ProcessContext[SetPriceResponse]):
        """Forward price response to G2G."""
        response = ctx.payload
        # Update local price cache
        self.prices[response.product] = response.new_price
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.SET_PRICE,
            success=response.success,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(CollectCashResponse)
    def forward_collect_response(self, ctx: ProcessContext[CollectCashResponse]):
        """Forward collect cash response to G2G."""
        response = ctx.payload
        # Update local cash cache
        self.machine_cash = response.new_machine_balance
        self.operator_cash = response.new_operator_balance
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.COLLECT_CASH,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(RestockResponse)
    def forward_restock_response(self, ctx: ProcessContext[RestockResponse]):
        """Forward restock response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.RESTOCK,
            success=response.success,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(ReadEmailsResponse)
    def forward_emails_response(self, ctx: ProcessContext[ReadEmailsResponse]):
        """Forward read emails response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.READ_EMAILS,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(SendEmailResponse)
    def forward_send_email_response(self, ctx: ProcessContext[SendEmailResponse]):
        """Forward send email response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.SEND_EMAIL,
            success=response.success,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(ScratchpadReadResponse)
    def forward_scratchpad_read_response(self, ctx: ProcessContext[ScratchpadReadResponse]):
        """Forward scratchpad read response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.SCRATCHPAD_READ,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(ScratchpadWriteResponse)
    def forward_scratchpad_write_response(self, ctx: ProcessContext[ScratchpadWriteResponse]):
        """Forward scratchpad write response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.SCRATCHPAD_WRITE,
            success=response.success,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(WaitResponse)
    def forward_wait_response(self, ctx: ProcessContext[WaitResponse]):
        """Forward wait response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.WAIT,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(EndDayResponse)
    def forward_end_day_response(self, ctx: ProcessContext[EndDayResponse]):
        """Forward end day response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        response_dict["simulation_time"] = current_time.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.END_DAY,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(CustomerPurchaseEvent)
    def handle_purchase(self, ctx: ProcessContext[CustomerPurchaseEvent]):
        """Track customer purchase for daily totals.

        Only counts sales that can actually be fulfilled from available inventory.
        """
        purchase = ctx.payload

        # Check available inventory before counting the sale
        available = self.inventory.get(purchase.product, 0)
        actual_quantity = min(purchase.quantity, available)

        if actual_quantity > 0:
            # Calculate actual revenue based on actual quantity sold
            unit_price = purchase.price_paid / purchase.quantity if purchase.quantity > 0 else 0
            actual_revenue = actual_quantity * unit_price

            self.daily_sales += actual_quantity
            self.daily_revenue += actual_revenue
            self.total_sales += actual_quantity
            self.total_revenue += actual_revenue

            # Update inventory cache
            self.inventory[purchase.product] = available - actual_quantity
