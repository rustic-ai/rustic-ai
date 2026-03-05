"""
Tests for supplier registry data models.
"""

import pytest

from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.supplier_registry import (
    NegotiationState,
    PendingSupplierOrder,
    SupplierBehaviorType,
    SupplierProductInfo,
    SupplierProfile,
    SupplierRegistry,
)


class TestSupplierProductInfo:
    """Tests for SupplierProductInfo model."""

    def test_create_product_info(self):
        """Should create product info with all fields."""
        info = SupplierProductInfo(
            base_price=0.75,
            current_quoted_price=0.95,
            min_order_quantity=10,
            in_stock=True,
            lead_time_days=3,
        )
        assert info.base_price == 0.75
        assert info.current_quoted_price == 0.95
        assert info.min_order_quantity == 10
        assert info.in_stock is True
        assert info.lead_time_days == 3

    def test_product_info_defaults(self):
        """Should use default values when not specified."""
        info = SupplierProductInfo(
            base_price=1.0,
            current_quoted_price=1.2,
        )
        assert info.min_order_quantity == 10
        assert info.in_stock is True
        assert info.lead_time_days == 3


class TestSupplierProfile:
    """Tests for SupplierProfile model."""

    def test_create_supplier_profile(self):
        """Should create supplier profile with all fields."""
        profile = SupplierProfile(
            name="Test Supplier",
            email="test@supplier.com",
            behavior_type=SupplierBehaviorType.HONEST,
            reliability_score=0.95,
        )
        assert profile.name == "Test Supplier"
        assert profile.email == "test@supplier.com"
        assert profile.behavior_type == SupplierBehaviorType.HONEST
        assert profile.reliability_score == 0.95
        assert profile.supplier_id.startswith("SUP-")
        assert profile.is_active is True

    def test_supplier_profile_defaults(self):
        """Should use default values."""
        profile = SupplierProfile(
            name="Default Supplier",
            email="default@supplier.com",
        )
        assert profile.behavior_type == SupplierBehaviorType.HONEST
        assert profile.reliability_score == 1.0
        assert profile.negotiation_flexibility == 0.15
        assert profile.orders_placed == 0
        assert profile.orders_completed == 0
        assert profile.loyalty_discount == 0.0
        assert profile.is_active is True

    def test_supplier_profile_with_products(self):
        """Should store product offerings."""
        products = {
            ProductType.CHIPS: SupplierProductInfo(
                base_price=0.75,
                current_quoted_price=0.90,
            ),
            ProductType.SODA: SupplierProductInfo(
                base_price=0.80,
                current_quoted_price=1.00,
            ),
        }
        profile = SupplierProfile(
            name="Multi Product Supplier",
            email="multi@supplier.com",
            products_offered=products,
        )
        assert len(profile.products_offered) == 2
        assert ProductType.CHIPS in profile.products_offered
        assert ProductType.SODA in profile.products_offered


class TestNegotiationState:
    """Tests for NegotiationState model."""

    def test_create_negotiation_state(self):
        """Should create negotiation state."""
        state = NegotiationState(
            supplier_id="SUP-TEST123",
            initial_quote=1.50,
            current_quote=1.35,
            started_on_day=5,
        )
        assert state.supplier_id == "SUP-TEST123"
        assert state.initial_quote == 1.50
        assert state.current_quote == 1.35
        assert state.started_on_day == 5
        assert state.negotiation_id.startswith("NEG-")
        assert state.is_active is True
        assert state.exchange_count == 0

    def test_negotiation_with_product(self):
        """Should support product-specific negotiation."""
        state = NegotiationState(
            supplier_id="SUP-TEST123",
            product_type=ProductType.ENERGY_DRINK,
            initial_quote=2.50,
            current_quote=2.25,
            started_on_day=10,
        )
        assert state.product_type == ProductType.ENERGY_DRINK


class TestPendingSupplierOrder:
    """Tests for PendingSupplierOrder model."""

    def test_create_pending_order(self):
        """Should create pending order."""
        order = PendingSupplierOrder(
            supplier_id="SUP-TEST123",
            products={ProductType.CHIPS: 20, ProductType.CANDY: 15},
            quoted_total=25.50,
            ordered_on_day=3,
            expected_delivery_day=6,
        )
        assert order.supplier_id == "SUP-TEST123"
        assert order.products[ProductType.CHIPS] == 20
        assert order.products[ProductType.CANDY] == 15
        assert order.quoted_total == 25.50
        assert order.order_id.startswith("ORD-")
        assert order.is_delivered is False
        assert order.is_delayed is False
        assert order.is_partial is False
        assert order.bait_and_switch_applied is False

    def test_pending_order_delayed(self):
        """Should track delayed orders."""
        order = PendingSupplierOrder(
            supplier_id="SUP-TEST123",
            products={ProductType.WATER: 30},
            quoted_total=15.00,
            ordered_on_day=5,
            expected_delivery_day=8,
            is_delayed=True,
            delay_days=2,
        )
        assert order.is_delayed is True
        assert order.delay_days == 2


