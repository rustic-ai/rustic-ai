"""Tests for the VendingBench Status Tracker Agent."""

import pytest

from rustic_ai.core.ui_protocol.types import TableFormat, TextFormat, VegaLiteFormat
from rustic_ai.showcase.vending_bench.messages import SimulationStatus
from rustic_ai.showcase.vending_bench.status_tracker_agent import (
    VendingBenchStatusTrackerAgent,
)


class TestVendingBenchStatusTrackerAgent:
    """Tests for the VendingBenchStatusTrackerAgent."""

    @pytest.fixture
    def agent(self):
        """Create a status tracker agent for testing."""
        agent = VendingBenchStatusTrackerAgent()
        return agent

    def test_generate_summary_update(self, agent):
        """Test generating the summary update."""
        agent.current_day = 5
        agent.current_net_worth = 550.0
        agent.total_sales = 100
        agent.total_revenue = 200.0
        agent.simulation_status = SimulationStatus.RUNNING

        summary = agent._generate_summary_update()

        assert isinstance(summary, TextFormat)
        assert summary.title == "Status Overview"
        assert "Day 5" in summary.text or "5" in summary.text
        assert "550.00" in summary.text
        assert "100" in summary.text
        assert "200.00" in summary.text

    def test_generate_net_worth_chart(self, agent):
        """Test generating the net worth chart (hourly tracking)."""
        agent.net_worth_history = [
            {"day": 1, "hour": 8, "net_worth": 500.0, "revenue": 0},
            {"day": 1, "hour": 10, "net_worth": 510.0, "revenue": 25.0},
            {"day": 1, "hour": 12, "net_worth": 520.0, "revenue": 50.0},
            {"day": 2, "hour": 8, "net_worth": 535.0, "revenue": 85.0},
        ]

        chart = agent._generate_net_worth_chart()

        assert isinstance(chart, VegaLiteFormat)
        assert chart.title == "Net Worth Over Time"
        assert chart.spec is not None
        # Chart data includes time_index for continuous x-axis across days
        chart_data = chart.spec["data"]["values"]
        assert len(chart_data) == 4
        # Verify time_index is calculated correctly: (day-1)*24 + (hour-8)
        assert chart_data[0]["time_index"] == 0  # Day 1, Hour 8: (1-1)*24 + (8-8) = 0
        assert chart_data[1]["time_index"] == 2  # Day 1, Hour 10: (1-1)*24 + (10-8) = 2
        assert chart_data[2]["time_index"] == 4  # Day 1, Hour 12: (1-1)*24 + (12-8) = 4
        assert chart_data[3]["time_index"] == 24  # Day 2, Hour 8: (2-1)*24 + (8-8) = 24
        # Verify the chart uses time_index for x-axis to handle multiple days
        assert chart.spec["encoding"]["x"]["field"] == "time_index"

    def test_generate_inventory_line_chart(self, agent):
        """Test generating the inventory line chart."""
        # Set up inventory history with multiple products
        agent.inventory_history = [
            {
                "day": 1,
                "time": 0,
                "inventory": {
                    "chips": 10,
                    "candy": 15,
                    "soda": 20,
                    "water": 25,
                    "energy_drink": 8,
                },
            }
        ]

        chart = agent._generate_inventory_line_chart()

        assert isinstance(chart, VegaLiteFormat)
        assert chart.title == "Inventory Over Time"
        assert chart.spec is not None
        # One snapshot with 5 products = 5 data entries
        assert len(chart.spec["data"]["values"]) == 5

    def test_generate_email_table(self, agent):
        """Test generating the email table."""
        agent.emails_sent = [
            {"day": 1, "to_address": "supplier@test.com", "subject": "Order"},
        ]
        agent.emails_received = [
            {"day": 1, "from_address": "supplier@test.com", "subject": "Confirmation"},
        ]

        table = agent._generate_email_table()

        assert isinstance(table, TableFormat)
        assert "Email Activity" in table.title
        assert table.data is not None
        assert table.headers is not None
        assert len(table.data) == 2

    def test_generate_sales_chart(self, agent):
        """Test generating the sales chart."""
        agent.daily_sales = [
            {"day": 1, "sales": 10, "revenue": 20.0},
            {"day": 2, "sales": 15, "revenue": 30.0},
        ]

        chart = agent._generate_sales_chart()

        assert isinstance(chart, VegaLiteFormat)
        assert chart.title == "Daily Sales & Revenue"
        assert chart.spec is not None

    def test_net_worth_history_appends_new_time_points(self, agent):
        """Test that net worth history correctly appends entries for different hours."""
        # Start with one entry
        agent.net_worth_history = [
            {"day": 1, "hour": 8, "net_worth": 500.0, "revenue": 0},
        ]

        # Simulate adding entries at different hours
        # This simulates what handle_balance_response would do
        test_data = [
            {"day": 1, "hour": 9, "net_worth": 510.0, "revenue": 10.0},
            {"day": 1, "hour": 10, "net_worth": 520.0, "revenue": 20.0},
            {"day": 1, "hour": 12, "net_worth": 540.0, "revenue": 40.0},
        ]

        for data in test_data:
            entry_exists = False
            for entry in agent.net_worth_history:
                if entry.get("day") == data["day"] and entry.get("hour") == data["hour"]:
                    entry["net_worth"] = data["net_worth"]
                    entry["revenue"] = data["revenue"]
                    entry_exists = True
                    break
            if not entry_exists:
                agent.net_worth_history.append(data)
                agent.net_worth_history.sort(key=lambda x: (x.get("day", 0), x.get("hour", 0)))

        # Verify all entries are present
        assert len(agent.net_worth_history) == 4
        # Verify they are sorted by day and hour
        hours = [e["hour"] for e in agent.net_worth_history]
        assert hours == [8, 9, 10, 12]

        # Generate chart and verify time_index values
        chart = agent._generate_net_worth_chart()
        chart_data = chart.spec["data"]["values"]
        assert len(chart_data) == 4
        # time_index = (day-1)*24 + (hour-8)
        assert chart_data[0]["time_index"] == 0   # Hour 8
        assert chart_data[1]["time_index"] == 1   # Hour 9
        assert chart_data[2]["time_index"] == 2   # Hour 10
        assert chart_data[3]["time_index"] == 4   # Hour 12

    def test_net_worth_history_updates_existing_entries(self, agent):
        """Test that net worth history updates existing entries for the same hour."""
        # Start with entries
        agent.net_worth_history = [
            {"day": 1, "hour": 8, "net_worth": 500.0, "revenue": 0},
            {"day": 1, "hour": 9, "net_worth": 510.0, "revenue": 10.0},
        ]

        # Try to add another entry for hour 9 (should update, not duplicate)
        new_data = {"day": 1, "hour": 9, "net_worth": 515.0, "revenue": 15.0}

        entry_exists = False
        for entry in agent.net_worth_history:
            if entry.get("day") == new_data["day"] and entry.get("hour") == new_data["hour"]:
                entry["net_worth"] = new_data["net_worth"]
                entry["revenue"] = new_data["revenue"]
                entry_exists = True
                break
        if not entry_exists:
            agent.net_worth_history.append(new_data)

        # Should still have only 2 entries
        assert len(agent.net_worth_history) == 2
        # Hour 9 entry should have updated values
        hour_9_entry = next(e for e in agent.net_worth_history if e["hour"] == 9)
        assert hour_9_entry["net_worth"] == 515.0
        assert hour_9_entry["revenue"] == 15.0

    def test_inventory_history_appends_new_time_points(self, agent):
        """Test that inventory history correctly appends entries for different hours."""
        # Start with one entry
        agent.inventory_history = [
            {"day": 1, "time": 0, "inventory": {"chips": 20, "candy": 25}},
        ]

        # Simulate adding entries at different hours
        test_data = [
            {"day": 1, "time": 60, "inventory": {"chips": 18, "candy": 23}},   # Hour 9
            {"day": 1, "time": 120, "inventory": {"chips": 15, "candy": 20}},  # Hour 10
            {"day": 1, "time": 240, "inventory": {"chips": 10, "candy": 15}},  # Hour 12
        ]

        for data in test_data:
            current_hour = 8 + (data["time"] // 60)
            entry_exists = False
            for entry in agent.inventory_history:
                entry_hour = 8 + (entry.get("time", 0) // 60)
                if entry.get("day") == data["day"] and entry_hour == current_hour:
                    entry["time"] = data["time"]
                    entry["inventory"] = data["inventory"]
                    entry_exists = True
                    break
            if not entry_exists:
                agent.inventory_history.append(data)
                agent.inventory_history.sort(key=lambda x: (x.get("day", 0), x.get("time", 0)))

        # Verify all entries are present
        assert len(agent.inventory_history) == 4

        # Generate chart and verify time_index values
        chart = agent._generate_inventory_line_chart()
        chart_data = chart.spec["data"]["values"]

        # Each inventory snapshot creates entries for each product
        # With 2 products and 4 time points, we should have 8 entries
        assert len(chart_data) == 8

        # Get unique time_index values
        time_indices = sorted(set(e["time_index"] for e in chart_data))
        # time_index = (day-1)*24 + (hour-8)
        assert time_indices == [0, 1, 2, 4]  # Hours 8, 9, 10, 12

    def test_inventory_history_updates_existing_entries(self, agent):
        """Test that inventory history updates existing entries for the same hour."""
        # Start with entries
        agent.inventory_history = [
            {"day": 1, "time": 0, "inventory": {"chips": 20, "candy": 25}},    # Hour 8
            {"day": 1, "time": 60, "inventory": {"chips": 18, "candy": 23}},   # Hour 9
        ]

        # Try to add another entry for hour 9 (time=65 is still hour 9)
        new_data = {"day": 1, "time": 65, "inventory": {"chips": 17, "candy": 22}}

        current_hour = 8 + (new_data["time"] // 60)
        entry_exists = False
        for entry in agent.inventory_history:
            entry_hour = 8 + (entry.get("time", 0) // 60)
            if entry.get("day") == new_data["day"] and entry_hour == current_hour:
                entry["time"] = new_data["time"]
                entry["inventory"] = new_data["inventory"]
                entry_exists = True
                break
        if not entry_exists:
            agent.inventory_history.append(new_data)

        # Should still have only 2 entries
        assert len(agent.inventory_history) == 2
        # Hour 9 entry should have updated values
        hour_9_entry = next(e for e in agent.inventory_history if 8 + (e["time"] // 60) == 9)
        assert hour_9_entry["time"] == 65
        assert hour_9_entry["inventory"]["chips"] == 17
        assert hour_9_entry["inventory"]["candy"] == 22

    def test_inventory_line_chart_time_progression_across_days(self, agent):
        """Test that inventory chart correctly handles time progression across multiple days."""
        agent.inventory_history = [
            {"day": 1, "time": 0, "inventory": {"chips": 20}},      # Day 1, Hour 8
            {"day": 1, "time": 240, "inventory": {"chips": 15}},    # Day 1, Hour 12
            {"day": 1, "time": 600, "inventory": {"chips": 10}},    # Day 1, Hour 18
            {"day": 2, "time": 0, "inventory": {"chips": 25}},      # Day 2, Hour 8 (restocked)
            {"day": 2, "time": 120, "inventory": {"chips": 22}},    # Day 2, Hour 10
        ]

        chart = agent._generate_inventory_line_chart()
        chart_data = chart.spec["data"]["values"]

        # Each snapshot has 1 product, so 5 entries
        assert len(chart_data) == 5

        # Verify time_index progression across days
        # time_index = (day-1)*24 + (hour-8)
        time_indices = [e["time_index"] for e in chart_data]
        expected_indices = [
            0,   # Day 1, Hour 8: (1-1)*24 + (8-8) = 0
            4,   # Day 1, Hour 12: (1-1)*24 + (12-8) = 4
            10,  # Day 1, Hour 18: (1-1)*24 + (18-8) = 10
            24,  # Day 2, Hour 8: (2-1)*24 + (8-8) = 24
            26,  # Day 2, Hour 10: (2-1)*24 + (10-8) = 26
        ]
        assert time_indices == expected_indices

    def test_net_worth_chart_time_progression_across_days(self, agent):
        """Test that net worth chart correctly handles time progression across multiple days."""
        agent.net_worth_history = [
            {"day": 1, "hour": 8, "net_worth": 500.0, "revenue": 0},
            {"day": 1, "hour": 12, "net_worth": 520.0, "revenue": 20.0},
            {"day": 1, "hour": 18, "net_worth": 550.0, "revenue": 50.0},
            {"day": 2, "hour": 8, "net_worth": 535.0, "revenue": 50.0},  # After daily fee
            {"day": 2, "hour": 14, "net_worth": 580.0, "revenue": 95.0},
            {"day": 3, "hour": 8, "net_worth": 565.0, "revenue": 95.0},  # After daily fee
        ]

        chart = agent._generate_net_worth_chart()
        chart_data = chart.spec["data"]["values"]

        assert len(chart_data) == 6

        # Verify time_index progression
        # time_index = (day-1)*24 + (hour-8)
        time_indices = [e["time_index"] for e in chart_data]
        expected_indices = [
            0,   # Day 1, Hour 8
            4,   # Day 1, Hour 12
            10,  # Day 1, Hour 18
            24,  # Day 2, Hour 8
            30,  # Day 2, Hour 14
            48,  # Day 3, Hour 8
        ]
        assert time_indices == expected_indices

        # Verify time_label is generated correctly
        time_labels = [e["time_label"] for e in chart_data]
        expected_labels = ["D1 H8", "D1 H12", "D1 H18", "D2 H8", "D2 H14", "D3 H8"]
        assert time_labels == expected_labels

    def test_no_duplicate_entries_on_repeated_same_hour_updates(self, agent):
        """Test that multiple updates at the same hour don't create duplicates."""
        agent.net_worth_history = []
        agent.total_revenue = 0

        # Simulate multiple balance checks at the same hour (hour 8)
        for net_worth in [500.0, 505.0, 510.0, 515.0]:
            agent.current_day = 1
            agent.current_net_worth = net_worth
            agent.total_revenue += 5.0

            current_hour = 8
            entry_exists = False
            for entry in agent.net_worth_history:
                if entry.get("day") == agent.current_day and entry.get("hour") == current_hour:
                    entry["net_worth"] = agent.current_net_worth
                    entry["revenue"] = agent.total_revenue
                    entry_exists = True
                    break
            if not entry_exists:
                agent.net_worth_history.append({
                    "day": agent.current_day,
                    "hour": current_hour,
                    "net_worth": agent.current_net_worth,
                    "revenue": agent.total_revenue,
                })

        # Should only have 1 entry (updated 4 times)
        assert len(agent.net_worth_history) == 1
        # Should have the latest values
        assert agent.net_worth_history[0]["net_worth"] == 515.0
        assert agent.net_worth_history[0]["revenue"] == 20.0

    def test_generate_cash_breakdown_chart(self, agent):
        """Test generating the cash breakdown chart."""
        agent.cash_breakdown_history = [
            {"day": 1, "hour": 8, "machine_cash": 0.0, "operator_cash": 100.0, "inventory_value": 400.0},
            {"day": 1, "hour": 12, "machine_cash": 50.0, "operator_cash": 100.0, "inventory_value": 350.0},
            {"day": 2, "hour": 8, "machine_cash": 0.0, "operator_cash": 150.0, "inventory_value": 350.0},
        ]

        chart = agent._generate_cash_breakdown_chart()

        assert isinstance(chart, VegaLiteFormat)
        assert chart.title == "Cash Breakdown Over Time"
        assert chart.spec is not None

        # Each snapshot creates 3 entries (one per component)
        chart_data = chart.spec["data"]["values"]
        assert len(chart_data) == 9  # 3 snapshots * 3 components

        # Verify time_index is calculated correctly: (day-1)*24 + (hour-8)
        time_indices = sorted(set(e["time_index"] for e in chart_data))
        expected_indices = [0, 4, 24]  # Day 1 Hour 8, Day 1 Hour 12, Day 2 Hour 8
        assert time_indices == expected_indices

        # Verify all three components are present
        components = set(e["component"] for e in chart_data)
        assert components == {"Machine Cash", "Operator Cash", "Inventory Value"}

        # Verify color scale in spec
        color_scale = chart.spec["encoding"]["color"]["scale"]
        assert color_scale["domain"] == ["Machine Cash", "Operator Cash", "Inventory Value"]
        assert len(color_scale["range"]) == 3

    def test_track_cash_breakdown(self, agent):
        """Test the _track_cash_breakdown method."""
        agent.cash_breakdown_history = []

        # Add first entry
        agent._track_cash_breakdown(
            day=1, hour=8, machine_cash=0.0, operator_cash=100.0, inventory_value=400.0
        )
        assert len(agent.cash_breakdown_history) == 1
        assert agent.cash_breakdown_history[0]["machine_cash"] == 0.0

        # Add second entry at different time
        agent._track_cash_breakdown(
            day=1, hour=10, machine_cash=25.0, operator_cash=100.0, inventory_value=375.0
        )
        assert len(agent.cash_breakdown_history) == 2

        # Update existing entry (same day/hour)
        agent._track_cash_breakdown(
            day=1, hour=10, machine_cash=30.0, operator_cash=100.0, inventory_value=370.0
        )
        assert len(agent.cash_breakdown_history) == 2  # Still 2 entries
        # Verify updated values
        entry = next(e for e in agent.cash_breakdown_history if e["hour"] == 10)
        assert entry["machine_cash"] == 30.0
        assert entry["inventory_value"] == 370.0

        # Verify sorted order
        hours = [e["hour"] for e in agent.cash_breakdown_history]
        assert hours == [8, 10]
