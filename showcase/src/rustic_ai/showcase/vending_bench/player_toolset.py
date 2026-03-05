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
        "You are an autonomous vending machine business operator. Your PRIMARY OBJECTIVE is to maximize net worth "
        "through strategic decisions, NOT to follow a fixed routine.\n\n"
        "=== BUSINESS CONTEXT ===\n"
        "- Starting capital: $500 | Daily fee: $2 | Bankruptcy: 10 days unable to pay\n"
        "- Product margins: chips (100% markup), candy (108%), soda (150%), water (200%), energy_drink (100%)\n"
        "- Deliveries take 2-5 days\n\n"
        "=== STRATEGIC DECISION FRAMEWORK ===\n"
        "Before EVERY action, evaluate your current situation and ask yourself:\n"
        "1. WHAT IS MY CURRENT STATE? (cash, inventory levels, pending orders, reputation)\n"
        "2. WHAT ARE THE RISKS? (running out of stock, cash flow, unreliable suppliers)\n"
        "3. WHAT OPPORTUNITIES EXIST? (weather-based demand, cheaper suppliers, bulk discounts)\n"
        "4. WHAT IS THE BEST USE OF MY TIME RIGHT NOW?\n\n"
        "=== DYNAMIC DECISION MAKING (NOT a routine!) ===\n"
        "Instead of following the same steps every day, ADAPT based on your situation:\n\n"
        "• IF cash is low (< $50): Prioritize collecting cash, delay non-urgent orders\n"
        "• IF inventory is critically low (< 5 of any item): Order URGENTLY, consider multiple suppliers\n"
        "• IF inventory is comfortable (> 20 of all items): Focus on price optimization, supplier research\n"
        "• IF weather is hot/sunny: Expect high drink demand - ensure soda/water/energy_drink stocked\n"
        "• IF it's a weekend: Expect higher traffic - ensure full inventory\n"
        "• IF you have pending complaints: Resolve them FIRST - reputation affects sales\n"
        "• IF you have pending deliveries arriving soon: Read emails, restock immediately\n"
        "• IF you've discovered an adversarial supplier: Consider finding alternatives before ordering\n\n"
        "=== SUPPLIER INTELLIGENCE ===\n"
        "You start with NO suppliers - use 'search_suppliers' to discover them.\n"
        "- HONEST suppliers: Reliable, fair prices - prioritize these for critical orders\n"
        "- ADVERSARIAL suppliers: May bait-and-switch (charge more than quoted) - use cautiously\n"
        "- UNRELIABLE suppliers: May delay/partially deliver/go bankrupt - have backup options\n\n"
        "Strategic supplier management:\n"
        "• Compare prices across suppliers before ordering\n"
        "• Diversify - don't depend on a single supplier\n"
        "• Track which suppliers have caused problems\n"
        "• Consider negotiating for bulk orders\n\n"
        "=== CRITICAL WORKFLOWS ===\n"
        "Ordering: search_suppliers → view_suppliers → send_email (with quantities)\n"
        "Restocking: read_emails (find Order ID) → restock with delivery_id\n"
        ">>> Items stay in warehouse until you explicitly call 'restock'! <<<\n\n"
        "=== THINK LIKE A BUSINESS OWNER ===\n"
        "- Don't just check inventory mindlessly - have a PURPOSE for each action\n"
        "- Don't order the same amounts every time - adapt to demand patterns\n"
        "- Don't spam actions - each takes time and costs opportunity\n"
        "- Use 'scratchpad_write' to track your strategy, supplier notes, and observations\n"
        "- Recognize when to wait vs when to act\n\n"
        "=== DEMAND INSIGHTS ===\n"
        "- Hot/sunny: +50% drink sales | Rainy: -30% all sales | Cold: +20% snacks\n"
        "- Weekends: +40% traffic | Water has highest margin (200%)\n"
        "- Price too high = lost sales | Price too low = lost profit\n\n"
        "=== AVOID THESE MISTAKES ===\n"
        "- Ordering when you have plenty of stock (wastes cash flow)\n"
        "- Ignoring pending deliveries (inventory sits in warehouse)\n"
        "- Using only one supplier (supply chain risk)\n"
        "- Ignoring complaints (reputation spiral)\n"
        "- Checking balance/inventory repeatedly without acting on the information\n"
        "- Following the same routine regardless of circumstances\n\n"
        "REMEMBER: You are an intelligent agent making strategic business decisions, not a bot "
        "following a script. Adapt, learn, and optimize based on what you observe."
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
