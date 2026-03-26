"""
VendingBench - A benchmark for testing LLM agent performance over long time horizons.

Based on the VendingBench paper (arxiv:2502.15840), this module implements a vending machine
business simulation where agents must balance inventories, place orders, set prices, and
handle daily fees to maintain sustained profitability.

Key components:
- VendingMachineAgent: Manages vending machine state (inventory, cash, prices)
- CustomerSimulatorAgent: Generates customer purchases based on demand model
- SupplierAgent: Handles email-based ordering and delivery scheduling
- SimulationControllerAgent: Controls simulation lifecycle and time progression
- EvaluatorAgent: Tracks metrics and produces evaluation results

The benchmark supports G2G communication, allowing external guilds to connect and "play"
the simulation via the standard gateway interface.
"""

from rustic_ai.showcase.vending_bench.config import (
    BANKRUPTCY_DAYS,
    DAILY_FEE,
    DEFAULT_COSTS,
    DEFAULT_PRICES,
    DEFAULT_STOCK,
    STARTING_CAPITAL,
    TIME_COSTS,
    ProductType,
)
from rustic_ai.showcase.vending_bench.economics import calculate_demand
from rustic_ai.showcase.vending_bench.messages import (
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
    Email,
    EvaluationResult,
    NetWorthReport,
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
    SimulationControlRequest,
    SimulationControlResponse,
    SimulationStatus,
    SimulationTime,
    SupplierDelivery,
    SupplierOrderConfirmation,
    VendingMachineState,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.player_toolset import (
    VendingBenchToolspecsProvider,
)

__all__ = [
    # Toolset
    "VendingBenchToolspecsProvider",
    # Config
    "STARTING_CAPITAL",
    "DAILY_FEE",
    "BANKRUPTCY_DAYS",
    "DEFAULT_PRICES",
    "DEFAULT_COSTS",
    "DEFAULT_STOCK",
    "TIME_COSTS",
    # Economics
    "calculate_demand",
    # Messages - Core types
    "ProductType",
    "WeatherType",
    "VendingMachineState",
    "SimulationTime",
    # Messages - Action requests/responses
    "CheckInventoryRequest",
    "CheckInventoryResponse",
    "CheckBalanceRequest",
    "CheckBalanceResponse",
    "SetPriceRequest",
    "SetPriceResponse",
    "CollectCashRequest",
    "CollectCashResponse",
    "RestockRequest",
    "RestockResponse",
    # Messages - Email system
    "Email",
    "ReadEmailsRequest",
    "ReadEmailsResponse",
    "SendEmailRequest",
    "SendEmailResponse",
    "SupplierOrderConfirmation",
    "SupplierDelivery",
    # Messages - Scratchpad
    "ScratchpadReadRequest",
    "ScratchpadReadResponse",
    "ScratchpadWriteRequest",
    "ScratchpadWriteResponse",
    # Messages - Simulation events
    "DayUpdateEvent",
    "NightUpdateEvent",
    "CustomerPurchaseEvent",
    # Messages - Evaluation
    "NetWorthReport",
    "SimulationStatus",
    "EvaluationResult",
    # Messages - G2G interface
    "AgentActionRequest",
    "AgentActionResponse",
    "SimulationControlRequest",
    "SimulationControlResponse",
]
