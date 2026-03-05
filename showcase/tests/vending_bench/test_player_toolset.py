"""Tests for the VendingBench player toolset."""

import pytest

from rustic_ai.showcase.vending_bench.messages import (
    CheckBalanceRequest,
    CheckInventoryRequest,
    CollectCashRequest,
    ReadEmailsRequest,
    RestockRequest,
    ScratchpadReadRequest,
    ScratchpadWriteRequest,
    SendEmailRequest,
    SetPriceRequest,
)
from rustic_ai.showcase.vending_bench.player_toolset import (
    VendingBenchToolspecsProvider,
)


class TestVendingBenchToolspecsProvider:
    """Tests for VendingBenchToolspecsProvider."""

    @pytest.fixture
    def provider(self) -> VendingBenchToolspecsProvider:
        """Create a provider instance."""
        return VendingBenchToolspecsProvider()

    def test_provider_has_all_tools(self, provider: VendingBenchToolspecsProvider):
        """Test that provider has all expected tools."""
        tool_specs = provider.get_toolspecs()
        tool_names = [t.name for t in tool_specs]

        expected_tools = [
            "check_inventory",
            "check_balance",
            "set_price",
            "collect_cash",
            "read_emails",
            "send_email",
            "restock",
            "scratchpad_read",
            "scratchpad_write",
            "search_suppliers",
            "view_suppliers",
            "view_complaints",
            "respond_complaint",
        ]
        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"

    def test_provider_tools_use_vending_bench_message_types(self, provider: VendingBenchToolspecsProvider):
        """Test that tools use VendingBench message types as parameter classes."""
        tool_specs = provider.get_toolspecs()
        tools_by_name = {t.name: t for t in tool_specs}

        # Verify parameter classes are the VendingBench request types
        assert tools_by_name["check_inventory"].parameter_class == CheckInventoryRequest
        assert tools_by_name["check_balance"].parameter_class == CheckBalanceRequest
        assert tools_by_name["set_price"].parameter_class == SetPriceRequest
        assert tools_by_name["collect_cash"].parameter_class == CollectCashRequest
        assert tools_by_name["read_emails"].parameter_class == ReadEmailsRequest
        assert tools_by_name["send_email"].parameter_class == SendEmailRequest
        assert tools_by_name["restock"].parameter_class == RestockRequest
        assert tools_by_name["scratchpad_read"].parameter_class == ScratchpadReadRequest
        assert tools_by_name["scratchpad_write"].parameter_class == ScratchpadWriteRequest

    def test_provider_has_additional_system_prompt(self, provider: VendingBenchToolspecsProvider):
        """Test that provider has an additional system prompt."""
        assert provider.additional_system_prompt is not None
        assert "vending machine" in provider.additional_system_prompt.lower()

    def test_provider_chat_tools(self, provider: VendingBenchToolspecsProvider):
        """Test that provider can generate chat tools for LLM."""
        chat_tools = provider.chat_tools
        assert len(chat_tools) == 15  # 11 original + 4 new supplier/complaint tools

        # Verify structure of a chat tool
        tool_names = [t.function.name for t in chat_tools]
        assert "check_inventory" in tool_names
        assert "set_price" in tool_names

    def test_provider_get_toolspec_by_name(self, provider: VendingBenchToolspecsProvider):
        """Test getting a specific toolspec by name."""
        spec = provider.get_toolspec_by_name("set_price")
        assert spec is not None
        assert spec.name == "set_price"
        assert spec.parameter_class == SetPriceRequest

        # Test non-existent tool
        assert provider.get_toolspec_by_name("nonexistent") is None

    def test_provider_toolspecs_by_name_cached(self, provider: VendingBenchToolspecsProvider):
        """Test that toolspecs_by_name is properly cached."""
        # Access the property twice
        first_access = provider.toolspecs_by_name
        second_access = provider.toolspecs_by_name

        # Should be the same object (cached)
        assert first_access is second_access
        assert len(first_access) == 15  # 11 original + 4 new supplier/complaint tools

    def test_set_price_tool_has_required_fields(self, provider: VendingBenchToolspecsProvider):
        """Test that SetPriceRequest tool has the correct parameter schema."""
        spec = provider.get_toolspec_by_name("set_price")
        chat_tool = spec.chat_tool

        # Verify the function has correct parameters
        params = chat_tool.function.parameters
        properties = params.properties if hasattr(params, "properties") else {}
        assert "product" in properties
        assert "new_price" in properties

    def test_send_email_tool_has_required_fields(self, provider: VendingBenchToolspecsProvider):
        """Test that SendEmailRequest tool has the correct parameter schema."""
        spec = provider.get_toolspec_by_name("send_email")
        chat_tool = spec.chat_tool

        # Verify the function has correct parameters
        params = chat_tool.function.parameters
        properties = params.properties if hasattr(params, "properties") else {}
        assert "to_address" in properties
        assert "subject" in properties
        assert "body" in properties
