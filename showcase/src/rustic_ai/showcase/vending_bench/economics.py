"""
Economics module for VendingBench simulation.

Implements demand calculation based on price elasticity, day-of-week effects,
and weather conditions.
"""

import math
import random
from typing import Dict, Optional

from rustic_ai.showcase.vending_bench.config import (
    BASE_DEMAND,
    DAY_OF_WEEK_MULTIPLIERS,
    DEFAULT_PRICES,
    PRICE_ELASTICITY,
    WEATHER_DRINK_MULTIPLIERS,
    WEATHER_SNACK_MULTIPLIERS,
    ProductType,
)
from rustic_ai.showcase.vending_bench.messages import WeatherType


def is_drink(product: ProductType) -> bool:
    """Check if a product is a drink (affected by weather differently)."""
    return product in [ProductType.SODA, ProductType.WATER, ProductType.ENERGY_DRINK]


def get_weather_multiplier(product: ProductType, weather: WeatherType) -> float:
    """Get the weather demand multiplier for a product.

    Drinks are more affected by hot weather, snacks by cold weather.

    Args:
        product: The product type
        weather: Current weather condition

    Returns:
        Multiplier for demand (1.0 = no change)
    """
    weather_str = weather.value
    if is_drink(product):
        return WEATHER_DRINK_MULTIPLIERS.get(weather_str, 1.0)
    else:
        return WEATHER_SNACK_MULTIPLIERS.get(weather_str, 1.0)


def calculate_price_elasticity_multiplier(
    current_price: float, base_price: float, elasticity: float = PRICE_ELASTICITY
) -> float:
    """Calculate demand multiplier based on price change.

    Uses constant elasticity demand model:
    Q = Q0 * (P / P0) ^ elasticity

    Args:
        current_price: Current selling price
        base_price: Default/base price
        elasticity: Price elasticity of demand (negative)

    Returns:
        Multiplier for demand based on price (1.0 if price unchanged)
    """
    if base_price <= 0 or current_price <= 0:
        return 1.0

    price_ratio = current_price / base_price
    return price_ratio**elasticity


def calculate_demand(
    product: ProductType,
    current_price: float,
    day_of_week: int,
    weather: WeatherType,
    base_price: Optional[float] = None,
    add_randomness: bool = True,
) -> int:
    """Calculate expected demand for a product.

    Combines base demand with price elasticity, day-of-week effects,
    and weather conditions to calculate expected customer purchases.

    Args:
        product: Product type to calculate demand for
        current_price: Current selling price
        day_of_week: Day of week (0=Monday, 6=Sunday)
        weather: Current weather condition
        base_price: Base price for elasticity calculation (uses default if None)
        add_randomness: Whether to add random variation

    Returns:
        Expected number of purchases (non-negative integer)
    """
    if base_price is None:
        base_price = DEFAULT_PRICES.get(product, 1.0)

    # Start with base demand
    base = BASE_DEMAND.get(product, 10)

    # Apply price elasticity
    price_multiplier = calculate_price_elasticity_multiplier(current_price, base_price)

    # Apply day-of-week multiplier
    dow_multiplier = DAY_OF_WEEK_MULTIPLIERS.get(day_of_week, 1.0)

    # Apply weather multiplier
    weather_multiplier = get_weather_multiplier(product, weather)

    # Calculate expected demand
    expected_demand = base * price_multiplier * dow_multiplier * weather_multiplier

    # Add randomness using Poisson distribution (common for count data)
    if add_randomness and expected_demand > 0:
        # Poisson distribution with lambda = expected_demand
        # Using numpy would be cleaner, but we'll use a simple implementation
        demand = poisson_sample(expected_demand)
    else:
        demand = round(expected_demand)

    return max(0, demand)


def poisson_sample(lam: float) -> int:
    """Sample from a Poisson distribution.

    Simple implementation using inverse transform sampling.

    Args:
        lam: Lambda (mean) of the Poisson distribution

    Returns:
        Random sample from Poisson(lam)
    """
    if lam <= 0:
        return 0

    # Use inverse transform sampling
    L = math.exp(-lam)  # e^(-lambda)
    k = 0
    p = 1.0

    while p > L:
        k += 1
        p *= random.random()

    return k - 1


def calculate_daily_demand(
    prices: Dict[ProductType, float], day_of_week: int, weather: WeatherType
) -> Dict[ProductType, int]:
    """Calculate demand for all products for a day.

    Args:
        prices: Current prices for all products
        day_of_week: Day of week (0=Monday, 6=Sunday)
        weather: Current weather condition

    Returns:
        Dictionary mapping product types to expected demand
    """
    demand = {}
    for product in ProductType:
        price = prices.get(product, DEFAULT_PRICES[product])
        demand[product] = calculate_demand(
            product=product,
            current_price=price,
            day_of_week=day_of_week,
            weather=weather,
        )
    return demand


def calculate_inventory_value(inventory: Dict[ProductType, int], cost_prices: Dict[ProductType, float]) -> float:
    """Calculate the total value of inventory at cost.

    Args:
        inventory: Current inventory levels
        cost_prices: Cost per unit for each product

    Returns:
        Total inventory value
    """
    total = 0.0
    for product, quantity in inventory.items():
        cost = cost_prices.get(product, 0.0)
        total += quantity * cost
    return total


def calculate_net_worth(
    machine_cash: float,
    operator_cash: float,
    inventory: Dict[ProductType, int],
    cost_prices: Dict[ProductType, float],
) -> float:
    """Calculate total net worth.

    Net worth = cash on hand + machine cash + unsold product value (at cost)

    Args:
        machine_cash: Cash in the vending machine
        operator_cash: Cash held by the operator
        inventory: Current inventory levels
        cost_prices: Cost per unit for each product

    Returns:
        Total net worth
    """
    inventory_value = calculate_inventory_value(inventory, cost_prices)
    return machine_cash + operator_cash + inventory_value
