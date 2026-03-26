"""
Tests for VendingBench message types.
"""

import pytest

from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.messages import (
    ActionType,
    AgentActionRequest,
    CheckBalanceRequest,
    CheckBalanceResponse,
    CheckInventoryRequest,
    CheckInventoryResponse,
    CollectCashRequest,
    CustomerPurchaseEvent,
    DayUpdateEvent,
    Email,
    EvaluationResult,
    NetWorthReport,
    NightUpdateEvent,
    ReadEmailsRequest,
    RestockRequest,
    SendEmailRequest,
    SetPriceRequest,
    SimulationControlCommand,
    SimulationControlRequest,
    SimulationControlResponse,
    SimulationStatus,
    SimulationTime,
    VendingMachineState,
    WeatherType,
)


class TestProductType:
    """Tests for ProductType enum."""

    def test_all_products_defined(self):
        """All expected products should be defined."""
        assert len(ProductType) == 5
        assert ProductType.CHIPS.value == "chips"
        assert ProductType.CANDY.value == "candy"
        assert ProductType.SODA.value == "soda"
        assert ProductType.WATER.value == "water"
        assert ProductType.ENERGY_DRINK.value == "energy_drink"


class TestWeatherType:
    """Tests for WeatherType enum."""

    def test_all_weather_types_defined(self):
        """All expected weather types should be defined."""
        assert len(WeatherType) == 5
        assert WeatherType.SUNNY.value == "sunny"
        assert WeatherType.CLOUDY.value == "cloudy"
        assert WeatherType.RAINY.value == "rainy"
        assert WeatherType.HOT.value == "hot"
        assert WeatherType.COLD.value == "cold"


class TestSimulationTime:
    """Tests for SimulationTime model."""

    def test_simulation_time_creation(self, default_simulation_time):
        """SimulationTime should create with valid values."""
        assert default_simulation_time.current_day == 1
        assert default_simulation_time.current_time_minutes == 0
        assert default_simulation_time.is_daytime is True
        assert default_simulation_time.weather == WeatherType.SUNNY
        assert default_simulation_time.day_of_week == 0

    def test_simulation_time_serialization(self, default_simulation_time):
        """SimulationTime should serialize/deserialize correctly."""
        data = default_simulation_time.model_dump()
        restored = SimulationTime(**data)
        assert restored == default_simulation_time


class TestVendingMachineState:
    """Tests for VendingMachineState model."""

    def test_vending_state_creation(self, default_vending_state):
        """VendingMachineState should create with valid values."""
        assert default_vending_state.machine_cash == 0.0
        assert default_vending_state.operator_cash == 500.0
        assert default_vending_state.day == 1
        assert len(default_vending_state.inventory) == 5
        assert len(default_vending_state.prices) == 5

    def test_vending_state_serialization(self, default_vending_state):
        """VendingMachineState should serialize/deserialize correctly."""
        data = default_vending_state.model_dump()
        restored = VendingMachineState(**data)
        assert restored.machine_cash == default_vending_state.machine_cash
        assert restored.operator_cash == default_vending_state.operator_cash


class TestActionRequests:
    """Tests for action request messages."""

    def test_check_inventory_request(self):
        """CheckInventoryRequest should generate unique IDs."""
        req1 = CheckInventoryRequest()
        req2 = CheckInventoryRequest()
        assert req1.request_id != req2.request_id

    def test_check_balance_request(self):
        """CheckBalanceRequest should generate unique IDs."""
        req = CheckBalanceRequest()
        assert req.request_id is not None
        assert len(req.request_id) > 0

    def test_set_price_request(self):
        """SetPriceRequest should validate price."""
        req = SetPriceRequest(product=ProductType.CHIPS, new_price=2.50)
        assert req.product == ProductType.CHIPS
        assert req.new_price == 2.50

    def test_set_price_request_negative_price_fails(self):
        """SetPriceRequest should reject negative prices."""
        with pytest.raises(ValueError):
            SetPriceRequest(product=ProductType.CHIPS, new_price=-1.0)

    def test_collect_cash_request(self):
        """CollectCashRequest should create successfully."""
        req = CollectCashRequest()
        assert req.request_id is not None

    def test_restock_request(self):
        """RestockRequest should accept delivery ID."""
        req = RestockRequest(delivery_id="DEL-123")
        assert req.delivery_id == "DEL-123"


