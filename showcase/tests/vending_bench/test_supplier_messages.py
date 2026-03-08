"""
Tests for supplier simulation message types.
"""

from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.supplier_messages import (
    BaitAndSwitchEvent,
    ComplaintResolution,
    ComplaintStatus,
    ComplaintType,
    CustomerComplaint,
    DeliveryDelayNotification,
    NegotiationExchangeRequest,
    NegotiationResponse,
    PartialDeliveryNotification,
    RespondToComplaintRequest,
    RespondToComplaintResponse,
    StartNegotiationRequest,
    SupplierFailureNotification,
    SupplierSearchRequest,
    SupplierSearchResponse,
    ViewComplaintsRequest,
    ViewComplaintsResponse,
    ViewSuppliersRequest,
    ViewSuppliersResponse,
)
from rustic_ai.showcase.vending_bench.supplier_registry import (
    SupplierProfile,
)


class TestSupplierSearchMessages:
    """Tests for supplier search messages."""

    def test_supplier_search_request(self):
        """Should create search request."""
        request = SupplierSearchRequest(
            product_types=[ProductType.CHIPS, ProductType.SODA],
            location="New York",
            max_results=5,
        )
        assert request.product_types == [ProductType.CHIPS, ProductType.SODA]
        assert request.location == "New York"
        assert request.max_results == 5
        assert request.request_id is not None

    def test_supplier_search_request_defaults(self):
        """Should use default values."""
        request = SupplierSearchRequest()
        assert request.product_types == []
        assert request.location == ""
        assert request.max_results == 5

    def test_supplier_search_response(self):
        """Should create search response with suppliers."""
        supplier = SupplierProfile(
            name="Found Supplier",
            email="found@supplier.com",
        )
        response = SupplierSearchResponse(
            request_id="test-123",
            suppliers_found=[supplier],
            search_query="vending machine chips wholesaler",
            time_elapsed_minutes=60,
            message="Found 1 suppliers",
        )
        assert response.request_id == "test-123"
        assert len(response.suppliers_found) == 1
        assert response.suppliers_found[0].name == "Found Supplier"
        assert response.time_elapsed_minutes == 60


class TestSupplyChainEventMessages:
    """Tests for supply chain event messages."""

    def test_delivery_delay_notification(self):
        """Should create delivery delay notification."""
        notification = DeliveryDelayNotification(
            order_id="ORD-TEST123",
            supplier_id="SUP-ABC",
            supplier_name="Test Supplier",
            original_delivery_day=5,
            new_delivery_day=8,
            delay_days=3,
            reason="Supply chain issues",
            day_notified=4,
        )
        assert notification.order_id == "ORD-TEST123"
        assert notification.original_delivery_day == 5
        assert notification.new_delivery_day == 8
        assert notification.delay_days == 3
        assert notification.notification_id is not None

    def test_partial_delivery_notification(self):
        """Should create partial delivery notification."""
        notification = PartialDeliveryNotification(
            order_id="ORD-TEST456",
            supplier_id="SUP-XYZ",
            supplier_name="Partial Supplier",
            original_products={ProductType.CHIPS: 20, ProductType.CANDY: 15},
            delivered_products={ProductType.CHIPS: 15, ProductType.CANDY: 10},
            missing_products={ProductType.CHIPS: 5, ProductType.CANDY: 5},
            reason="Stock shortage",
            day_notified=7,
        )
        assert notification.order_id == "ORD-TEST456"
        assert notification.original_products[ProductType.CHIPS] == 20
        assert notification.delivered_products[ProductType.CHIPS] == 15
        assert notification.missing_products[ProductType.CHIPS] == 5

    def test_supplier_failure_notification(self):
        """Should create supplier failure notification."""
        notification = SupplierFailureNotification(
            supplier_id="SUP-FAILED",
            supplier_name="Failed Supplier Inc",
            affected_orders=["ORD-1", "ORD-2", "ORD-3"],
            message="Supplier has gone out of business.",
            day_notified=15,
        )
        assert notification.supplier_id == "SUP-FAILED"
        assert len(notification.affected_orders) == 3
        assert notification.notification_id is not None

    def test_bait_and_switch_event(self):
        """Should create bait-and-switch event."""
        event = BaitAndSwitchEvent(
            order_id="ORD-BAIT123",
            supplier_id="SUP-SHADY",
            supplier_name="Shady Supplier",
            quoted_total=50.00,
            actual_total=65.00,
            difference=15.00,
            reason_given="Market price adjustment",
            day_occurred=10,
        )
        assert event.order_id == "ORD-BAIT123"
        assert event.quoted_total == 50.00
        assert event.actual_total == 65.00
        assert event.difference == 15.00
        assert event.event_id is not None


