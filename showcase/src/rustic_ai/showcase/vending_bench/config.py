"""
Configuration constants for the VendingBench simulation.

Based on the VendingBench paper (arxiv:2502.15840).
"""

from enum import Enum
from typing import Dict


class ProductType(str, Enum):
    """Product types available in the vending machine."""

    CHIPS = "chips"
    CANDY = "candy"
    SODA = "soda"
    WATER = "water"
    ENERGY_DRINK = "energy_drink"


# Starting conditions
STARTING_CAPITAL: float = 500.0
DAILY_FEE: float = 2.0
BANKRUPTCY_DAYS: int = 10

# Default prices (what the agent sells products for)
DEFAULT_PRICES: Dict[ProductType, float] = {
    ProductType.CHIPS: 1.50,
    ProductType.CANDY: 1.25,
    ProductType.SODA: 2.00,
    ProductType.WATER: 1.50,
    ProductType.ENERGY_DRINK: 3.00,
}

# Default costs (what the agent pays to restock from supplier)
DEFAULT_COSTS: Dict[ProductType, float] = {
    ProductType.CHIPS: 0.75,
    ProductType.CANDY: 0.60,
    ProductType.SODA: 0.80,
    ProductType.WATER: 0.50,
    ProductType.ENERGY_DRINK: 1.50,
}

# Default starting inventory
DEFAULT_STOCK: Dict[ProductType, int] = {
    ProductType.CHIPS: 20,
    ProductType.CANDY: 25,
    ProductType.SODA: 30,
    ProductType.WATER: 30,
    ProductType.ENERGY_DRINK: 15,
}

# Base daily demand per product (average number of purchases per day)
BASE_DEMAND: Dict[ProductType, int] = {
    ProductType.CHIPS: 8,
    ProductType.CANDY: 10,
    ProductType.SODA: 12,
    ProductType.WATER: 15,
    ProductType.ENERGY_DRINK: 5,
}

# Time costs per action (in minutes)
TIME_COSTS: Dict[str, int] = {
    # Quick actions (5 minutes)
    "check_inventory": 5,
    "check_balance": 5,
    # Medium actions (25 minutes)
    "read_emails": 25,
    "scratchpad_read": 25,
    # Long actions (75 minutes = 1.25 hours)
    "send_email": 75,
    "set_price": 75,
    "scratchpad_write": 75,
    # Extended actions (300 minutes = 5 hours)
    "collect_cash": 300,
    "restock": 300,
    # Time management actions
    "wait": 60,  # Wait for 1 hour
    "end_day": 720,  # Skip to end of current day (12 hours max)
}

# Day duration settings
DAY_DURATION_MINUTES: int = 720  # 12 hours of active time (8 AM - 8 PM)
NIGHT_DURATION_MINUTES: int = 720  # 12 hours of night (8 PM - 8 AM)
TOTAL_DAY_MINUTES: int = DAY_DURATION_MINUTES + NIGHT_DURATION_MINUTES  # 24 hours

# Price elasticity settings
PRICE_ELASTICITY: float = -1.5  # Demand decreases 1.5% for each 1% price increase

# Day-of-week demand multipliers (0 = Monday, 6 = Sunday)
DAY_OF_WEEK_MULTIPLIERS: Dict[int, float] = {
    0: 0.9,  # Monday - lower traffic
    1: 1.0,  # Tuesday - normal
    2: 1.0,  # Wednesday - normal
    3: 1.0,  # Thursday - normal
    4: 1.2,  # Friday - higher traffic
    5: 1.3,  # Saturday - weekend high
    6: 1.1,  # Sunday - weekend moderate
}

# Weather demand multipliers
WEATHER_DRINK_MULTIPLIERS: Dict[str, float] = {
    "sunny": 1.2,  # Hot weather = more drinks
    "cloudy": 1.0,
    "rainy": 0.8,  # Less foot traffic
    "hot": 1.5,  # Very hot = lots more drinks
    "cold": 0.7,  # Cold weather = fewer drinks
}

WEATHER_SNACK_MULTIPLIERS: Dict[str, float] = {
    "sunny": 1.0,
    "cloudy": 1.0,
    "rainy": 0.9,
    "hot": 0.9,  # Hot weather = less snacking
    "cold": 1.1,  # Cold weather = more snacking
}

# Supplier settings
SUPPLIER_DELIVERY_DAYS_MIN: int = 2
SUPPLIER_DELIVERY_DAYS_MAX: int = 5

# Maximum inventory capacity per slot
MAX_INVENTORY_PER_PRODUCT: int = 50
