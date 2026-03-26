"""
Message types for realistic supplier simulation.

Includes supplier discovery, supply chain events, and customer complaints.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, SerializationInfo, field_serializer
import shortuuid

from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.supplier_registry import SupplierProfile

# =============================================================================
# Supplier Discovery Messages
# =============================================================================


class SupplierSearchRequest(BaseModel):
    """Request to search for new suppliers."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    product_types: List[ProductType] = Field(default_factory=list, description="Product types to search suppliers for")
    location: str = Field(default="", description="Location to search near")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum suppliers to return")


class SupplierSearchResponse(BaseModel):
    """Response with discovered suppliers."""

    request_id: str
    suppliers_found: List[SupplierProfile] = Field(default_factory=list, description="List of discovered suppliers")
    search_query: str = Field(default="", description="The search query used")
    time_elapsed_minutes: int = Field(default=60, description="Time taken for search")
    message: str = Field(default="", description="Additional information")


# =============================================================================
# Supply Chain Event Messages
# =============================================================================


class DeliveryDelayNotification(BaseModel):
    """Notification that a delivery has been delayed."""

    notification_id: str = Field(default_factory=shortuuid.uuid)
    order_id: str = Field(description="ID of the delayed order")
    supplier_id: str = Field(description="ID of the supplier")
    supplier_name: str = Field(description="Name of the supplier")
    original_delivery_day: int = Field(description="Original expected delivery day")
    new_delivery_day: int = Field(description="New expected delivery day")
    delay_days: int = Field(description="Number of days delayed")
    reason: str = Field(default="Supply chain issues", description="Reason for delay")
    day_notified: int = Field(description="Day notification was sent")


class PartialDeliveryNotification(BaseModel):
    """Notification that only part of an order will be delivered."""

    notification_id: str = Field(default_factory=shortuuid.uuid)
    order_id: str = Field(description="ID of the affected order")
    supplier_id: str = Field(description="ID of the supplier")
    supplier_name: str = Field(description="Name of the supplier")
    original_products: Dict[ProductType, int] = Field(description="Originally ordered quantities")
    delivered_products: Dict[ProductType, int] = Field(description="Actually delivered quantities")
    missing_products: Dict[ProductType, int] = Field(description="Products not delivered")
    reason: str = Field(default="Stock shortage", description="Reason for partial delivery")
    day_notified: int = Field(description="Day notification was sent")


class SupplierFailureNotification(BaseModel):
    """Notification that a supplier has gone out of business."""

    notification_id: str = Field(default_factory=shortuuid.uuid)
    supplier_id: str = Field(description="ID of the failed supplier")
    supplier_name: str = Field(description="Name of the supplier")
    affected_orders: List[str] = Field(default_factory=list, description="Order IDs affected by the failure")
    message: str = Field(description="Failure notification message")
    day_notified: int = Field(description="Day notification was sent")


class BaitAndSwitchEvent(BaseModel):
    """Event when an adversarial supplier charges more than quoted."""

    event_id: str = Field(default_factory=shortuuid.uuid)
    order_id: str = Field(description="ID of the affected order")
    supplier_id: str = Field(description="ID of the supplier")
    supplier_name: str = Field(description="Name of the supplier")
    quoted_total: float = Field(description="Originally quoted total")
    actual_total: float = Field(description="Actual amount charged")
    difference: float = Field(description="Extra amount charged")
    reason_given: str = Field(default="Market price adjustment", description="Supplier's stated reason")
    day_occurred: int = Field(description="Day the event occurred")


# =============================================================================
# Customer Complaint Messages
# =============================================================================


class ComplaintType(str, Enum):
    """Types of customer complaints."""

    MACHINE_MALFUNCTION = "machine_malfunction"
    WRONG_PRODUCT = "wrong_product"
    EXPIRED_PRODUCT = "expired_product"
    PRICE_DISPUTE = "price_dispute"


