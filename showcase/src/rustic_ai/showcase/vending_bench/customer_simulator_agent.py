"""
CustomerSimulatorAgent - Simulates customer purchases.

This agent generates realistic customer purchase patterns based on:
- Current prices
- Day of week
- Weather conditions
- Random variation
"""

import random
import logging
from typing import Dict

from pydantic import Field

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.showcase.vending_bench.config import (
    DEFAULT_PRICES,
    PRICE_ELASTICITY,
    ProductType,
)
from rustic_ai.showcase.vending_bench.economics import calculate_demand
from rustic_ai.showcase.vending_bench.messages import (
    CustomerPurchaseEvent,
    DayUpdateEvent,
    VendingMachineState,
    WeatherType,
)

logger = logging.getLogger(__name__)


class CustomerSimulatorAgentProps(BaseAgentProps):
    """Configuration properties for CustomerSimulatorAgent."""

    price_elasticity: float = Field(default=PRICE_ELASTICITY)
    demand_variance: float = Field(default=0.2, description="Variance in demand (0-1)")
    batch_purchases: bool = Field(default=True, description="Whether to batch purchases or emit individually")


class CustomerSimulatorAgent(Agent[CustomerSimulatorAgentProps]):
    """Agent that simulates customer purchases.

    Generates realistic purchase events based on economic model
    when a day starts. Purchases are distributed throughout the day.
    """

    def __init__(self):
        # Track current simulation state
        self.current_day: int = 1
        self.current_prices: Dict[ProductType, float] = {p: DEFAULT_PRICES[p] for p in ProductType}
        self.daily_purchases: int = 0

    def _generate_purchases_for_day(
        self,
        day: int,
        day_of_week: int,
        weather: WeatherType,
        prices: Dict[ProductType, float],
    ) -> list[CustomerPurchaseEvent]:
        """Generate all customer purchase events for a day.

        Args:
            day: Current day number
            day_of_week: Day of week (0=Monday, 6=Sunday)
            weather: Current weather condition
            prices: Current prices for all products

        Returns:
            List of CustomerPurchaseEvent for the day
        """
        purchases = []

        for product in ProductType:
            price = prices.get(product, DEFAULT_PRICES[product])

            # Calculate demand for this product
            demand = calculate_demand(
                product=product,
                current_price=price,
                day_of_week=day_of_week,
                weather=weather,
                add_randomness=True,
            )

            # Generate individual purchase events
            # Distribute throughout the day (0-720 minutes of business hours)
            for i in range(demand):
                # Random time during business hours (8 AM = 0, 8 PM = 720)
                time_of_day = random.randint(0, 719)

                purchase = CustomerPurchaseEvent(
                    product=product,
                    quantity=1,  # Single item purchases
                    price_paid=price,
                    day=day,
                    time_of_day_minutes=time_of_day,
                )
                purchases.append(purchase)

        # Sort by time of day for realistic ordering
        purchases.sort(key=lambda p: p.time_of_day_minutes)

        return purchases

    @agent.processor(DayUpdateEvent)
    def handle_day_start(self, ctx: ProcessContext[DayUpdateEvent]):
        """Generate customer purchases when a new day starts."""
        event = ctx.payload

        self.current_day = event.day

        # Generate purchases for the day
        purchases = self._generate_purchases_for_day(
            day=event.day,
            day_of_week=event.day_of_week,
            weather=event.weather,
            prices=self.current_prices,
        )

        self.daily_purchases = len(purchases)

        # Emit all purchase events
        for purchase in purchases:
            ctx.send(purchase)

        logger.info(f"Day {event.day}: Generated {len(purchases)} customer purchases")

    @agent.processor(VendingMachineState)
    def handle_state_update(self, ctx: ProcessContext[VendingMachineState]):
        """Update local price cache when vending machine state changes."""
        state = ctx.payload

        # Update prices for demand calculation
        self.current_prices = {p: state.prices.get(p, DEFAULT_PRICES[p]) for p in ProductType}

        logger.debug(f"Updated prices: {self.current_prices}")
