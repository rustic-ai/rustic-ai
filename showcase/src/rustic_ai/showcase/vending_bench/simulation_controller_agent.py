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
from rustic_ai.showcase.vending_bench.state_keys import (
    CURRENT_DAY,
    CURRENT_TIME_MINUTES,
    DAYS_WITHOUT_PAYMENT,
    MACHINE_CASH,
    OPERATOR_CASH,
    SIMULATION_STATUS,
    VM_INVENTORY,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    NegotiationExchangeRequest,
    NegotiationResponse,
    RespondToComplaintRequest,
    RespondToComplaintResponse,
    StartNegotiationRequest,
    SupplierSearchRequest,
    SupplierSearchResponse,
    ViewComplaintsRequest,
    ViewComplaintsResponse,
    ViewSuppliersRequest,
    ViewSuppliersResponse,
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
        # Note: Inventory is managed by VendingMachineAgent and read from guild state when needed
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

        # Track whether NightUpdateEvent has been emitted for current day
        self._night_emitted_for_day: int = 0

        # Flag to track if initial state has been loaded from guild
        self._state_initialized: bool = False

    def _load_state_from_guild(self):
        """Load persisted state from guild state.

        This ensures simulation status and other state survives agent re-instantiation.
        """
        if self._state_initialized:
            return

        guild_state = self.get_guild_state() or {}

        # Load simulation status - critical for time advancement
        status_str = guild_state.get(SIMULATION_STATUS)
        if status_str:
            try:
                self.status = SimulationStatus(status_str)
            except ValueError:
                pass  # Keep default PAUSED if invalid

        # Load other simulation state
        self.current_day = guild_state.get(CURRENT_DAY, self.current_day)
        self.current_time_minutes = guild_state.get(CURRENT_TIME_MINUTES, self.current_time_minutes)
        self.operator_cash = guild_state.get(OPERATOR_CASH, self.operator_cash)
        self.machine_cash = guild_state.get(MACHINE_CASH, self.machine_cash)
        self.days_without_payment = guild_state.get(DAYS_WITHOUT_PAYMENT, self.days_without_payment)

        self._state_initialized = True

    def _persist_status(self, ctx: ProcessContext):
        """Persist simulation status to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={SIMULATION_STATUS: self.status.value},
        )

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

    def _get_inventory_from_guild_state(self) -> Dict[ProductType, int]:
        """Read inventory from guild state (managed by VendingMachineAgent)."""
        guild_state = self.get_guild_state() or {}
        vm_inventory = guild_state.get(VM_INVENTORY, {})
        # Convert string keys back to ProductType enum
        inventory: Dict[ProductType, int] = {}
        for product in ProductType:
            inventory[product] = vm_inventory.get(product.value, DEFAULT_STOCK[product])
        return inventory

    def get_vending_state(self) -> VendingMachineState:
        """Get current vending machine state."""
        return VendingMachineState(
            inventory=self._get_inventory_from_guild_state(),
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
        if (
            not day_changed
            and self.current_time_minutes >= self.config.day_duration_minutes
            and self._night_emitted_for_day != self.current_day
        ):
            # Just entered night - emit NightUpdateEvent once per day
            self._night_emitted_for_day = self.current_day
            ending_inventory = self._get_inventory_from_guild_state()
            night_event = NightUpdateEvent(
                day=self.current_day,
                total_sales_today=self.daily_sales,
                total_revenue_today=self.daily_revenue,
                ending_inventory=ending_inventory,
                machine_cash=self.machine_cash,
                operator_cash=self.operator_cash,
                simulation_time=self.get_simulation_time(),
            )
            ctx.send(night_event)

        # Persist current time to guild state so other agents can read it
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                CURRENT_DAY: self.current_day,
                CURRENT_TIME_MINUTES: self.current_time_minutes,
            },
        )

        return day_changed

    def _transition_to_new_day(self, ctx: ProcessContext):
        """Handle transition to a new day."""
        # Emit night update for the ending day
        # Read inventory from guild state (managed by VendingMachineAgent)
        ending_inventory = self._get_inventory_from_guild_state()
        night_event = NightUpdateEvent(
            day=self.current_day,
            total_sales_today=self.daily_sales,
            total_revenue_today=self.daily_revenue,
            ending_inventory=ending_inventory,
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
        else:
            # Can't pay fee from either source
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
                CURRENT_DAY: self.current_day,
                OPERATOR_CASH: self.operator_cash,
                MACHINE_CASH: self.machine_cash,
                DAYS_WITHOUT_PAYMENT: self.days_without_payment,
            },
        )

        logger.info(f"Day {self.current_day} started. Weather: {self.weather.value}")

    def _record_action(self, action: str):
        """Record an action in the statistics."""
        self.action_counts[action] = self.action_counts.get(action, 0) + 1

    def _process_wait(self, request_id: str, hours: int, ctx: ProcessContext) -> WaitResponse:
        """Process wait logic and return response. Core logic shared by inline and message-based handling."""
        hours = min(max(hours, 1), 12)  # Clamp between 1 and 12
        minutes_to_wait = hours * 60

        events = []
        day_changed = self._advance_time(minutes_to_wait, ctx)
        if day_changed:
            events.append("DayUpdateEvent")

        return WaitResponse(
            request_id=request_id,
            hours_waited=hours,
            time_elapsed_minutes=minutes_to_wait,
            simulation_time=self.get_simulation_time(),
            events_during_wait=events,
        )

    def _process_end_day(self, request_id: str, ctx: ProcessContext) -> EndDayResponse:
        """Process end day logic and return response. Core logic shared by inline and message-based handling."""
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

        return EndDayResponse(
            request_id=request_id,
            previous_day=previous_day,
            new_day=self.current_day,
            time_elapsed_minutes=minutes_to_end,
            simulation_time=self.get_simulation_time(),
            day_summary=day_summary,
        )

    @agent.processor(SimulationControlRequest)
    def handle_simulation_control(self, ctx: ProcessContext[SimulationControlRequest]):
        """Handle simulation control commands."""
        self._load_state_from_guild()

        request = ctx.payload
        command = request.command
        status_changed = False

        if command == SimulationControlCommand.START:
            if self.status == SimulationStatus.PAUSED:
                self.status = SimulationStatus.RUNNING
                status_changed = True
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
                status_changed = True
                message = "Simulation paused"
            else:
                message = f"Cannot pause: simulation is {self.status.value}"

        elif command == SimulationControlCommand.RESUME:
            if self.status == SimulationStatus.PAUSED:
                self.status = SimulationStatus.RUNNING
                status_changed = True
                message = "Simulation resumed"
            else:
                message = f"Cannot resume: simulation is {self.status.value}"

        elif command == SimulationControlCommand.RESET:
            self._reset_simulation()
            status_changed = True
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

        # Persist status if it changed
        if status_changed:
            self._persist_status(ctx)

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
        # Note: Inventory is managed by VendingMachineAgent, not reset here
        self.prices = {p: DEFAULT_PRICES[p] for p in ProductType}
        self.days_without_payment = 0
        self.total_sales = 0
        self.total_revenue = 0.0
        self.daily_sales = 0
        self.daily_revenue = 0.0
        self.action_counts = {}
        self._night_emitted_for_day = 0

    @agent.processor(AgentActionRequest)
    def handle_agent_action(self, ctx: ProcessContext[AgentActionRequest]):  # noqa: C901
        """Handle generic action requests from external agents via G2G.

        Routes the action to the appropriate handler and advances time.
        """
        self._load_state_from_guild()

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
            # Process inline to avoid self-message filtering (messaging excludes sender from non-self-inbox topics)
            hours = request.parameters.get("hours", 1)
            wait_response = self._process_wait(request.request_id, hours, ctx)
            current_time = self.get_simulation_time()
            response_dict = wait_response.model_dump()
            response_dict["simulation_time"] = current_time.model_dump()
            wrapped = AgentActionResponse(
                request_id=request.request_id,
                action_type=ActionType.WAIT,
                success=True,
                response=response_dict,
                simulation_time=current_time,
            )
            ctx.send(wrapped)

        elif action_type == ActionType.END_DAY:
            # Process inline to avoid self-message filtering (messaging excludes sender from non-self-inbox topics)
            end_day_response = self._process_end_day(request.request_id, ctx)
            current_time = self.get_simulation_time()
            response_dict = end_day_response.model_dump()
            response_dict["simulation_time"] = current_time.model_dump()
            wrapped = AgentActionResponse(
                request_id=request.request_id,
                action_type=ActionType.END_DAY,
                success=True,
                response=response_dict,
                simulation_time=current_time,
            )
            ctx.send(wrapped)

        elif action_type == ActionType.SEARCH_SUPPLIERS:
            product_types_raw = request.parameters.get("product_types", [])
            product_types = [ProductType(p) for p in product_types_raw] if product_types_raw else []
            location = request.parameters.get("location", "")
            internal_request = SupplierSearchRequest(
                request_id=request.request_id,
                product_types=product_types,
                location=location,
            )
            ctx.send(internal_request)

        elif action_type == ActionType.VIEW_SUPPLIERS:
            active_only = request.parameters.get("active_only", True)
            product_filter_raw = request.parameters.get("product_filter")
            product_filter = ProductType(product_filter_raw) if product_filter_raw else None
            internal_request = ViewSuppliersRequest(
                request_id=request.request_id,
                active_only=active_only,
                product_filter=product_filter,
            )
            ctx.send(internal_request)

        elif action_type == ActionType.START_NEGOTIATION:
            supplier_id = request.parameters.get("supplier_id", "")
            product_type_raw = request.parameters.get("product_type")
            product_type = ProductType(product_type_raw) if product_type_raw else None
            target_discount = request.parameters.get("target_discount", 0.10)
            internal_request = StartNegotiationRequest(
                request_id=request.request_id,
                supplier_id=supplier_id,
                product_type=product_type,
                target_discount=target_discount,
            )
            ctx.send(internal_request)

        elif action_type == ActionType.NEGOTIATE:
            negotiation_id = request.parameters.get("negotiation_id", "")
            message = request.parameters.get("message", "")
            offer_price = request.parameters.get("offer_price")
            internal_request = NegotiationExchangeRequest(
                request_id=request.request_id,
                negotiation_id=negotiation_id,
                message=message,
                offer_price=float(offer_price) if offer_price else None,
            )
            ctx.send(internal_request)

        elif action_type == ActionType.VIEW_COMPLAINTS:
            status_filter_raw = request.parameters.get("status_filter")
            from rustic_ai.showcase.vending_bench.supplier_messages import (
                ComplaintStatus,
            )

            status_filter = ComplaintStatus(status_filter_raw) if status_filter_raw else None
            internal_request = ViewComplaintsRequest(
                request_id=request.request_id,
                status_filter=status_filter,
            )
            ctx.send(internal_request)

        elif action_type == ActionType.RESPOND_COMPLAINT:
            complaint_id = request.parameters.get("complaint_id", "")
            action = request.parameters.get("action", "")
            refund_amount = request.parameters.get("refund_amount")
            response_message = request.parameters.get("response_message", "")
            internal_request = RespondToComplaintRequest(
                request_id=request.request_id,
                complaint_id=complaint_id,
                action=action,
                refund_amount=float(refund_amount) if refund_amount else None,
                response_message=response_message,
            )
            ctx.send(internal_request)

        # Advance time based on action (skip for wait and end_day which handle their own time)
        if self.config.auto_advance_time and action_type not in (ActionType.WAIT, ActionType.END_DAY):
            time_cost = TIME_COSTS.get(action_type.value, 5)
            self._advance_time(time_cost, ctx)

    @agent.processor(TimeAdvanceRequest)
    def handle_time_advance(self, ctx: ProcessContext[TimeAdvanceRequest]):
        """Handle explicit time advance requests."""
        self._load_state_from_guild()

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
        self._load_state_from_guild()

        request = ctx.payload
        response = self._process_wait(request.request_id, request.hours, ctx)
        ctx.send(response)

    @agent.processor(EndDayRequest)
    def handle_end_day(self, ctx: ProcessContext[EndDayRequest]):
        """Handle end day requests - skip to the next day."""
        self._load_state_from_guild()

        request = ctx.payload
        response = self._process_end_day(request.request_id, ctx)
        ctx.send(response)

    # Forward responses back to G2G gateway
    @agent.processor(CheckInventoryResponse)
    def forward_inventory_response(self, ctx: ProcessContext[CheckInventoryResponse]):
        """Forward inventory response to G2G."""
        self._load_state_from_guild()

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

        Note: Inventory management is handled by VendingMachineAgent.
        This handler only tracks statistics for reporting purposes.
        The actual sale fulfillment (checking available stock) is done
        by VendingMachineAgent when it processes the same event.
        """
        self._load_state_from_guild()

        purchase = ctx.payload

        # Track the purchase for daily/total statistics
        # VendingMachineAgent handles actual inventory fulfillment
        self.daily_sales += purchase.quantity
        self.daily_revenue += purchase.price_paid
        self.total_sales += purchase.quantity
        self.total_revenue += purchase.price_paid

    # Response forwarders for new supplier and complaint actions

    @agent.processor(SupplierSearchResponse)
    def forward_supplier_search_response(self, ctx: ProcessContext[SupplierSearchResponse]):
        """Forward supplier search response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.SEARCH_SUPPLIERS,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(ViewSuppliersResponse)
    def forward_view_suppliers_response(self, ctx: ProcessContext[ViewSuppliersResponse]):
        """Forward view suppliers response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.VIEW_SUPPLIERS,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(NegotiationResponse)
    def forward_negotiation_response(self, ctx: ProcessContext[NegotiationResponse]):
        """Forward negotiation response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        # Determine action type based on whether this is a start or continuation
        action_type = ActionType.NEGOTIATE if response.negotiation_id else ActionType.START_NEGOTIATION
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=action_type,
            success=not response.is_rejected,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(ViewComplaintsResponse)
    def forward_view_complaints_response(self, ctx: ProcessContext[ViewComplaintsResponse]):
        """Forward view complaints response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.VIEW_COMPLAINTS,
            success=True,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)

    @agent.processor(RespondToComplaintResponse)
    def forward_respond_complaint_response(self, ctx: ProcessContext[RespondToComplaintResponse]):
        """Forward respond to complaint response to G2G."""
        response = ctx.payload
        current_time = self.get_simulation_time()
        response_dict = response.model_dump()
        wrapped = AgentActionResponse(
            request_id=response.request_id,
            action_type=ActionType.RESPOND_COMPLAINT,
            success=response.success,
            response=response_dict,
            simulation_time=current_time,
        )
        ctx.send(wrapped)
