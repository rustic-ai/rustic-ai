"""
Configuration constants for realistic supplier simulation.

Based on the Vending-Bench paper for adversarial supplier dynamics.
"""

# Supplier behavior type probabilities
# When discovering new suppliers, these probabilities determine their behavior type
HONEST_SUPPLIER_PROBABILITY = 0.5  # Fair pricing, reliable delivery
ADVERSARIAL_SUPPLIER_PROBABILITY = 0.3  # Price gouging, bait-and-switch tactics
UNRELIABLE_SUPPLIER_PROBABILITY = 0.2  # Delays, partial deliveries, may go bankrupt

# Adversarial supplier pricing
# Adversarial suppliers quote prices inflated by this multiplier range
PRICE_GOUGING_MULTIPLIER_MIN = 1.5
PRICE_GOUGING_MULTIPLIER_MAX = 3.0

# Bait-and-switch probability for adversarial suppliers
# When order is delivered, they may charge more than quoted
BAIT_AND_SWITCH_PROBABILITY = 0.3

# Negotiation settings
INITIAL_QUOTE_MARKUP = 0.30  # Suppliers start with 30% markup over base cost
MAX_NEGOTIATION_DISCOUNT = 0.25  # Maximum discount achievable through negotiation
DISCOUNT_PER_EXCHANGE = 0.03  # 3% discount per negotiation exchange
MAX_NEGOTIATION_EXCHANGES = 8  # Maximum back-and-forth before supplier walks away

# Loyalty discount settings
MAX_LOYALTY_DISCOUNT = 0.10  # Maximum 10% loyalty discount

# Supply chain risk probabilities (per delivery for unreliable suppliers)
DELIVERY_DELAY_PROBABILITY = 0.15  # 15% chance of delivery delay
PARTIAL_DELIVERY_PROBABILITY = 0.10  # 10% chance of partial delivery
PARTIAL_DELIVERY_FRACTION_MIN = 0.3  # Minimum fraction delivered in partial
PARTIAL_DELIVERY_FRACTION_MAX = 0.8  # Maximum fraction delivered in partial

# Supplier bankruptcy probability (monthly rate for unreliable suppliers)
SUPPLIER_BANKRUPTCY_PROBABILITY = 0.02  # 2% monthly chance of going bankrupt

# Customer complaint settings
BASE_COMPLAINT_RATE = 0.02  # 2% base daily complaint rate
OUT_OF_STOCK_COMPLAINT_BONUS = 0.05  # +5% if frequently out of stock
HIGH_PRICE_COMPLAINT_BONUS = 0.03  # +3% if prices are high

# Complaint types and their refund amounts
COMPLAINT_REFUND_AMOUNTS = {
    "machine_malfunction": (2.0, 5.0),  # Range for random refund
    "wrong_product": (1.0, 3.0),
    "expired_product": (1.5, 4.0),
    "price_dispute": (0.50, 2.0),
}

# Reputation settings
INITIAL_REPUTATION_SCORE = 80.0  # Starting reputation (0-100)
COMPLAINT_REPUTATION_PENALTY = 2.0  # Points lost per unresolved complaint
RESOLVED_COMPLAINT_REPUTATION_GAIN = 0.5  # Points gained for resolving complaints
MIN_REPUTATION_SCORE = 0.0
MAX_REPUTATION_SCORE = 100.0

# Delay duration settings (in days)
DELAY_DURATION_MIN = 1
DELAY_DURATION_MAX = 5

# Default supplier email
DEFAULT_SUPPLIER_EMAIL = "orders@vendingsupply.com"
OPERATOR_EMAIL = "operator@vendingbiz.com"
