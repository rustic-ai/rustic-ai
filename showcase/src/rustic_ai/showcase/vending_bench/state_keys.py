"""
Guild state key constants for VendingBench simulation.

Centralizes all guild state keys to prevent typos and enable easier refactoring.
Keys are organized by the agent that primarily owns/manages them.
"""

# =============================================================================
# Simulation Controller State Keys
# =============================================================================

# Shared simulation state (read by multiple agents)
CURRENT_DAY = "current_day"
CURRENT_TIME_MINUTES = "current_time_minutes"
SIMULATION_STATUS = "simulation_status"

# Financial state
OPERATOR_CASH = "operator_cash"
MACHINE_CASH = "machine_cash"
DAYS_WITHOUT_PAYMENT = "days_without_payment"


# =============================================================================
# Vending Machine Agent State Keys
# =============================================================================

VM_INVENTORY = "vm_inventory"
VM_PENDING_DELIVERIES = "vm_pending_deliveries"


# =============================================================================
# Supplier Agent State Keys
# =============================================================================

SUPPLIER_INBOX = "supplier_inbox"
SUPPLIER_SENT_EMAILS = "supplier_sent_emails"
SUPPLIER_PENDING_ORDERS = "supplier_pending_orders"
SCRATCHPAD = "scratchpad"
SUPPLIER_CURRENT_DAY = "supplier_current_day"
SUPPLIER_SIMULATION_TIME = "supplier_simulation_time"
SUPPLIER_REGISTRY = "supplier_registry"


# =============================================================================
# Supplier Discovery Agent State Keys
# =============================================================================

PENDING_SUPPLIER_SEARCHES = "pending_supplier_searches"


# =============================================================================
# Customer Complaint Agent State Keys
# =============================================================================

CUSTOMER_COMPLAINTS = "customer_complaints"
REPUTATION_SCORE = "reputation_score"
OUT_OF_STOCK_DAYS = "out_of_stock_days"
HIGH_PRICE_DAYS = "high_price_days"
COMPLAINT_SIMULATION_TIME = "complaint_simulation_time"


# =============================================================================
# Status Tracker Agent State Keys
# =============================================================================

TRACKER_NET_WORTH_HISTORY = "tracker_net_worth_history"
TRACKER_CASH_BREAKDOWN_HISTORY = "tracker_cash_breakdown_history"
TRACKER_INVENTORY_HISTORY = "tracker_inventory_history"
TRACKER_EMAILS_SENT = "tracker_emails_sent"
TRACKER_EMAILS_RECEIVED = "tracker_emails_received"
TRACKER_DAILY_SALES = "tracker_daily_sales"
TRACKER_TOTAL_SALES = "tracker_total_sales"
TRACKER_TOTAL_REVENUE = "tracker_total_revenue"
TRACKER_CURRENT_DAY_SALES = "tracker_current_day_sales"
TRACKER_CURRENT_DAY_REVENUE = "tracker_current_day_revenue"
TRACKER_CURRENT_DAY = "tracker_current_day"
TRACKER_CURRENT_NET_WORTH = "tracker_current_net_worth"