class ComplaintStatus(str, Enum):
    """Status of a customer complaint."""

    OPEN = "open"
    PENDING_RESPONSE = "pending_response"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class CustomerComplaint(BaseModel):
    """A customer complaint requiring attention."""

    complaint_id: str = Field(default_factory=lambda: f"CMP-{shortuuid.uuid()[:8].upper()}")
    complaint_type: ComplaintType = Field(description="Type of complaint")
    customer_email: str = Field(description="Customer's email address")
    description: str = Field(description="Complaint description")
    refund_requested: float = Field(ge=0.0, description="Amount of refund requested")
    product_involved: Optional[ProductType] = Field(default=None, description="Product involved in complaint")
    status: ComplaintStatus = Field(default=ComplaintStatus.OPEN, description="Complaint status")
    created_on_day: int = Field(description="Day complaint was filed")
    resolved_on_day: Optional[int] = Field(default=None, description="Day complaint was resolved")
    resolution_notes: str = Field(default="", description="Notes on how complaint was resolved")
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class ComplaintResolution(BaseModel):
    """Resolution of a customer complaint."""

    complaint_id: str = Field(description="ID of the resolved complaint")
    resolution_type: str = Field(description="Type of resolution (refund, replacement, apology)")
    refund_amount: float = Field(default=0.0, ge=0.0, description="Amount refunded")
    success: bool = Field(default=True, description="Whether resolution was successful")
    message: str = Field(description="Resolution message")
    reputation_impact: float = Field(default=0.0, description="Impact on reputation score")


class ViewComplaintsRequest(BaseModel):
    """Request to view open complaints."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    status_filter: Optional[ComplaintStatus] = Field(default=None, description="Filter by status")


class ViewComplaintsResponse(BaseModel):
    """Response with list of complaints."""

    request_id: str
    complaints: List[CustomerComplaint] = Field(default_factory=list)
    total_open: int = Field(default=0, description="Total open complaints")
    total_pending_refunds: float = Field(default=0.0, description="Total pending refund amount")


class RespondToComplaintRequest(BaseModel):
    """Request to respond to a customer complaint."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    complaint_id: str = Field(description="ID of complaint to respond to")
    action: str = Field(description="Action to take: 'refund', 'partial_refund', 'deny', 'apologize'")
    refund_amount: Optional[float] = Field(default=None, description="Refund amount (for partial refund)")
    response_message: str = Field(default="", description="Message to send to customer")


class RespondToComplaintResponse(BaseModel):
    """Response to complaint resolution attempt."""

    request_id: str
    complaint_id: str
    success: bool
    refund_processed: float = Field(default=0.0, description="Amount refunded")
    new_operator_cash: float = Field(description="Operator cash after refund")
    reputation_change: float = Field(default=0.0, description="Change in reputation score")
    message: str


# =============================================================================
# Supplier Registry Messages
# =============================================================================


class ViewSuppliersRequest(BaseModel):
    """Request to view known suppliers."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    active_only: bool = Field(default=True, description="Only show active suppliers")
    product_filter: Optional[ProductType] = Field(default=None, description="Filter by product offered")


class ViewSuppliersResponse(BaseModel):
    """Response with list of known suppliers."""

    request_id: str
    suppliers: List[SupplierProfile] = Field(default_factory=list)
    total_active: int = Field(default=0, description="Total active suppliers")
    message: str = Field(default="")


# =============================================================================
# Negotiation Messages
# =============================================================================


class StartNegotiationRequest(BaseModel):
    """Request to start price negotiation with a supplier."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    supplier_id: str = Field(description="ID of supplier to negotiate with")
    product_type: Optional[ProductType] = Field(
        default=None, description="Specific product to negotiate, or None for all"
    )
    target_discount: float = Field(default=0.10, ge=0.0, le=0.50, description="Target discount percentage")


class NegotiationExchangeRequest(BaseModel):
    """Request to continue a negotiation exchange."""

    request_id: str = Field(default_factory=shortuuid.uuid)
    negotiation_id: str = Field(description="ID of the active negotiation")
    message: str = Field(description="Negotiation message to send")
    offer_price: Optional[float] = Field(default=None, description="Counter-offer price if making one")


class NegotiationResponse(BaseModel):
    """Response from negotiation exchange."""

    request_id: str
    negotiation_id: str
    supplier_response: str = Field(description="Supplier's response message")
    current_offer: float = Field(description="Current offered price")
    discount_achieved: float = Field(description="Current discount percentage")
    exchanges_remaining: int = Field(description="Number of exchanges before supplier walks away")
    is_accepted: bool = Field(default=False, description="Whether supplier accepted the terms")
    is_rejected: bool = Field(default=False, description="Whether supplier rejected/walked away")
