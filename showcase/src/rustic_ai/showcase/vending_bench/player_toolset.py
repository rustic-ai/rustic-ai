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
        "=== MOST IMPORTANT: RESTOCKING ===\n"
        "Your inventory will run out! You MUST restock to continue selling. Here's the REQUIRED workflow:\n\n"
        "STEP 1 - ORDER: Send email to supplier@vendingsupply.com\n"
        "   Example: 'I'd like to order 20 chips, 25 candy, 30 soda, 30 water, 15 energy_drink'\n"
        "   Deliveries take 2-5 days, so ORDER EARLY before running out!\n\n"
        "STEP 2 - WAIT: Use 'end_day' to advance time until delivery day arrives\n\n"
        "STEP 3 - CHECK: Call 'read_emails' to look for 'Delivery Arrived' emails\n"
        "   The email will contain an Order ID like 'ORD-ABC123'\n\n"
        "STEP 4 - RESTOCK: Call 'restock' with delivery_id='ORD-ABC123'\n"
        "   >>> WITHOUT THIS STEP, ITEMS STAY IN WAREHOUSE AND NEVER ENTER YOUR INVENTORY! <<<\n\n"
        "DAILY ROUTINE (do this EVERY day):\n"
        "1. read_emails - Check for 'Delivery Arrived' notifications\n"
        "2. restock - If delivery arrived, call restock with the Order ID immediately\n"
        "3. check_inventory - See what's running low\n"
        "4. send_email - Order more supplies if inventory < 10 for any product\n"
        "5. end_day - Advance to next day\n\n"
        "=== Simulation mechanics ===\n"
        "- Customer purchases happen throughout each day based on demand\n"
        "- Each action advances simulation time (shown in response)\n"
        "- Use 'end_day' to skip to next day after taking your actions\n\n"
        "Product costs: chips=$0.75, candy=$0.60, soda=$0.80, water=$0.50, energy_drink=$1.50\n"
        "Selling prices: chips=$1.50, candy=$1.25, soda=$2.00, water=$1.50, energy_drink=$3.00\n\n"
        "Demand factors:\n"
        "- Hot/sunny weather = more drink sales\n"
        "- Weekends = higher traffic\n"
        "- Higher prices = lower demand\n\n"
        "Strategy tips:\n"
        "- Order supplies BEFORE running out (plan 2-5 days ahead)\n"
        "- Always check emails after advancing days - deliveries arrive overnight\n"
        "- Collect cash periodically to pay the daily fee"
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
                description=(
                    "Read emails from your inbox. IMPORTANT: Check for 'Delivery Arrived' emails! "
                    "When you see one, extract the Order ID (e.g., 'ORD-ABC123') and immediately call "
                    "'restock' with that ID to add items to your inventory. Takes 25 minutes."
                ),
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
                    "End the current day and skip to the start of the next day. AFTER calling this, "
                    "always call 'read_emails' to check if any deliveries arrived overnight! "
                    "If you see a 'Delivery Arrived' email, call 'restock' immediately with the Order ID."
                ),
                parameter_class=EndDayRequest,
            ),
        ]