class TestSupplierRegistry:
    """Tests for SupplierRegistry model."""

    def test_create_empty_registry(self):
        """Should create empty registry."""
        registry = SupplierRegistry()
        assert len(registry.suppliers) == 0
        assert len(registry.negotiations) == 0
        assert len(registry.pending_orders) == 0
        assert registry.default_supplier_id is None

    def test_add_supplier(self):
        """Should add supplier to registry."""
        registry = SupplierRegistry()
        supplier = SupplierProfile(
            name="New Supplier",
            email="new@supplier.com",
        )
        registry.add_supplier(supplier)
        assert supplier.supplier_id in registry.suppliers
        assert registry.suppliers[supplier.supplier_id].name == "New Supplier"

    def test_get_supplier_by_email(self):
        """Should find supplier by email."""
        registry = SupplierRegistry()
        supplier = SupplierProfile(
            name="Email Test Supplier",
            email="find@me.com",
        )
        registry.add_supplier(supplier)

        found = registry.get_supplier_by_email("find@me.com")
        assert found is not None
        assert found.name == "Email Test Supplier"

        # Should be case insensitive
        found_upper = registry.get_supplier_by_email("FIND@ME.COM")
        assert found_upper is not None
        assert found_upper.name == "Email Test Supplier"

        # Should return None for not found
        not_found = registry.get_supplier_by_email("notfound@nowhere.com")
        assert not_found is None

    def test_get_active_suppliers(self):
        """Should return only active suppliers."""
        registry = SupplierRegistry()

        active_supplier = SupplierProfile(
            name="Active Supplier",
            email="active@supplier.com",
            is_active=True,
        )
        inactive_supplier = SupplierProfile(
            name="Inactive Supplier",
            email="inactive@supplier.com",
            is_active=False,
        )

        registry.add_supplier(active_supplier)
        registry.add_supplier(inactive_supplier)

        active = registry.get_active_suppliers()
        assert len(active) == 1
        assert active_supplier.supplier_id in active

    def test_get_suppliers_for_product(self):
        """Should return suppliers offering a specific product."""
        registry = SupplierRegistry()

        chips_supplier = SupplierProfile(
            name="Chips Only",
            email="chips@supplier.com",
            products_offered={
                ProductType.CHIPS: SupplierProductInfo(base_price=0.75, current_quoted_price=0.90),
            },
        )
        soda_supplier = SupplierProfile(
            name="Soda Only",
            email="soda@supplier.com",
            products_offered={
                ProductType.SODA: SupplierProductInfo(base_price=0.80, current_quoted_price=1.00),
            },
        )
        both_supplier = SupplierProfile(
            name="Both Products",
            email="both@supplier.com",
            products_offered={
                ProductType.CHIPS: SupplierProductInfo(base_price=0.75, current_quoted_price=0.85),
                ProductType.SODA: SupplierProductInfo(base_price=0.80, current_quoted_price=0.95),
            },
        )

        registry.add_supplier(chips_supplier)
        registry.add_supplier(soda_supplier)
        registry.add_supplier(both_supplier)

        chips_suppliers = registry.get_suppliers_for_product(ProductType.CHIPS)
        assert len(chips_suppliers) == 2
        assert chips_supplier.supplier_id in chips_suppliers
        assert both_supplier.supplier_id in chips_suppliers

        soda_suppliers = registry.get_suppliers_for_product(ProductType.SODA)
        assert len(soda_suppliers) == 2
        assert soda_supplier.supplier_id in soda_suppliers
        assert both_supplier.supplier_id in soda_suppliers

    def test_get_pending_orders_for_supplier(self):
        """Should return pending orders for a specific supplier."""
        registry = SupplierRegistry()

        order1 = PendingSupplierOrder(
            supplier_id="SUP-A",
            products={ProductType.CHIPS: 10},
            quoted_total=10.00,
            ordered_on_day=1,
            expected_delivery_day=3,
        )
        order2 = PendingSupplierOrder(
            supplier_id="SUP-A",
            products={ProductType.CANDY: 20},
            quoted_total=15.00,
            ordered_on_day=2,
            expected_delivery_day=4,
        )
        order3 = PendingSupplierOrder(
            supplier_id="SUP-B",
            products={ProductType.SODA: 30},
            quoted_total=25.00,
            ordered_on_day=1,
            expected_delivery_day=3,
        )
        delivered_order = PendingSupplierOrder(
            supplier_id="SUP-A",
            products={ProductType.WATER: 40},
            quoted_total=20.00,
            ordered_on_day=1,
            expected_delivery_day=2,
            is_delivered=True,
        )

        registry.pending_orders[order1.order_id] = order1
        registry.pending_orders[order2.order_id] = order2
        registry.pending_orders[order3.order_id] = order3
        registry.pending_orders[delivered_order.order_id] = delivered_order

        sup_a_orders = registry.get_pending_orders_for_supplier("SUP-A")
        assert len(sup_a_orders) == 2
        assert order1.order_id in sup_a_orders
        assert order2.order_id in sup_a_orders
        assert delivered_order.order_id not in sup_a_orders

    def test_mark_supplier_bankrupt(self):
        """Should mark supplier as bankrupt."""
        registry = SupplierRegistry()
        supplier = SupplierProfile(
            name="Soon Bankrupt",
            email="bankrupt@supplier.com",
        )
        registry.add_supplier(supplier)

        assert registry.suppliers[supplier.supplier_id].is_active is True

        registry.mark_supplier_bankrupt(supplier.supplier_id)

        assert registry.suppliers[supplier.supplier_id].is_active is False


class TestBehaviorTypes:
    """Tests for supplier behavior types."""

    def test_all_behavior_types_exist(self):
        """Should have all expected behavior types."""
        assert SupplierBehaviorType.HONEST.value == "honest"
        assert SupplierBehaviorType.ADVERSARIAL.value == "adversarial"
        assert SupplierBehaviorType.UNRELIABLE.value == "unreliable"

    def test_behavior_type_string_conversion(self):
        """Behavior types should be string enums."""
        assert str(SupplierBehaviorType.HONEST) == "SupplierBehaviorType.HONEST"
        assert SupplierBehaviorType.ADVERSARIAL == "adversarial"
