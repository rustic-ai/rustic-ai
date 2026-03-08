"""
VendingBench Status Tracker Agent - Tracks simulation metrics and displays UI visualizations.

This agent:
- Tracks net worth over time and displays a line chart
- Tracks inventory levels over time and displays a multi-line chart
- Displays email activity in a table
- Shows a summary status overview
"""

import logging
from typing import Any, Dict, List, Optional

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.core.ui_protocol.types import TableFormat, TextFormat, VegaLiteFormat
from rustic_ai.showcase.vending_bench.messages import (
    CheckBalanceResponse,
    CheckInventoryResponse,
    CustomerPurchaseEvent,
    DayUpdateEvent,
    NightUpdateEvent,
    ReadEmailsResponse,
    SendEmailResponse,
    SimulationControlResponse,
    SimulationStatus,
)
from rustic_ai.showcase.vending_bench.state_keys import (
    CURRENT_DAY,
    CURRENT_TIME_MINUTES,
    TRACKER_CASH_BREAKDOWN_HISTORY,
    TRACKER_CURRENT_DAY,
    TRACKER_CURRENT_DAY_REVENUE,
    TRACKER_CURRENT_DAY_SALES,
    TRACKER_CURRENT_NET_WORTH,
    TRACKER_DAILY_SALES,
    TRACKER_EMAILS_RECEIVED,
    TRACKER_EMAILS_SENT,
    TRACKER_INVENTORY_HISTORY,
    TRACKER_NET_WORTH_HISTORY,
    TRACKER_TOTAL_REVENUE,
    TRACKER_TOTAL_SALES,
)

logger = logging.getLogger(__name__)


class VendingBenchStatusTrackerProps(BaseAgentProps):
    """Configuration properties for VendingBenchStatusTrackerAgent."""

    pass


