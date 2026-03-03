"""
EvaluatorAgent - Tracks metrics and produces evaluation results.

This agent:
- Monitors daily net worth
- Tracks action usage statistics
- Produces final evaluation results
- Emits periodic net worth reports
"""

import logging
from typing import Dict, List

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.showcase.vending_bench.config import (
    DEFAULT_COSTS,
    STARTING_CAPITAL,
    ProductType,
)
from rustic_ai.showcase.vending_bench.economics import calculate_net_worth
from rustic_ai.showcase.vending_bench.messages import (
    AgentActionResponse,
    CheckBalanceResponse,
    CollectCashResponse,
    CustomerPurchaseEvent,
    DayUpdateEvent,
    EvaluationResult,
    NetWorthReport,
    NightUpdateEvent,
    RestockResponse,
    SetPriceResponse,
    SimulationControlResponse,
    SimulationStatus,
    VendingMachineState,
)

logger = logging.getLogger(__name__)


class EvaluatorAgentProps(BaseAgentProps):
    """Configuration properties for EvaluatorAgent."""

    emit_daily_reports: bool = Field(default=True, description="Emit daily net worth reports")
    starting_net_worth: float = Field(default=STARTING_CAPITAL)


class EvaluatorAgent(Agent[EvaluatorAgentProps]):
    """Agent that evaluates benchmark performance.

    Tracks net worth over time, action counts, and produces
    final evaluation results when the simulation ends.
    """

    def __init__(self):
        # Track daily net worth history
        self.daily_net_worth: List[NetWorthReport] = []
        self.starting_net_worth: float = self.config.starting_net_worth

        # Current state tracking
        self.current_day: int = 1
        self.current_machine_cash: float = 0.0
        self.current_operator_cash: float = self.starting_net_worth
        self.current_inventory: Dict[ProductType, int] = {}

        # Statistics
        self.total_sales: int = 0
        self.total_revenue: float = 0.0
        self.action_counts: Dict[str, int] = {}

        # Last recorded net worth for change calculation
        self.last_net_worth: float = self.starting_net_worth

    def _calculate_current_net_worth(self) -> float:
        """Calculate current net worth."""
        return calculate_net_worth(
            self.current_machine_cash,
            self.current_operator_cash,
            self.current_inventory,
            DEFAULT_COSTS,
        )

    def _record_action(self, action_type: str):
        """Record an action in statistics."""
        self.action_counts[action_type] = self.action_counts.get(action_type, 0) + 1

    def _create_net_worth_report(self, day: int) -> NetWorthReport:
        """Create a net worth report for the given day."""
        current_nw = self._calculate_current_net_worth()
        inventory_value = sum(qty * DEFAULT_COSTS.get(p, 0) for p, qty in self.current_inventory.items())

        report = NetWorthReport(
            day=day,
            machine_cash=self.current_machine_cash,
            operator_cash=self.current_operator_cash,
            inventory_value=inventory_value,
            net_worth=current_nw,
            change_from_previous=current_nw - self.last_net_worth,
        )

        self.last_net_worth = current_nw
        return report

    def _create_evaluation_result(self, status: SimulationStatus) -> EvaluationResult:
        """Create final evaluation result."""
        final_nw = self._calculate_current_net_worth()

        result = EvaluationResult(
            final_day=self.current_day,
            final_net_worth=final_nw,
            starting_net_worth=self.starting_net_worth,
            net_worth_change=final_nw - self.starting_net_worth,
            total_sales=self.total_sales,
            total_revenue=self.total_revenue,
            daily_net_worth_history=self.daily_net_worth,
            action_counts=self.action_counts,
            simulation_status=status,
            bankrupt=status == SimulationStatus.BANKRUPT,
            days_survived=self.current_day,
            success_message=self._generate_success_message(status, final_nw),
        )

        return result

    def _generate_success_message(self, status: SimulationStatus, final_nw: float) -> str:
        """Generate a human-readable success message."""
        if status == SimulationStatus.BANKRUPT:
            return f"Simulation ended: BANKRUPT after {self.current_day} days. Final net worth: ${final_nw:.2f}"
        elif status == SimulationStatus.COMPLETED:
            profit = final_nw - self.starting_net_worth
            if profit > 0:
                return (
                    f"Simulation completed successfully! Survived {self.current_day} days "
                    f"with ${profit:.2f} profit. Final net worth: ${final_nw:.2f}"
                )
            else:
                return (
                    f"Simulation completed. Survived {self.current_day} days "
                    f"with ${profit:.2f} loss. Final net worth: ${final_nw:.2f}"
                )
        else:
            return f"Simulation status: {status.value}. Day {self.current_day}, net worth: ${final_nw:.2f}"

    @agent.processor(DayUpdateEvent)
    def handle_day_update(self, ctx: ProcessContext[DayUpdateEvent]):
        """Record state at the start of each day."""
        event = ctx.payload
        self.current_day = event.day

        # Update cash from event
        # Note: remaining_cash includes both operator and machine cash
        # We'll get detailed breakdown from balance responses

        logger.debug(f"Evaluator: Day {event.day}, remaining cash: ${event.remaining_cash:.2f}")

    @agent.processor(NightUpdateEvent)
    def handle_night_update(self, ctx: ProcessContext[NightUpdateEvent]):
        """Record daily summary at end of business day."""
        event = ctx.payload

        # Update inventory
        self.current_inventory = event.ending_inventory

        # Create and store daily report
        if self.config.emit_daily_reports:
            report = self._create_net_worth_report(event.day)
            self.daily_net_worth.append(report)
            ctx.send(report)

            logger.info(
                f"Day {event.day} summary: Sales={event.total_sales_today}, "
                f"Revenue=${event.total_revenue_today:.2f}, Net Worth=${report.net_worth:.2f}"
            )

    @agent.processor(CustomerPurchaseEvent)
    def handle_purchase(self, ctx: ProcessContext[CustomerPurchaseEvent]):
        """Track purchase statistics."""
        purchase = ctx.payload
        self.total_sales += purchase.quantity
        self.total_revenue += purchase.price_paid * purchase.quantity

    @agent.processor(CheckBalanceResponse)
    def handle_balance_update(self, ctx: ProcessContext[CheckBalanceResponse]):
        """Update cash tracking from balance responses."""
        response = ctx.payload
        self.current_machine_cash = response.machine_cash
        self.current_operator_cash = response.operator_cash
        self._record_action("check_balance")

    @agent.processor(CollectCashResponse)
    def handle_collect_cash(self, ctx: ProcessContext[CollectCashResponse]):
        """Update cash tracking after collection."""
        response = ctx.payload
        self.current_machine_cash = response.new_machine_balance
        self.current_operator_cash = response.new_operator_balance
        self._record_action("collect_cash")

    @agent.processor(SetPriceResponse)
    def handle_price_change(self, ctx: ProcessContext[SetPriceResponse]):
        """Track price change actions."""
        self._record_action("set_price")

    @agent.processor(RestockResponse)
    def handle_restock(self, ctx: ProcessContext[RestockResponse]):
        """Track restock actions and update inventory."""
        response = ctx.payload
        if response.success:
            for product, quantity in response.products_restocked.items():
                current = self.current_inventory.get(product, 0)
                self.current_inventory[product] = current + quantity
        self._record_action("restock")

    @agent.processor(AgentActionResponse)
    def handle_action_response(self, ctx: ProcessContext[AgentActionResponse]):
        """Track all actions from G2G interface."""
        response = ctx.payload
        self._record_action(response.action_type.value)

    @agent.processor(VendingMachineState)
    def handle_state_update(self, ctx: ProcessContext[VendingMachineState]):
        """Update local state tracking from full state updates."""
        state = ctx.payload
        self.current_machine_cash = state.machine_cash
        self.current_operator_cash = state.operator_cash
        self.current_inventory = state.inventory
        self.total_sales = state.total_sales
        self.total_revenue = state.total_revenue

    @agent.processor(SimulationControlResponse)
    def handle_simulation_end(self, ctx: ProcessContext[SimulationControlResponse]):
        """Handle simulation completion and produce evaluation result."""
        response = ctx.payload

        # Check if simulation ended
        if response.simulation_status in [SimulationStatus.COMPLETED, SimulationStatus.BANKRUPT]:
            # Update state from response
            if response.vending_machine_state:
                state = response.vending_machine_state
                self.current_machine_cash = state.machine_cash
                self.current_operator_cash = state.operator_cash
                self.current_inventory = state.inventory
                self.total_sales = state.total_sales
                self.total_revenue = state.total_revenue

            # Create and send evaluation result
            result = self._create_evaluation_result(response.simulation_status)
            ctx.send(result)

            logger.info(f"Evaluation complete: {result.success_message}")