class TestActionResponses:
    """Tests for action response messages."""

    def test_check_inventory_response(self, default_simulation_time):
        """CheckInventoryResponse should contain inventory data."""
        inventory = {ProductType.CHIPS: 20, ProductType.CANDY: 25}
        resp = CheckInventoryResponse(
            request_id="req-1",
            inventory=inventory,
            time_elapsed_minutes=5,
            simulation_time=default_simulation_time,
        )
        assert resp.inventory[ProductType.CHIPS] == 20
        assert resp.time_elapsed_minutes == 5

    def test_check_balance_response(self, default_simulation_time):
        """CheckBalanceResponse should contain all balance info."""
        resp = CheckBalanceResponse(
            request_id="req-1",
            machine_cash=50.0,
            operator_cash=450.0,
            inventory_value=100.0,
            net_worth=600.0,
            time_elapsed_minutes=5,
            simulation_time=default_simulation_time,
        )
        assert resp.net_worth == 600.0
        assert resp.machine_cash + resp.operator_cash + resp.inventory_value == resp.net_worth


class TestEmailMessages:
    """Tests for email-related messages."""

    def test_email_creation(self):
        """Email should create with required fields."""
        email = Email(
            from_address="sender@test.com",
            to_address="receiver@test.com",
            subject="Test Subject",
            body="Test body content",
        )
        assert email.id is not None
        assert email.from_address == "sender@test.com"
        assert email.is_read is False

    def test_read_emails_request(self):
        """ReadEmailsRequest should default to unread only."""
        req = ReadEmailsRequest()
        assert req.unread_only is True

    def test_send_email_request(self):
        """SendEmailRequest should contain email details."""
        req = SendEmailRequest(
            to_address="supplier@test.com",
            subject="Order",
            body="I want to order 20 chips",
        )
        assert req.to_address == "supplier@test.com"


class TestSimulationEvents:
    """Tests for simulation event messages."""

    def test_day_update_event(self, default_simulation_time):
        """DayUpdateEvent should contain day info."""
        event = DayUpdateEvent(
            day=2,
            weather=WeatherType.RAINY,
            day_of_week=1,
            simulation_time=default_simulation_time,
            daily_fee_deducted=2.0,
            remaining_cash=498.0,
            days_without_payment=0,
        )
        assert event.day == 2
        assert event.weather == WeatherType.RAINY
        assert event.daily_fee_deducted == 2.0

    def test_night_update_event(self, default_simulation_time):
        """NightUpdateEvent should contain daily summary."""
        event = NightUpdateEvent(
            day=1,
            total_sales_today=25,
            total_revenue_today=50.0,
            ending_inventory={ProductType.CHIPS: 15},
            machine_cash=75.0,
            operator_cash=200.0,
            simulation_time=default_simulation_time,
        )
        assert event.total_sales_today == 25
        assert event.total_revenue_today == 50.0
        assert event.machine_cash == 75.0
        assert event.operator_cash == 200.0

    def test_customer_purchase_event(self):
        """CustomerPurchaseEvent should contain purchase info."""
        event = CustomerPurchaseEvent(
            product=ProductType.SODA,
            quantity=2,
            price_paid=2.0,
            day=1,
            time_of_day_minutes=300,
        )
        assert event.product == ProductType.SODA
        assert event.quantity == 2


class TestEvaluationMessages:
    """Tests for evaluation-related messages."""

    def test_net_worth_report(self):
        """NetWorthReport should calculate correctly."""
        report = NetWorthReport(
            day=5,
            machine_cash=100.0,
            operator_cash=400.0,
            inventory_value=150.0,
            net_worth=650.0,
            change_from_previous=50.0,
        )
        assert report.net_worth == 650.0
        assert report.change_from_previous == 50.0

    def test_evaluation_result(self):
        """EvaluationResult should contain all metrics."""
        result = EvaluationResult(
            final_day=30,
            final_net_worth=750.0,
            starting_net_worth=500.0,
            net_worth_change=250.0,
            total_sales=500,
            total_revenue=1000.0,
            daily_net_worth_history=[],
            action_counts={"check_inventory": 30},
            simulation_status=SimulationStatus.COMPLETED,
            bankrupt=False,
            days_survived=30,
            success_message="Success!",
        )
        assert result.net_worth_change == 250.0
        assert not result.bankrupt


class TestG2GMessages:
    """Tests for G2G interface messages."""

    def test_agent_action_request(self):
        """AgentActionRequest should contain action type and params."""
        req = AgentActionRequest(
            action_type=ActionType.SET_PRICE,
            parameters={"product": "chips", "new_price": 2.0},
        )
        assert req.action_type == ActionType.SET_PRICE
        assert req.parameters["product"] == "chips"

    def test_simulation_control_request(self):
        """SimulationControlRequest should contain command."""
        req = SimulationControlRequest(command=SimulationControlCommand.START)
        assert req.command == SimulationControlCommand.START

    def test_simulation_control_response(self, default_simulation_time):
        """SimulationControlResponse should contain status."""
        resp = SimulationControlResponse(
            request_id="req-1",
            command=SimulationControlCommand.START,
            success=True,
            message="Simulation started",
            simulation_status=SimulationStatus.RUNNING,
            simulation_time=default_simulation_time,
        )
        assert resp.simulation_status == SimulationStatus.RUNNING
