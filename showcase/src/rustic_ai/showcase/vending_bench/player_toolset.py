"""
VendingBench Player Toolset - Tools for interacting with VendingBench simulation via G2G.

This module provides VendingBenchToolspecsProvider for use with LLMAgent + ToolsManagerPlugin.
When the LLM calls a tool, the plugin produces the corresponding VendingBench request message
which gets routed via G2G to the VendingBench guild.
"""

from typing import List, Optional

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.tools.tools_manager_plugin import ToolspecsProvider

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
from .supplier_messages import (
    RespondToComplaintRequest,
    SupplierSearchRequest,
    ViewComplaintsRequest,
    ViewSuppliersRequest,
)


class VendingBenchToolspecsProvider(ToolspecsProvider):
    """
    Toolspecs provider for VendingBench that produces VendingBench request messages.

    Use this with LLMAgent's ToolsManagerPlugin. When the LLM calls a tool,
    the ToolsManagerPlugin will create the corresponding VendingBench request
    message which can then be routed via G2G to the VendingBench guild.
    """

    additional_system_prompt: Optional[str] = (
        "=== CRITICAL: AUTONOMOUS OPERATION ===\n"
        "You MUST call a tool on EVERY turn. Never respond with just text!\n"
        "After receiving a tool result, immediately call your next tool.\n\n"
        "=== FIRST ACTIONS (if no suppliers known) ===\n"
        "1. search_suppliers - You start with NO suppliers, must discover them first!\n"
        "2. check_inventory - See current stock levels\n"
        "3. check_balance - See available cash\n"
        "4. send_email to discovered supplier to order supplies\n"
        "5. end_day - Advance to let customers buy and deliveries progress\n\n"
        "=== DAILY LOOP (repeat this!) ===\n"
        "1. read_emails - Check for 'Delivery Arrived' notifications\n"
        "2. restock - If delivery arrived, use the Order ID to add items to inventory\n"
        "3. Strategic action (order more supplies, adjust prices, handle complaints)\n"
        "4. end_day - ALWAYS end with this to advance the simulation!\n\n"
        "=== SUPPLIER WORKFLOW ===\n"
        "search_suppliers → view_suppliers → send_email (e.g., 'Order 20 chips, 15 soda')\n"
        ">>> Deliveries take 2-5 days - order BEFORE running out! <<<\n\n"
        "=== RESTOCK WORKFLOW ===\n"
        "read_emails → find 'Order ID: ORD-XXXXX' → call restock with that ID\n"
        ">>> Items sit in warehouse until you call restock! <<<\n\n"
        "=== SUPPLIER TYPES ===\n"
        "- HONEST: Reliable, fair prices - use for critical orders\n"
        "- ADVERSARIAL: May overcharge - use cautiously\n"
        "- UNRELIABLE: May delay/fail - have backups\n\n"
        "=== ADAPT TO SITUATION ===\n"
        "- Low cash (< $50): collect_cash first\n"
        "- Low inventory (< 5 items): Order urgently\n"
        "- Hot weather: Stock drinks (soda, water, energy_drink)\n"
        "- Complaints pending: view_complaints → respond_complaint\n\n"
        "=== TIME EFFICIENCY ===\n"
        "- Don't spam check_inventory/check_balance - act on what you know\n"
        "- Use end_day frequently to progress the simulation\n"
        "- Each action takes simulation time - be purposeful\n\n"
        "REMEMBER: Always call a tool. Progress the simulation by calling end_day after your daily actions!"
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
                    "Send an email to a discovered supplier to order supplies. IMPORTANT: You MUST first use "
                    "'search_suppliers' to discover suppliers, then use 'view_suppliers' to see valid email "
                    "addresses. You cannot send to unknown suppliers! Example body: 'I'd like to order 20 chips, "
                    "15 candy, 30 soda'. Takes 75 minutes."
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
            # New supplier discovery and management tools
            ToolSpec(
                name="search_suppliers",
                description=(
                    "Search for new suppliers in a specific region. Returns a list of discovered "
                    "suppliers with their pricing and reliability. Different suppliers may have "
                    "better prices but vary in reliability. Takes 60 minutes."
                ),
                parameter_class=SupplierSearchRequest,
            ),
            ToolSpec(
                name="view_suppliers",
                description=(
                    "View all known suppliers and their details including pricing, reliability, "
                    "and behavior type (honest/adversarial/unreliable). Takes 5 minutes."
                ),
                parameter_class=ViewSuppliersRequest,
            ),
            # Customer complaint management tools
            ToolSpec(
                name="view_complaints",
                description=(
                    "View open customer complaints that need attention. Shows complaint type, "
                    "refund requested, and days open. Unresolved complaints hurt reputation. Takes 5 minutes."
                ),
                parameter_class=ViewComplaintsRequest,
            ),
            ToolSpec(
                name="respond_complaint",
                description=(
                    "Respond to a customer complaint. Actions: 'refund' (full refund, reputation gain), "
                    "'partial_refund' (partial refund), 'deny' (no refund, reputation loss), "
                    "'apologize' (no refund, small reputation gain). Takes 30 minutes."
                ),
                parameter_class=RespondToComplaintRequest,
            ),
        ]
