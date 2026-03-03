"""
Message types for the VendingBench simulation.

All messages used for communication between agents in the vending machine benchmark.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, SerializationInfo, field_serializer
import shortuuid

from rustic_ai.showcase.vending_bench.config import ProductType


class WeatherType(str, Enum):
    """Weather conditions that affect customer demand."""

    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    HOT = "hot"
    COLD = "cold"


# =============================================================================
# Core State Types
# =============================================================================


class SimulationTime(BaseModel):
    """Current simulation time state."""

    current_day: int = Field(description="Current day number (starts at 1)")
    current_time_minutes: int = Field(description="Minutes since day start (0-1440, where 0-720 is daytime)")
    is_daytime: bool = Field(description="True during business hours (8 AM - 8 PM)")
    weather: WeatherType = Field(description="Current weather condition")
    day_of_week: int = Field(description="Day of week (0=Monday, 6=Sunday)", ge=0, le=6)


class VendingMachineState(BaseModel):
    """Complete state of the vending machine."""

    inventory: Dict[ProductType, int] = Field(default_factory=dict, description="Current inventory per product")
    machine_cash: float = Field(default=0.0, description="Cash in the machine")
    operator_cash: float = Field(default=0.0, description="Cash held by operator")
    prices: Dict[ProductType, float] = Field(default_factory=dict, description="Current prices per product")
    day: int = Field(default=1, description="Current simulation day")
    total_sales: int = Field(default=0, description="Total number of sales made")
    total_revenue: float = Field(default=0.0, description="Total revenue earned")


# =============================================================================
# Action Request/Response Types
# =============================================================================


class CheckInventoryRequest(BaseModel):
    """Request to check current inventory levels."""

    request_id: str = Field(default_factory=shortuuid.uuid)


class CheckInventoryResponse(BaseModel):
    """Response with current inventory levels."""

    request_id: str
    inventory: Dict[ProductType, int]
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class CheckBalanceRequest(BaseModel):
    """Request to check current cash balance and net worth."""

    request_id: str = Field(default_factory=shortuuid.uuid)


class CheckBalanceResponse(BaseModel):
    """Response with current balance information."""

    request_id: str
    machine_cash: float = Field(description="Cash in the vending machine")
    operator_cash: float = Field(description="Cash held by the operator")
    inventory_value: float = Field(description="Value of unsold inventory at cost")
    net_worth: float = Field(description="Total net worth")
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class SetPriceRequest(BaseModel):
    """Request to set price for a product."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    product: ProductType
    new_price: float = Field(ge=0.0)


class SetPriceResponse(BaseModel):
    """Response confirming price change."""

    request_id: str
    product: ProductType
    old_price: float
    new_price: float
    success: bool
    message: str
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class CollectCashRequest(BaseModel):
    """Request to collect cash from the vending machine."""

    request_id: str = Field(default_factory=shortuuid.uuid)


class CollectCashResponse(BaseModel):
    """Response confirming cash collection."""

    request_id: str
    amount_collected: float
    new_machine_balance: float
    new_operator_balance: float
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class RestockRequest(BaseModel):
    """Request to restock products from a delivered order."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    delivery_id: str = Field(description="Order ID from the delivery email (e.g., 'ORD-ABC123')")


class RestockResponse(BaseModel):
    """Response confirming restock operation."""

    request_id: str
    delivery_id: str
    products_restocked: Dict[ProductType, int]
    success: bool
    message: str
    time_elapsed_minutes: int
    simulation_time: SimulationTime


# =============================================================================
# Email System Types
# =============================================================================


class Email(BaseModel):
    """An email message in the simulation."""

    id: str = Field(default_factory=shortuuid.uuid)
    from_address: str
    to_address: str
    subject: str
    body: str
    timestamp: datetime = Field(default_factory=datetime.now)
    is_read: bool = False

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class ReadEmailsRequest(BaseModel):
    """Request to read emails from inbox."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    unread_only: bool = True


class ReadEmailsResponse(BaseModel):
    """Response with email list."""

    request_id: str
    emails: List[Email]
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class SendEmailRequest(BaseModel):
    """Request to send an email."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    to_address: str
    subject: str
    body: str


class SendEmailResponse(BaseModel):
    """Response confirming email was sent."""

    request_id: str
    success: bool
    message: str
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class SupplierOrderConfirmation(BaseModel):
    """Confirmation of a supplier order placement."""

    order_id: str = Field(default_factory=shortuuid.uuid)
    products: Dict[ProductType, int]
    total_cost: float
    expected_delivery_day: int
    confirmation_message: str


class SupplierDelivery(BaseModel):
    """A delivery from the supplier."""

    delivery_id: str = Field(default_factory=shortuuid.uuid)
    order_id: str
    products: Dict[ProductType, int]
    delivery_day: int


# =============================================================================
# Scratchpad Types
# =============================================================================


class ScratchpadReadRequest(BaseModel):
    """Request to read from the agent's scratchpad memory."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    key: Optional[str] = Field(default=None, description="Specific key to read, or None for all")


class ScratchpadReadResponse(BaseModel):
    """Response with scratchpad contents."""

    request_id: str
    data: Dict[str, str] = Field(description="Key-value pairs from scratchpad")
    time_elapsed_minutes: int
    simulation_time: SimulationTime


class ScratchpadWriteRequest(BaseModel):
    """Request to write to the agent's scratchpad memory."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    key: str
    value: str


class ScratchpadWriteResponse(BaseModel):
    """Response confirming scratchpad write."""

    request_id: str
    key: str
    success: bool
    message: str
    time_elapsed_minutes: int
    simulation_time: SimulationTime


# =============================================================================
# Time Management Types
# =============================================================================


class WaitRequest(BaseModel):
    """Request to wait and let time pass."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    hours: int = Field(default=1, ge=1, le=12, description="Number of hours to wait (1-12)")