class VendingBenchStatusTrackerAgent(Agent[VendingBenchStatusTrackerProps]):
    """Agent that tracks simulation metrics and sends UI visualizations.

    Listens to simulation events and generates:
    - Net worth progression chart (line chart)
    - Inventory levels over time chart (multi-line chart)
    - Email activity table
    - Summary status overview
    """

    def __init__(self):
        # Track net worth history for charting
        self.net_worth_history: List[Dict[str, Any]] = []

        # Track cash breakdown history (machine_cash, operator_cash, inventory_value)
        self.cash_breakdown_history: List[Dict[str, Any]] = []

        # Track inventory history
        self.inventory_history: List[Dict[str, Any]] = []

        # Track emails
        self.emails_sent: List[Dict[str, Any]] = []
        self.emails_received: List[Dict[str, Any]] = []

        # Track sales
        self.daily_sales: List[Dict[str, Any]] = []
        self.total_sales: int = 0
        self.total_revenue: float = 0.0
        self.current_day_sales: int = 0
        self.current_day_revenue: float = 0.0

        # Current state
        self.current_day: int = 1
        self.current_net_worth: float = 500.0
        self.simulation_status: SimulationStatus = SimulationStatus.PAUSED

        # Flag to track if initial state has been loaded from guild
        # This prevents overwriting in-memory data with stale guild state
        # due to async state update race conditions
        self._state_initialized: bool = False

    def _load_state_from_guild(self):
        """Load persisted state from guild state.

        This only loads from guild state once (for session recovery).
        After the first load, we rely on in-memory data to avoid race conditions
        where async state updates haven't been received yet.
        """
        if self._state_initialized:
            return

        guild_state = self.get_guild_state() or {}

        # Only load if guild state has tracker data (indicates a resumed session)
        if guild_state.get(TRACKER_NET_WORTH_HISTORY) is not None:
            self.net_worth_history = guild_state.get(TRACKER_NET_WORTH_HISTORY, [])
            self.cash_breakdown_history = guild_state.get(TRACKER_CASH_BREAKDOWN_HISTORY, [])
            self.inventory_history = guild_state.get(TRACKER_INVENTORY_HISTORY, [])
            self.emails_sent = guild_state.get(TRACKER_EMAILS_SENT, [])
            self.emails_received = guild_state.get(TRACKER_EMAILS_RECEIVED, [])
            self.daily_sales = guild_state.get(TRACKER_DAILY_SALES, [])
            self.total_sales = guild_state.get(TRACKER_TOTAL_SALES, 0)
            self.total_revenue = guild_state.get(TRACKER_TOTAL_REVENUE, 0.0)
            self.current_day_sales = guild_state.get(TRACKER_CURRENT_DAY_SALES, 0)
            self.current_day_revenue = guild_state.get(TRACKER_CURRENT_DAY_REVENUE, 0.0)
            self.current_day = guild_state.get(TRACKER_CURRENT_DAY, 1)
            self.current_net_worth = guild_state.get(TRACKER_CURRENT_NET_WORTH, 500.0)

        self._state_initialized = True

    def _persist_state(self, ctx: ProcessContext):
        """Persist current state to guild state."""
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                TRACKER_NET_WORTH_HISTORY: self.net_worth_history,
                TRACKER_CASH_BREAKDOWN_HISTORY: self.cash_breakdown_history,
                TRACKER_INVENTORY_HISTORY: self.inventory_history,
                TRACKER_EMAILS_SENT: self.emails_sent,
                TRACKER_EMAILS_RECEIVED: self.emails_received,
                TRACKER_DAILY_SALES: self.daily_sales,
                TRACKER_TOTAL_SALES: self.total_sales,
                TRACKER_TOTAL_REVENUE: self.total_revenue,
                TRACKER_CURRENT_DAY_SALES: self.current_day_sales,
                TRACKER_CURRENT_DAY_REVENUE: self.current_day_revenue,
                TRACKER_CURRENT_DAY: self.current_day,
                TRACKER_CURRENT_NET_WORTH: self.current_net_worth,
            },
        )

    def _generate_summary_update(self) -> TextFormat:
        """Generate the status overview markdown."""
        summary_content = f"""<table>
<tr><td><b>Current Day</b></td><td>{self.current_day}</td></tr>
<tr><td><b>Status</b></td><td>{self.simulation_status.value}</td></tr>
<tr><td><b>Net Worth</b></td><td>${self.current_net_worth:.2f}</td></tr>
<tr><td><b>Total Sales</b></td><td>{self.total_sales} items</td></tr>
<tr><td><b>Total Revenue</b></td><td>${self.total_revenue:.2f}</td></tr>
<tr><td><b>Emails Sent</b></td><td>{len(self.emails_sent)}</td></tr>
<tr><td><b>Emails Received</b></td><td>{len(self.emails_received)}</td></tr>
</table>"""
        return TextFormat(
            title="Status Overview",
            update_id="vb_status_overview",
            update_type="replace",
            text=summary_content,
        )

    def _generate_net_worth_chart(self) -> VegaLiteFormat:
        """Generate the net worth progression line chart (hourly tracking)."""
        # Add a continuous time index for proper x-axis ordering across days
        chart_data = []
        for entry in self.net_worth_history:
            day = entry.get("day", 1)
            hour = entry.get("hour", 8)
            # Use 24-hour day boundary to ensure monotonic time_index even when
            # simulation hours exceed the typical 12-hour business day (hours 8-20)
            time_index = (day - 1) * 24 + (hour - 8)
            chart_data.append({
                **entry,
                "time_index": time_index,
                "time_label": f"D{day} H{hour}",
            })

        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"values": chart_data},
            "width": 400,
            "height": 200,
            "mark": {"type": "line", "point": True, "interpolate": "monotone"},
            "encoding": {
                "x": {
                    "field": "time_index",
                    "type": "quantitative",
                    "title": "Time (Day/Hour)",
                    "axis": {"grid": True, "tickMinStep": 1},
                },
                "y": {
                    "field": "net_worth",
                    "type": "quantitative",
                    "title": "Net Worth ($)",
                    "axis": {"grid": True},
                },
                "color": {"value": "#4caf50"},
                "tooltip": [
                    {"field": "day", "type": "quantitative", "title": "Day"},
                    {"field": "hour", "type": "quantitative", "title": "Hour"},
                    {"field": "net_worth", "type": "quantitative", "title": "Net Worth ($)", "format": "$.2f"},
                    {"field": "revenue", "type": "quantitative", "title": "Revenue ($)", "format": "$.2f"},
                ],
            },
            "config": {
                "axis": {"labelFontSize": 12, "titleFontSize": 14},
                "view": {"stroke": "transparent"},
                "mark": {"line": {"strokeWidth": 2}},
            },
        }
        return VegaLiteFormat(
            title="Net Worth Over Time",
            update_id="vb_net_worth_chart",
            update_type="replace",
            spec=spec,
            theme={"light": "quartz"}
        )

    def _generate_cash_breakdown_chart(self) -> VegaLiteFormat:
        """Generate the cash breakdown chart showing machine_cash, operator_cash, and inventory_value over time."""
        # Transform cash_breakdown_history to flat format for multi-line chart
        chart_data = []
        for entry in self.cash_breakdown_history:
            day = entry.get("day", 1)
            hour = entry.get("hour", 8)
            # Use 24-hour day boundary to ensure monotonic time_index
            time_index = (day - 1) * 24 + (hour - 8)
            time_label = f"D{day} H{hour}"

            # Add separate data points for each component
            chart_data.append({
                "time_index": time_index,
                "time_label": time_label,
                "component": "Machine Cash",
                "value": entry.get("machine_cash", 0),
            })
            chart_data.append({
                "time_index": time_index,
                "time_label": time_label,
                "component": "Operator Cash",
                "value": entry.get("operator_cash", 0),
            })
            chart_data.append({
                "time_index": time_index,
                "time_label": time_label,
                "component": "Inventory Value",
                "value": entry.get("inventory_value", 0),
            })

        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"values": chart_data},
            "width": 400,
            "height": 200,
            "mark": {"type": "line", "point": True, "interpolate": "monotone"},
            "encoding": {
                "x": {
                    "field": "time_index",
                    "type": "quantitative",
                    "title": "Time (Day/Hour)",
                    "axis": {"grid": True, "tickMinStep": 1},
                },
                "y": {
                    "field": "value",
                    "type": "quantitative",
                    "title": "Amount ($)",
                    "axis": {"grid": True},
                },
                "color": {
                    "field": "component",
                    "type": "nominal",
                    "title": "Component",
                    "scale": {
                        "domain": ["Machine Cash", "Operator Cash", "Inventory Value"],
                        "range": ["#4caf50", "#2196f3", "#ff9800"],
                    },
                },
                "tooltip": [
                    {"field": "component", "type": "nominal", "title": "Component"},
                    {"field": "value", "type": "quantitative", "title": "Amount ($)", "format": "$.2f"},
                    {"field": "time_label", "type": "nominal", "title": "Time"},
                ],
            },
            "config": {
                "axis": {"labelFontSize": 12, "titleFontSize": 14},
                "view": {"stroke": "transparent"},
                "mark": {"line": {"strokeWidth": 2}},
            },
        }
        return VegaLiteFormat(
            title="Cash Breakdown Over Time",
            update_id="vb_cash_breakdown_chart",
            update_type="replace",
            spec=spec,
            theme={"light": "quartz"}
        )

    def _generate_inventory_line_chart(self) -> VegaLiteFormat:
        """Generate the inventory levels line chart showing quantity changes over time."""
        # Transform inventory_history to flat format for multi-line chart
        chart_data = []
        for idx, snapshot in enumerate(self.inventory_history):
            day = snapshot.get("day", 1)
            time_minutes = snapshot.get("time", 0)
            hour = 8 + (time_minutes // 60)
            # Use 24-hour day boundary to ensure monotonic time_index even when
            # simulation hours exceed the typical 12-hour business day (hours 8-20)
            time_index = (day - 1) * 24 + (hour - 8)
            inventory = snapshot.get("inventory", {})
            for product, quantity in inventory.items():
                product_name = product.replace("_", " ").title()
                chart_data.append({
                    "time_index": time_index,
                    "time_label": f"D{day} H{hour}",
                    "product": product_name,
                    "quantity": quantity,
                })

        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"values": chart_data},
            "width": 400,
            "height": 200,
            "mark": {"type": "line", "point": True, "interpolate": "monotone"},
            "encoding": {
                "x": {
                    "field": "time_index",
                    "type": "quantitative",
                    "title": "Time (Day/Hour)",
                    "axis": {"grid": True, "tickMinStep": 1},
                },
                "y": {
                    "field": "quantity",
                    "type": "quantitative",
                    "title": "Quantity",
                    "axis": {"grid": True},
                },
                "color": {
                    "field": "product",
                    "type": "nominal",
                    "title": "Product",
                    "scale": {
                        "domain": ["Chips", "Candy", "Soda", "Water", "Energy Drink"],
                        "range": ["#ff9800", "#e91e63", "#2196f3", "#00bcd4", "#9c27b0"],
                    },
                },
                "tooltip": [
                    {"field": "product", "type": "nominal", "title": "Product"},
                    {"field": "quantity", "type": "quantitative", "title": "Quantity"},
                    {"field": "time_label", "type": "nominal", "title": "Time"},
                ],
            },
            "config": {
                "axis": {"labelFontSize": 12, "titleFontSize": 14},
                "view": {"stroke": "transparent"},
                "mark": {"line": {"strokeWidth": 2}},
            },
        }
        return VegaLiteFormat(
            title="Inventory Over Time",
            update_id="vb_inventory_chart",
            update_type="replace",
            spec=spec,
            theme={"light": "quartz"}
        )

    def _generate_email_table(self) -> Optional[TableFormat]:
        """Generate the email activity table. Returns None if no emails exist."""
        # Return None if no emails to display
        if not self.emails_sent and not self.emails_received:
            return None

        # Combine sent and received emails
        all_emails = []

        for email in self.emails_sent[-10:]:  # Last 10 sent emails
            all_emails.append({
                "direction": "Sent",
                "day": email.get("day", "?"),
                "to_from": email.get("to_address", "Unknown"),
                "subject": email.get("subject", "No subject")[:50],
            })

        for email in self.emails_received[-10:]:  # Last 10 received emails
            all_emails.append({
                "direction": "Received",
                "day": email.get("day", "?"),
                "to_from": email.get("from_address", "Unknown"),
                "subject": email.get("subject", "No subject")[:50],
            })

        # Sort by day (descending)
        all_emails.sort(key=lambda x: x.get("day", 0), reverse=True)

        headers = [
            {"dataKey": "direction", "label": "Type"},
            {"dataKey": "day", "label": "Day"},
            {"dataKey": "to_from", "label": "To/From"},
            {"dataKey": "subject", "label": "Subject"},
        ]

        return TableFormat(
            title=f"Email Activity ({len(self.emails_sent)} sent, {len(self.emails_received)} received)",
            update_id="vb_email_table",
            update_type="replace",
            data=all_emails[:15],  # Show last 15 emails
            headers=headers,
        )

    def _generate_sales_chart(self) -> VegaLiteFormat:
        """Generate daily sales chart."""
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"values": self.daily_sales},
            "width": 400,
            "height": 200,
            "layer": [
                {
                    "mark": {"type": "bar", "opacity": 0.7},
                    "encoding": {
                        "x": {
                            "field": "day",
                            "type": "ordinal",
                            "title": "Day",
                        },
                        "y": {
                            "field": "sales",
                            "type": "quantitative",
                            "title": "Units Sold",
                            "axis": {"titleColor": "#2196f3"},
                        },
                        "color": {"value": "#2196f3"},
                    },
                },
                {
                    "mark": {"type": "line", "point": True, "color": "#4caf50"},
                    "encoding": {
                        "x": {"field": "day", "type": "ordinal"},
                        "y": {
                            "field": "revenue",
                            "type": "quantitative",
                            "title": "Revenue ($)",
                            "axis": {"titleColor": "#4caf50"},
                        },
                    },
                },
            ],
            "resolve": {"scale": {"y": "independent"}},
            "config": {"view": {"stroke": "transparent"}},
        }
        return VegaLiteFormat(
            title="Daily Sales & Revenue",
            update_id="vb_sales_chart",
            update_type="replace",
            spec=spec,
            theme={"light": "quartz"}
        )

    def _track_net_worth(self, day: int, hour: int, net_worth: float, revenue: float):
        """Track net worth entry if not already tracked for this day/hour."""
        for entry in self.net_worth_history:
            if entry.get("day") == day and entry.get("hour") == hour:
                return
        self.net_worth_history.append({
            "day": day,
            "hour": hour,
            "net_worth": net_worth,
            "revenue": revenue,
        })
        self.net_worth_history.sort(key=lambda x: (x.get("day", 0), x.get("hour", 0)))

    def _track_cash_breakdown(
        self, day: int, hour: int, machine_cash: float, operator_cash: float, inventory_value: float
    ):
        """Track cash breakdown entry if not already tracked for this day/hour."""
        for entry in self.cash_breakdown_history:
            if entry.get("day") == day and entry.get("hour") == hour:
                # Update existing entry with latest values
                entry["machine_cash"] = machine_cash
                entry["operator_cash"] = operator_cash
                entry["inventory_value"] = inventory_value
                return
        self.cash_breakdown_history.append({
            "day": day,
            "hour": hour,
            "machine_cash": machine_cash,
            "operator_cash": operator_cash,
            "inventory_value": inventory_value,
        })
        self.cash_breakdown_history.sort(key=lambda x: (x.get("day", 0), x.get("hour", 0)))

    @agent.processor(SimulationControlResponse)
    def handle_simulation_control(self, ctx: ProcessContext[SimulationControlResponse]):
        """Handle simulation control responses to track status."""
        self._load_state_from_guild()

        response = ctx.payload
        self.simulation_status = response.simulation_status

        if response.simulation_time:
            self.current_day = response.simulation_time.current_day

        if response.vending_machine_state:
            state = response.vending_machine_state
            # Calculate net worth
            inventory_value = sum(
                qty * 0.75 for qty in state.inventory.values()  # Approximate cost
            )
            self.current_net_worth = state.machine_cash + state.operator_cash + inventory_value

            # Reset all tracking data when starting a new simulation
            if response.command.value == "start":
                self.net_worth_history = [{"day": 1, "hour": 8, "net_worth": self.current_net_worth, "revenue": 0}]
                # Initialize cash_breakdown_history with starting values
                self.cash_breakdown_history = [{
                    "day": 1,
                    "hour": 8,
                    "machine_cash": state.machine_cash,
                    "operator_cash": state.operator_cash,
                    "inventory_value": inventory_value,
                }]
                # Initialize inventory_history with starting inventory snapshot
                self.inventory_history = [{
                    "day": 1,
                    "time": 0,
                    "inventory": {k.value: v for k, v in state.inventory.items()},
                }]
                self.daily_sales = []
                self.emails_sent = []
                self.emails_received = []
                self.total_sales = 0
                self.total_revenue = 0.0
                self.current_day_sales = 0
                self.current_day_revenue = 0.0
                # Mark state as initialized since we just reset it
                self._state_initialized = True

        self._persist_state(ctx)

        # Send UI updates
        ctx.send(self._generate_summary_update())
        if self.net_worth_history:
            ctx.send(self._generate_net_worth_chart())
        if self.cash_breakdown_history:
            ctx.send(self._generate_cash_breakdown_chart())
        if self.inventory_history:
            ctx.send(self._generate_inventory_line_chart())

    @agent.processor(DayUpdateEvent)
    def handle_day_update(self, ctx: ProcessContext[DayUpdateEvent]):
        """Handle day start events."""
        self._load_state_from_guild()

        event = ctx.payload
        self.current_day = event.day

        # Track net worth at day start (hour 8)
        self._track_net_worth(event.day, 8, self.current_net_worth, self.total_revenue)

        self._persist_state(ctx)

        # Send UI updates
        ctx.send(self._generate_summary_update())
        if self.net_worth_history:
            ctx.send(self._generate_net_worth_chart())

    @agent.processor(NightUpdateEvent)
    def handle_night_update(self, ctx: ProcessContext[NightUpdateEvent]):
        """Handle day end events - update net worth and sales charts."""
        self._load_state_from_guild()

        event = ctx.payload

        # Calculate inventory value (approximate)
        inventory_value = sum(qty * 0.75 for qty in event.ending_inventory.values())

        # Calculate net worth at end of day
        end_of_day_net_worth = event.operator_cash + event.machine_cash + inventory_value
        self.current_net_worth = end_of_day_net_worth

        # Track net worth at hour 20 (day end)
        self._track_net_worth(event.day, 20, end_of_day_net_worth, self.total_revenue)

        # Track cash breakdown at end of day
        self._track_cash_breakdown(
            day=event.day,
            hour=20,
            machine_cash=event.machine_cash,
            operator_cash=event.operator_cash,
            inventory_value=inventory_value,
        )

        # Add daily sales data (use current_day counters which track real-time purchases)
        self.daily_sales.append({
            "day": event.day,
            "sales": self.current_day_sales,
            "revenue": self.current_day_revenue,
        })

        # Reset day counters for next day
        self.current_day_sales = 0
        self.current_day_revenue = 0.0

        self._persist_state(ctx)

        # Send UI updates
        ctx.send(self._generate_summary_update())
        if self.net_worth_history:
            ctx.send(self._generate_net_worth_chart())
        if self.cash_breakdown_history:
            ctx.send(self._generate_cash_breakdown_chart())
        if len(self.daily_sales) > 0:
            ctx.send(self._generate_sales_chart())

    @agent.processor(CheckBalanceResponse)
    def handle_balance_response(self, ctx: ProcessContext[CheckBalanceResponse]):
        """Handle balance checks to update net worth (hourly tracking)."""
        self._load_state_from_guild()

        response = ctx.payload
        self.current_net_worth = response.net_worth

        # Read current time from guild state (updated by simulation controller)
        # This is more reliable than the time in the response, which may be stale
        guild_state = self.get_guild_state() or {}
        self.current_day = guild_state.get(CURRENT_DAY, response.simulation_time.current_day)
        current_time_minutes = guild_state.get(
            CURRENT_TIME_MINUTES, response.simulation_time.current_time_minutes
        )
        # Convert to hour (simulation time: 0 = 8 AM, so hour = 8 + minutes/60)
        current_hour = 8 + (current_time_minutes // 60)

        # Check if this data point already exists (check ALL entries, not just last)
        # This handles race conditions where guild state might be stale
        # If entry exists, update it with latest values; otherwise add new entry
        entry_exists = False
        for entry in self.net_worth_history:
            if entry.get("day") == self.current_day and entry.get("hour") == current_hour:
                # Update existing entry with latest values
                entry["net_worth"] = self.current_net_worth
                entry["revenue"] = self.total_revenue
                entry_exists = True
                break

        if not entry_exists:
            self.net_worth_history.append({
                "day": self.current_day,
                "hour": current_hour,
                "net_worth": self.current_net_worth,
                "revenue": self.total_revenue,
            })
            # Sort by day and hour to ensure proper ordering after potential out-of-order appends
            self.net_worth_history.sort(key=lambda x: (x.get("day", 0), x.get("hour", 0)))

        # Track cash breakdown (machine_cash, operator_cash, inventory_value)
        self._track_cash_breakdown(
            day=self.current_day,
            hour=current_hour,
            machine_cash=response.machine_cash,
            operator_cash=response.operator_cash,
            inventory_value=response.inventory_value,
        )

        self._persist_state(ctx)

        # Send UI updates
        ctx.send(self._generate_summary_update())
        ctx.send(self._generate_net_worth_chart())
        ctx.send(self._generate_cash_breakdown_chart())

    @agent.processor(CheckInventoryResponse)
    def handle_inventory_response(self, ctx: ProcessContext[CheckInventoryResponse]):
        """Handle inventory checks to update inventory chart."""
        self._load_state_from_guild()

        response = ctx.payload

        # Read current time from guild state (updated by simulation controller)
        # This is more reliable than the time in the response, which may be stale
        guild_state = self.get_guild_state() or {}
        self.current_day = guild_state.get(CURRENT_DAY, response.simulation_time.current_day)
        current_time_minutes = guild_state.get(
            CURRENT_TIME_MINUTES, response.simulation_time.current_time_minutes
        )
        current_hour = 8 + (current_time_minutes // 60)

        # Check if an entry for this day/hour already exists and update it,
        # otherwise add a new entry. This prevents duplicate entries at the same time point.
        entry_exists = False
        for entry in self.inventory_history:
            entry_day = entry.get("day", 1)
            entry_time = entry.get("time", 0)
            entry_hour = 8 + (entry_time // 60)
            if entry_day == self.current_day and entry_hour == current_hour:
                # Update existing entry with latest inventory
                entry["time"] = current_time_minutes
                entry["inventory"] = {k.value: v for k, v in response.inventory.items()}
                entry_exists = True
                break

        if not entry_exists:
            # Store new inventory snapshot
            self.inventory_history.append({
                "day": self.current_day,
                "time": current_time_minutes,
                "inventory": {k.value: v for k, v in response.inventory.items()},
            })
            # Sort by day and time to ensure proper ordering
            self.inventory_history.sort(key=lambda x: (x.get("day", 0), x.get("time", 0)))

        # Keep only last 50 snapshots
        if len(self.inventory_history) > 50:
            self.inventory_history = self.inventory_history[-50:]

        self._persist_state(ctx)

        # Send inventory chart update
        ctx.send(self._generate_inventory_line_chart())

    @agent.processor(SendEmailResponse)
    def handle_send_email_response(self, ctx: ProcessContext[SendEmailResponse]):
        """Handle email sending to track outgoing emails."""
        self._load_state_from_guild()

        response = ctx.payload

        # Track sent email (we don't have full email details here, but we can track it)
        self.emails_sent.append({
            "day": response.simulation_time.current_day,
            "to_address": "supplier@vendingsupply.com",  # Assume supplier
            "subject": "Order Request",
            "success": response.success,
        })

        self._persist_state(ctx)
        email_table = self._generate_email_table()
        if email_table:
            ctx.send(email_table)

    @agent.processor(ReadEmailsResponse)
    def handle_read_emails_response(self, ctx: ProcessContext[ReadEmailsResponse]):
        """Handle email reading to track incoming emails."""
        self._load_state_from_guild()

        response = ctx.payload

        # Track received emails
        for email in response.emails:
            email_data = {
                "day": response.simulation_time.current_day,
                "from_address": email.from_address,
                "to_address": email.to_address,
                "subject": email.subject,
            }
            # Avoid duplicates by checking if email already tracked
            if email_data not in self.emails_received:
                self.emails_received.append(email_data)

        self._persist_state(ctx)
        email_table = self._generate_email_table()
        if email_table:
            ctx.send(email_table)

    @agent.processor(CustomerPurchaseEvent)
    def handle_purchase_event(self, ctx: ProcessContext[CustomerPurchaseEvent]):
        """Handle purchase events to update totals."""
        self._load_state_from_guild()

        event = ctx.payload
        self.total_sales += event.quantity
        self.total_revenue += event.price_paid
        self.current_day_sales += event.quantity
        self.current_day_revenue += event.price_paid

        self._persist_state(ctx)
        # Don't send update for every purchase - let night update handle batch
