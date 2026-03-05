"""
Data models for multi-supplier support in VendingBench.

Includes supplier profiles, behavior types, negotiation state, and registry management.
"""

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.showcase.vending_bench.config import ProductType


class SupplierBehaviorType(str, Enum):
    """Behavior types for suppliers that affect pricing and reliability."""

    HONEST = "honest"  # Fair pricing, reliable delivery
    ADVERSARIAL = "adversarial"  # Price gouging, bait-and-switch tactics
    UNRELIABLE = "unreliable"  # Delays, partial deliveries, may go bankrupt


class SupplierProductInfo(BaseModel):
    """Information about a product offered by a supplier."""

    base_price: float = Field(description="Base wholesale price per unit")
    current_quoted_price: float = Field(description="Current quoted price (may be marked up)")
    min_order_quantity: int = Field(default=10, description="Minimum order quantity")
    in_stock: bool = Field(default=True, description="Whether product is in stock")
    lead_time_days: int = Field(default=3, description="Expected delivery time in days")


class SupplierProfile(BaseModel):
    """Profile of a supplier in the registry."""

    supplier_id: str = Field(default_factory=lambda: f"SUP-{shortuuid.uuid()[:8].upper()}")
    name: str = Field(description="Supplier company name")
    email: str = Field(description="Supplier email address")
    products_offered: Dict[ProductType, SupplierProductInfo] = Field(
        default_factory=dict, description="Products this supplier offers"
    )
    behavior_type: SupplierBehaviorType = Field(
        default=SupplierBehaviorType.HONEST, description="Supplier behavior classification"
    )
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Reliability score from 0 to 1")
    negotiation_flexibility: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Maximum discount from negotiation"
    )
    orders_placed: int = Field(default=0, ge=0, description="Total orders placed with this supplier")
    orders_completed: int = Field(default=0, ge=0, description="Successfully completed orders")
    loyalty_discount: float = Field(default=0.0, ge=0.0, le=0.15, description="Accumulated loyalty discount")
    is_active: bool = Field(default=True, description="Whether supplier is still in business")
    discovered_on_day: int = Field(default=1, description="Day when supplier was discovered")
    location: str = Field(default="", description="Supplier location/region")
    notes: str = Field(default="", description="Additional notes about the supplier")


class NegotiationState(BaseModel):
    """State of an ongoing price negotiation with a supplier."""

    negotiation_id: str = Field(default_factory=lambda: f"NEG-{shortuuid.uuid()[:8].upper()}")
    supplier_id: str = Field(description="ID of the supplier being negotiated with")
    product_type: Optional[ProductType] = Field(
        default=None, description="Specific product being negotiated, or None for all"
    )
    exchange_count: int = Field(default=0, ge=0, description="Number of negotiation exchanges")
    initial_quote: float = Field(description="Initial quoted price")
    current_quote: float = Field(description="Current negotiated price")
    started_on_day: int = Field(description="Day negotiation started")
    is_active: bool = Field(default=True, description="Whether negotiation is still ongoing")
    last_exchange_content: str = Field(default="", description="Content of last exchange")


class PendingSupplierOrder(BaseModel):
    """A pending order with a supplier awaiting delivery."""

    order_id: str = Field(default_factory=lambda: f"ORD-{shortuuid.uuid()[:8].upper()}")
    supplier_id: str = Field(description="ID of the supplier")
    products: Dict[ProductType, int] = Field(description="Products and quantities ordered")
    quoted_total: float = Field(description="Total quoted price at order time")
    actual_total: Optional[float] = Field(
        default=None, description="Actual total charged (may differ for adversarial suppliers)"
    )
    ordered_on_day: int = Field(description="Day order was placed")
    expected_delivery_day: int = Field(description="Expected delivery day")
    is_delayed: bool = Field(default=False, description="Whether delivery is delayed")
    delay_days: int = Field(default=0, description="Additional delay days")
    is_partial: bool = Field(default=False, description="Whether this will be a partial delivery")
    partial_fraction: float = Field(default=1.0, ge=0.0, le=1.0, description="Fraction to be delivered if partial")
    is_delivered: bool = Field(default=False, description="Whether order has been delivered")
    bait_and_switch_applied: bool = Field(default=False, description="Whether bait-and-switch pricing was applied")


class SupplierRegistry(BaseModel):
    """Registry managing all known suppliers and their state."""

    suppliers: Dict[str, SupplierProfile] = Field(default_factory=dict, description="Registered suppliers by ID")
    negotiations: Dict[str, NegotiationState] = Field(default_factory=dict, description="Active negotiations by ID")
    pending_orders: Dict[str, PendingSupplierOrder] = Field(
        default_factory=dict, description="Pending orders by order ID"
    )
    default_supplier_id: Optional[str] = Field(
        default=None, description="ID of the default supplier (VendingSupply Co.)"
    )

    def get_supplier_by_email(self, email: str) -> Optional[SupplierProfile]:
        """Look up a supplier by their email address."""
        email_lower = email.lower()
        for supplier in self.suppliers.values():
            if supplier.email.lower() == email_lower:
                return supplier
        return None

    def get_active_suppliers(self) -> Dict[str, SupplierProfile]:
        """Get all active suppliers."""
        return {sid: s for sid, s in self.suppliers.items() if s.is_active}

    def get_suppliers_for_product(self, product: ProductType) -> Dict[str, SupplierProfile]:
        """Get all active suppliers that offer a specific product."""
        return {sid: s for sid, s in self.suppliers.items() if s.is_active and product in s.products_offered}

    def add_supplier(self, supplier: SupplierProfile) -> None:
        """Add a supplier to the registry."""
        self.suppliers[supplier.supplier_id] = supplier

    def get_pending_orders_for_supplier(self, supplier_id: str) -> Dict[str, PendingSupplierOrder]:
        """Get all pending orders for a specific supplier."""
        return {
            oid: order
            for oid, order in self.pending_orders.items()
            if order.supplier_id == supplier_id and not order.is_delivered
        }

    def mark_supplier_bankrupt(self, supplier_id: str) -> None:
        """Mark a supplier as bankrupt (out of business)."""
        if supplier_id in self.suppliers:
            self.suppliers[supplier_id].is_active = False
