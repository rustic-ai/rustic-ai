"""
VendingBench Player Toolset - Tools for interacting with VendingBench simulation via G2G.

This module provides VendingBenchToolspecsProvider for use with LLMAgent + ToolsManagerPlugin.
When the LLM calls a tool, the plugin produces the corresponding VendingBench request message
which gets routed via G2G to the VendingBench guild.
"""

from typing import List, Optional

from rustic_ai.llm_agent.tools.tools_manager_plugin import ToolspecsProvider

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec

from .messages import (
    CheckBalanceRequest,
    CheckInventoryRequest,
    CollectCashRequest,
    EndDayRequest,
    ReadEmailsRequest,
    RestockRequest,
    ScratchpadReadRequest,
    ScratchpadWriteRequest,
    SendEmailRequest,
    SetPriceRequest,
    WaitRequest,
)


class VendingBenchToolspecsProvider(ToolspecsProvider):
    """
    Toolspecs provider for VendingBench that produces VendingBench request messages.

    Use this with LLMAgent's ToolsManagerPlugin. When the LLM calls a tool,
    the ToolsManagerPlugin will create the corresponding VendingBench request
    message which can then be routed via G2G to the VendingBench guild.
    """

    additional_system_prompt: Optional[str] = (
        "You are operating a vending machine business in a simulation. Your goal is to maximize net worth.\n\n"
        "You have $500 starting capital and must pay a $2 daily fee. If you can't pay for 10 consecutive days, "
        "you go bankrupt.\n\n"
        "IMPORTANT - How the simulation works:\n"
        "- Customer purchases happen throughout each day based on demand\n"
        "- Each action you take advances simulation time (shown in response)\n"
        "- New customers only come when a new day starts\n"
        "- Use 'wait' to let time pass (1 hour) or 'end_day' to skip to the next day\n"
        "- Don't repeatedly check inventory/balance - take strategic actions instead!\n\n"
        "Product wholesale costs: chips=$0.75, candy=$0.60, soda=$0.80, water=$0.50, energy_drink=$1.50\n"
        "Default selling prices: chips=$1.50, candy=$1.25, soda=$2.00, water=$1.50, energy_drink=$3.00\n\n"
        "Demand factors:\n"
        "- Weather affects drink demand (hot/sunny = more drinks, cold/rainy = fewer)\n"
        "- Weekends have higher traffic than weekdays\n"
        "- Higher prices reduce demand, lower prices increase it\n\n"
        "CRITICAL - Restocking workflow:\n"
        "1. Order supplies by sending email to supplier@vendingsupply.com (deliveries take 2-5 days)\n"
        "2. Check emails regularly for 'Delivery Arrived' notifications\n"
        "3. When you see a delivery email, note the Order ID (e.g., 'ORD-ABC123')\n"
        "4. You MUST call the 'restock' tool with that Order ID as delivery_id to add items to inventory\n"
        "5. Without calling restock, delivered items will NOT appear in your inventory!\n\n"
        "Strategy tips:\n"
        "- Check inventory once, then decide on restocking needs\n"
        "- Order supplies BEFORE running out - plan 2-5 days ahead\n"
        "- Read emails daily to check for delivery notifications and restock immediately\n"
        "- Collect cash periodically to ensure you can pay the daily fee\n"
        "- Use 'end_day' to advance time efficiently after taking actions\n"
        "- Adjust prices based on weather and demand patterns"
    )

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return tool specs that produce VendingBench request messages."""
        return [
            ToolSpec(
                name="check_inventory",
                description="Check current inventory levels for all products. Takes 5 minutes.",
                parameter_class=CheckInventoryRequest,
            ),
            ToolSpec(
                name="check_balance",
                description="Check current cash balance, inventory value, and net worth. Takes 5 minutes.",
                parameter_class=CheckBalanceRequest,
            ),
            ToolSpec(
                name="set_price",
                description="Set the selling price for a product. Takes 75 minutes.",
                parameter_class=SetPriceRequest,
            ),
            ToolSpec(
                name="collect_cash",
                description="Collect cash from the vending machine to your operator account. Takes 5 hours.",
                parameter_class=CollectCashRequest,
            ),
            ToolSpec(
                name="read_emails",
                description="Read emails from your inbox. Takes 25 minutes.",
                parameter_class=ReadEmailsRequest,
            ),
            ToolSpec(
                name="send_email",
                description=(
                    "Send an email. To order supplies, send to 'supplier@vendingsupply.com' with products. "
                    "Example body: 'I'd like to order 20 chips, 15 candy, 30 soda'. Takes 75 minutes."
                ),
                parameter_class=SendEmailRequest,
            ),
            ToolSpec(
                name="restock",
                description=(
                    "Restock products from a delivered order into your vending machine inventory. "
                    "You MUST call this after receiving a 'Delivery Arrived' email to add items to inventory. "
                    "Pass the Order ID from the delivery email (e.g., 'ORD-ABC123') as the delivery_id parameter. "
                    "Without calling restock, your inventory will NOT be updated! Takes 5 hours."
                ),
                parameter_class=RestockRequest,
            ),
            ToolSpec(
                name="scratchpad_read",
                description="Read notes from your scratchpad memory. Takes 25 minutes.",
                parameter_class=ScratchpadReadRequest,
            ),
            ToolSpec(
                name="scratchpad_write",
                description="Write a note to your scratchpad memory for future reference. Takes 75 minutes.",
                parameter_class=ScratchpadWriteRequest,
            ),
            ToolSpec(
                name="wait",
                description=(
                    "Wait and let time pass. Use this to advance time without taking other actions. "
                    "Customers may make purchases while you wait. Takes 1 hour per hour waited (1-12 hours)."
                ),
                parameter_class=WaitRequest,
            ),
            ToolSpec(
                name="end_day",
                description=(
                    "End the current day and skip to the start of the next day. Use this after you've "
                    "taken your actions for the day. This is more efficient than waiting hour by hour. "
                    "A new day means new customers and new demand!"
                ),
                parameter_class=EndDayRequest,
            ),
        ]
