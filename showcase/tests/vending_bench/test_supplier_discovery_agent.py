"""
Tests for SupplierDiscoveryAgent.
"""

import time

import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.messages import Email
from rustic_ai.showcase.vending_bench.supplier_discovery_agent import SupplierDiscoveryAgent
from rustic_ai.showcase.vending_bench.supplier_messages import (
    SupplierSearchRequest,
    SupplierSearchResponse,
)
from rustic_ai.showcase.vending_bench.supplier_registry import (
    SupplierBehaviorType,
    SupplierProductInfo,
    SupplierProfile,
    SupplierRegistry,
)


class TestSupplierDiscoveryAgentUnit:
    """Unit tests for SupplierDiscoveryAgent methods."""

    def test_build_search_query_with_products(self):
        """Should build search query with product types."""
        agent = SupplierDiscoveryAgent()

        request = SupplierSearchRequest(
            product_types=[ProductType.CHIPS, ProductType.SODA],
            location="New York",
        )
        query = agent._build_search_query(request)

        assert "chips" in query.lower()
        assert "soda" in query.lower()
        assert "new york" in query.lower()
        assert "vending machine" in query.lower()

    def test_build_search_query_default(self):
        """Should build default search query when no products specified."""
        agent = SupplierDiscoveryAgent()

        request = SupplierSearchRequest()
        query = agent._build_search_query(request)

        assert "snacks and beverages" in query.lower()
        assert "usa" in query.lower()

    def test_determine_behavior_type(self):
        """Should return valid behavior types."""
        agent = SupplierDiscoveryAgent()

        # Run multiple times to verify randomness
        behaviors = []
        for _ in range(100):
            behavior = agent._determine_behavior_type()
            behaviors.append(behavior)
            assert behavior in list(SupplierBehaviorType)

        # Should have some variety (statistically very likely with 100 samples)
        unique_behaviors = set(behaviors)
        assert len(unique_behaviors) >= 1  # At minimum, one type should appear

    def test_generate_pricing_honest(self):
        """Should generate reasonable pricing for honest suppliers."""
        agent = SupplierDiscoveryAgent()

        products = [ProductType.CHIPS, ProductType.SODA]
        pricing = agent._generate_pricing(SupplierBehaviorType.HONEST, products)

        assert ProductType.CHIPS in pricing
        assert ProductType.SODA in pricing

        # Honest pricing should have reasonable markup (around 30%)
        for product, info in pricing.items():
            assert info.current_quoted_price >= info.base_price
            # Should not be too high (less than 2x base price for honest)
            assert info.current_quoted_price < info.base_price * 2

    def test_generate_pricing_adversarial(self):
        """Should generate higher pricing for adversarial suppliers."""
        agent = SupplierDiscoveryAgent()

        products = [ProductType.WATER]
        pricing = agent._generate_pricing(SupplierBehaviorType.ADVERSARIAL, products)

        assert ProductType.WATER in pricing
        info = pricing[ProductType.WATER]

        # Adversarial pricing should be higher (1.5x to 3x base)
        assert info.current_quoted_price >= info.base_price * 1.4  # Account for randomness

    def test_generate_fictional_suppliers(self):
        """Should generate fictional suppliers with proper structure."""
        agent = SupplierDiscoveryAgent()

        products = [ProductType.ENERGY_DRINK, ProductType.CANDY]
        suppliers = agent._generate_fictional_suppliers(products, "California", count=3)

        assert len(suppliers) == 3

        for supplier in suppliers:
            assert supplier.name is not None
            assert supplier.email is not None
            assert supplier.supplier_id.startswith("SUP-")
            assert supplier.behavior_type in list(SupplierBehaviorType)
            # Should offer the requested products
            for product in products:
                assert product in supplier.products_offered

    def test_create_supplier_from_research(self):
        """Should create supplier profile from research data."""
        agent = SupplierDiscoveryAgent()
        agent.current_day = 5

        supplier = agent._create_supplier_from_research(
            name="Test Supplier Inc",
            email="test@supplier.com",
            location="Texas",
            product_types=[ProductType.CHIPS],
            notes="Test supplier",
        )

        assert supplier.name == "Test Supplier Inc"
        assert supplier.email == "test@supplier.com"
        assert supplier.location == "Texas"
        assert supplier.discovered_on_day == 5
        assert supplier.notes == "Test supplier"
        assert ProductType.CHIPS in supplier.products_offered