class WaitResponse(BaseModel):
    """Response confirming time has passed."""

    request_id: str
    hours_waited: int
    time_elapsed_minutes: int
    simulation_time: SimulationTime
    events_during_wait: List[str] = Field(default_factory=list, description="Events that occurred during wait")


class EndDayRequest(BaseModel):
    """Request to end the current day and skip to the next day."""

    request_id: str = Field(default_factory=shortuuid.uuid)


class EndDayResponse(BaseModel):
    """Response confirming day has ended."""

    request_id: str
    previous_day: int
    new_day: int
    time_elapsed_minutes: int
    simulation_time: SimulationTime
    day_summary: str = Field(description="Summary of what happened during the day")


# =============================================================================
# Simulation Event Types
# =============================================================================


class DayUpdateEvent(BaseModel):
    """Event emitted at the start of each new day."""

    day: int = Field(description="The new day number")
    weather: WeatherType
    day_of_week: int = Field(ge=0, le=6)
    simulation_time: SimulationTime
    daily_fee_deducted: float
    remaining_cash: float
    days_without_payment: int = Field(default=0, description="Consecutive days unable to pay fee")


class NightUpdateEvent(BaseModel):
    """Event emitted at the end of each business day."""

    day: int
    total_sales_today: int
    total_revenue_today: float
    ending_inventory: Dict[ProductType, int]
    machine_cash: float = Field(default=0.0, description="Cash in the vending machine at end of day")
    operator_cash: float = Field(default=0.0, description="Cash held by the operator at end of day")
    simulation_time: SimulationTime


class CustomerPurchaseEvent(BaseModel):
    """Event representing a customer purchase."""

    purchase_id: str = Field(default_factory=shortuuid.uuid)
    product: ProductType
    quantity: int
    price_paid: float
    day: int
    time_of_day_minutes: int


# =============================================================================
# Evaluation Types
# =============================================================================


class NetWorthReport(BaseModel):
    """Daily net worth report."""

    day: int
    machine_cash: float
    operator_cash: float
    inventory_value: float
    net_worth: float
    change_from_previous: float = 0.0


class SimulationStatus(str, Enum):
    """Status of the simulation."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    BANKRUPT = "bankrupt"


class EvaluationResult(BaseModel):
    """Final evaluation result for the benchmark."""

    final_day: int
    final_net_worth: float
    starting_net_worth: float
    net_worth_change: float
    total_sales: int
    total_revenue: float
    daily_net_worth_history: List[NetWorthReport]
    action_counts: Dict[str, int] = Field(default_factory=dict, description="Count of each action type taken")
    simulation_status: SimulationStatus
    bankrupt: bool = False
    days_survived: int = 0
    success_message: str = ""


# =============================================================================
# G2G Interface Types
# =============================================================================


class ActionType(str, Enum):
    """Types of actions available to external agents."""

    CHECK_INVENTORY = "check_inventory"
    CHECK_BALANCE = "check_balance"
    SET_PRICE = "set_price"
    COLLECT_CASH = "collect_cash"
    RESTOCK = "restock"
    READ_EMAILS = "read_emails"
    SEND_EMAIL = "send_email"
    SCRATCHPAD_READ = "scratchpad_read"
    SCRATCHPAD_WRITE = "scratchpad_write"
    WAIT = "wait"
    END_DAY = "end_day"


class AgentActionRequest(BaseModel):
    """Generic action request for G2G interface.

    External guilds send this message to perform actions in the simulation.
    """

    request_id: str = Field(default_factory=shortuuid.uuid)
    action_type: ActionType
    parameters: Dict = Field(default_factory=dict, description="Action-specific parameters")


class AgentActionResponse(BaseModel):
    """Generic action response for G2G interface.

    Wraps the specific response type for external guilds.
    """

    request_id: str
    action_type: ActionType
    success: bool
    response: Dict = Field(description="Action-specific response data")
    error_message: Optional[str] = None
    simulation_time: SimulationTime


class SimulationControlCommand(str, Enum):
    """Commands for controlling the simulation."""

    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STEP = "step"  # Advance one action
    RESET = "reset"
    GET_STATUS = "get_status"


class SimulationControlRequest(BaseModel):
    """Request to control the simulation (start, pause, reset, etc.)."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    command: SimulationControlCommand
    config: Dict = Field(default_factory=dict, description="Optional configuration overrides")


class SimulationControlResponse(BaseModel):
    """Response to simulation control request."""

    request_id: str
    command: SimulationControlCommand
    success: bool
    message: str
    simulation_status: SimulationStatus
    simulation_time: Optional[SimulationTime] = None
    vending_machine_state: Optional[VendingMachineState] = None


# =============================================================================
# Internal Agent Communication Types
# =============================================================================


class TimeAdvanceRequest(BaseModel):
    """Internal request to advance simulation time."""

    minutes: int
    source_action: str = Field(description="The action that caused the time advance")


class TimeAdvanceResponse(BaseModel):
    """Internal response after time has been advanced."""

    new_time: SimulationTime
    day_changed: bool
    events_generated: List[str] = Field(default_factory=list, description="List of event types generated")


class DeliverySchedule(BaseModel):
    """Internal tracking of pending deliveries."""

    order_id: str
    products: Dict[ProductType, int]
    expected_delivery_day: int
    ordered_on_day: int