class TestCustomerComplaintMessages:
    """Tests for customer complaint messages."""

    def test_complaint_types(self):
        """Should have all expected complaint types."""
        assert ComplaintType.MACHINE_MALFUNCTION.value == "machine_malfunction"
        assert ComplaintType.WRONG_PRODUCT.value == "wrong_product"
        assert ComplaintType.EXPIRED_PRODUCT.value == "expired_product"
        assert ComplaintType.PRICE_DISPUTE.value == "price_dispute"

    def test_complaint_status(self):
        """Should have all expected complaint statuses."""
        assert ComplaintStatus.OPEN.value == "open"
        assert ComplaintStatus.PENDING_RESPONSE.value == "pending_response"
        assert ComplaintStatus.RESOLVED.value == "resolved"
        assert ComplaintStatus.ESCALATED.value == "escalated"

    def test_customer_complaint(self):
        """Should create customer complaint."""
        complaint = CustomerComplaint(
            complaint_type=ComplaintType.MACHINE_MALFUNCTION,
            customer_email="angry@customer.com",
            description="The machine ate my money!",
            refund_requested=5.00,
            product_involved=ProductType.CHIPS,
            created_on_day=3,
        )
        assert complaint.complaint_type == ComplaintType.MACHINE_MALFUNCTION
        assert complaint.customer_email == "angry@customer.com"
        assert complaint.refund_requested == 5.00
        assert complaint.status == ComplaintStatus.OPEN
        assert complaint.complaint_id.startswith("CMP-")
        assert complaint.timestamp is not None

    def test_complaint_resolution(self):
        """Should create complaint resolution."""
        resolution = ComplaintResolution(
            complaint_id="CMP-TEST123",
            resolution_type="refund",
            refund_amount=5.00,
            success=True,
            message="Full refund issued",
            reputation_impact=1.0,
        )
        assert resolution.complaint_id == "CMP-TEST123"
        assert resolution.resolution_type == "refund"
        assert resolution.refund_amount == 5.00
        assert resolution.success is True

    def test_view_complaints_request(self):
        """Should create view complaints request."""
        request = ViewComplaintsRequest(
            status_filter=ComplaintStatus.OPEN,
        )
        assert request.status_filter == ComplaintStatus.OPEN
        assert request.request_id is not None

    def test_view_complaints_response(self):
        """Should create view complaints response."""
        complaint = CustomerComplaint(
            complaint_type=ComplaintType.WRONG_PRODUCT,
            customer_email="test@customer.com",
            description="Wrong product received",
            refund_requested=3.00,
            created_on_day=5,
        )
        response = ViewComplaintsResponse(
            request_id="req-123",
            complaints=[complaint],
            total_open=1,
            total_pending_refunds=3.00,
        )
        assert len(response.complaints) == 1
        assert response.total_open == 1
        assert response.total_pending_refunds == 3.00

    def test_respond_to_complaint_request(self):
        """Should create respond to complaint request."""
        request = RespondToComplaintRequest(
            complaint_id="CMP-TEST123",
            action="refund",
            refund_amount=5.00,
            response_message="We apologize for the inconvenience.",
        )
        assert request.complaint_id == "CMP-TEST123"
        assert request.action == "refund"
        assert request.refund_amount == 5.00

    def test_respond_to_complaint_response(self):
        """Should create respond to complaint response."""
        response = RespondToComplaintResponse(
            request_id="req-456",
            complaint_id="CMP-TEST123",
            success=True,
            refund_processed=5.00,
            new_operator_cash=495.00,
            reputation_change=1.0,
            message="Complaint resolved successfully",
        )
        assert response.success is True
        assert response.refund_processed == 5.00
        assert response.new_operator_cash == 495.00


class TestViewSuppliersMessages:
    """Tests for view suppliers messages."""

    def test_view_suppliers_request(self):
        """Should create view suppliers request."""
        request = ViewSuppliersRequest(
            active_only=True,
            product_filter=ProductType.SODA,
        )
        assert request.active_only is True
        assert request.product_filter == ProductType.SODA

    def test_view_suppliers_response(self):
        """Should create view suppliers response."""
        supplier = SupplierProfile(
            name="Test Supplier",
            email="test@supplier.com",
        )
        response = ViewSuppliersResponse(
            request_id="req-789",
            suppliers=[supplier],
            total_active=1,
            message="Found 1 suppliers",
        )
        assert len(response.suppliers) == 1
        assert response.total_active == 1


class TestNegotiationMessages:
    """Tests for negotiation messages."""

    def test_start_negotiation_request(self):
        """Should create start negotiation request."""
        request = StartNegotiationRequest(
            supplier_id="SUP-TEST123",
            product_type=ProductType.ENERGY_DRINK,
            target_discount=0.15,
        )
        assert request.supplier_id == "SUP-TEST123"
        assert request.product_type == ProductType.ENERGY_DRINK
        assert request.target_discount == 0.15

    def test_negotiation_exchange_request(self):
        """Should create negotiation exchange request."""
        request = NegotiationExchangeRequest(
            negotiation_id="NEG-TEST123",
            message="Can you do $1.50?",
            offer_price=1.50,
        )
        assert request.negotiation_id == "NEG-TEST123"
        assert request.message == "Can you do $1.50?"
        assert request.offer_price == 1.50

    def test_negotiation_response_accepted(self):
        """Should create accepted negotiation response."""
        response = NegotiationResponse(
            request_id="req-123",
            negotiation_id="NEG-TEST123",
            supplier_response="Deal! We accept $1.50.",
            current_offer=1.50,
            discount_achieved=0.10,
            exchanges_remaining=3,
            is_accepted=True,
            is_rejected=False,
        )
        assert response.is_accepted is True
        assert response.is_rejected is False
        assert response.current_offer == 1.50
        assert response.discount_achieved == 0.10

    def test_negotiation_response_rejected(self):
        """Should create rejected negotiation response."""
        response = NegotiationResponse(
            request_id="req-456",
            negotiation_id="NEG-TEST456",
            supplier_response="Sorry, that's too low.",
            current_offer=1.80,
            discount_achieved=0.05,
            exchanges_remaining=0,
            is_accepted=False,
            is_rejected=True,
        )
        assert response.is_accepted is False
        assert response.is_rejected is True
        assert response.exchanges_remaining == 0