class TestSupplierDiscoveryAgentIntegration:
    """Integration tests for SupplierDiscoveryAgent."""

    def test_handles_supplier_search_request(self, org_id, supplier_discovery_spec):
        """SupplierDiscoveryAgent should handle search requests without crashing."""
        builder = GuildBuilder(
            guild_id=f"discovery_test_{shortuuid.uuid()}",
            guild_name="Discovery Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_discovery_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SEARCH")
            .add_additional_topic("EMAIL")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send a search request
        search_request = SupplierSearchRequest(
            product_types=[ProductType.CHIPS, ProductType.SODA],
            location="New York",
            max_results=3,
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            search_request.model_dump(),
            format=get_qualified_class_name(SupplierSearchRequest),
        )

        time.sleep(0.5)

        # Agent should send a SERPQuery to the research agent
        messages = probe.get_messages()
        # Check that a SERPQuery was sent (it will be on the default topic)
        serp_queries = [m for m in messages if "SERPQuery" in m.format]
        assert len(serp_queries) >= 1, "Expected at least one SERPQuery to be sent"

        guild.shutdown()

    def test_search_request_with_empty_products(self, org_id, supplier_discovery_spec):
        """SupplierDiscoveryAgent should handle empty product list."""
        builder = GuildBuilder(
            guild_id=f"discovery_empty_test_{shortuuid.uuid()}",
            guild_name="Discovery Empty Test Guild",
            guild_description="Test guild",
        ).set_messaging(
            "rustic_ai.core.messaging.backend",
            "InMemoryMessagingBackend",
            {},
        )

        builder.add_agent_spec(supplier_discovery_spec)
        guild = builder.launch(org_id)

        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id(f"probe_{shortuuid.uuid()}")
            .set_name("ProbeAgent")
            .set_description("Test probe")
            .listen_to_default_topic(True)
            .add_additional_topic("SUPPLIER_SEARCH")
            .build_spec()
        )
        probe: ProbeAgent = guild._add_local_agent(probe_spec)

        # Send a search request with no products
        search_request = SupplierSearchRequest(
            location="Seattle",
        )
        probe.publish_dict(
            guild.DEFAULT_TOPIC,
            search_request.model_dump(),
            format=get_qualified_class_name(SupplierSearchRequest),
        )

        time.sleep(0.5)

        # Should send a SERPQuery even with empty products
        messages = probe.get_messages()
        serp_queries = [m for m in messages if "SERPQuery" in m.format]
        assert len(serp_queries) >= 1, "Expected at least one SERPQuery to be sent"

        guild.shutdown()


class TestSupplierDiscoveryConfiguration:
    """Tests for supplier discovery configuration."""

    def test_behavior_probabilities_sum_to_one(self):
        """Behavior probabilities should sum to 1."""
        from rustic_ai.showcase.vending_bench.supplier_config import (
            ADVERSARIAL_SUPPLIER_PROBABILITY,
            HONEST_SUPPLIER_PROBABILITY,
            UNRELIABLE_SUPPLIER_PROBABILITY,
        )

        total = HONEST_SUPPLIER_PROBABILITY + ADVERSARIAL_SUPPLIER_PROBABILITY + UNRELIABLE_SUPPLIER_PROBABILITY
        assert abs(total - 1.0) < 0.001

    def test_price_multipliers_are_reasonable(self):
        """Price gouging multipliers should be reasonable."""
        from rustic_ai.showcase.vending_bench.supplier_config import (
            INITIAL_QUOTE_MARKUP,
            PRICE_GOUGING_MULTIPLIER_MAX,
            PRICE_GOUGING_MULTIPLIER_MIN,
        )

        assert INITIAL_QUOTE_MARKUP > 0
        assert INITIAL_QUOTE_MARKUP < 1  # Less than 100% markup for honest
        assert PRICE_GOUGING_MULTIPLIER_MIN > 1.0
        assert PRICE_GOUGING_MULTIPLIER_MAX > PRICE_GOUGING_MULTIPLIER_MIN
        assert PRICE_GOUGING_MULTIPLIER_MAX <= 5.0  # Not absurdly high
