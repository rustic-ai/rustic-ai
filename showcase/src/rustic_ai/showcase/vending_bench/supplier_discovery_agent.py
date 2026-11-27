"""
SupplierDiscoveryAgent - Discovers new suppliers via Google Research.

This agent:
- Handles supplier search requests
- Integrates with GoogleResearchAgent for web-based discovery
- Creates supplier profiles with randomized behavior types
- Maintains a registry of discovered suppliers
"""

import logging
import random
import re
from typing import Dict, List, Optional

from pydantic import Field
import shortuuid

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.state.models import StateOwner, StateUpdateFormat
from rustic_ai.serpapi.agent import SERPQuery
from rustic_ai.showcase.vending_bench.config import DEFAULT_COSTS, ProductType
from rustic_ai.showcase.vending_bench.messages import Email
from rustic_ai.showcase.vending_bench.state_keys import (
    CURRENT_DAY,
    PENDING_SUPPLIER_SEARCHES,
    SUPPLIER_REGISTRY,
)
from rustic_ai.showcase.vending_bench.supplier_config import (
    ADVERSARIAL_SUPPLIER_PROBABILITY,
    HONEST_SUPPLIER_PROBABILITY,
    INITIAL_QUOTE_MARKUP,
    OPERATOR_EMAIL,
    PRICE_GOUGING_MULTIPLIER_MAX,
    PRICE_GOUGING_MULTIPLIER_MIN,
)
from rustic_ai.showcase.vending_bench.supplier_messages import (
    SupplierSearchRequest,
    SupplierSearchResponse,
    ViewSuppliersRequest,
    build_supplier_view,
)
from rustic_ai.showcase.vending_bench.supplier_registry import (
    SupplierBehaviorType,
    SupplierProductInfo,
    SupplierProfile,
    SupplierRegistry,
)

logger = logging.getLogger(__name__)


class SupplierDiscoveryAgentProps(BaseAgentProps):
    """Configuration for SupplierDiscoveryAgent."""

    search_timeout_minutes: int = Field(default=60, description="Time cost for supplier search")
    max_suppliers_per_search: int = Field(default=3, description="Max suppliers to return per search")


class SupplierDiscoveryAgent(Agent[SupplierDiscoveryAgentProps]):
    """Agent that discovers new suppliers via web research.

    Integrates with GoogleResearchAgent to search for suppliers and
    creates supplier profiles with randomized behavior types.
    """

    def __init__(self):
        self.pending_searches: Dict[str, SupplierSearchRequest] = {}
        self._pending_completions: dict[str, tuple[ProcessContext, Optional[Email], SupplierSearchResponse]] = {}
        self.registry: SupplierRegistry = SupplierRegistry()
        self.current_day: int = 1

    def _load_state_from_guild(self):
        """Load persisted state from guild state."""
        guild_state = self.get_guild_state() or {}

        # Load registry
        registry_data = guild_state.get(SUPPLIER_REGISTRY)
        if registry_data:
            self.registry = SupplierRegistry(**registry_data) if isinstance(registry_data, dict) else registry_data

        # Load current day
        self.current_day = guild_state.get(CURRENT_DAY, 1)

        # Load pending searches
        searches_data = guild_state.get(PENDING_SUPPLIER_SEARCHES, {})
        self.pending_searches = {
            k: SupplierSearchRequest(**v) if isinstance(v, dict) else v
            for k, v in searches_data.items()
            if k not in self._pending_completions
        }

    def _persist_state(self, ctx: ProcessContext, completed_search_id: Optional[str] = None):
        """Persist current state to guild state."""
        pending: dict[str, Optional[dict]] = {k: v.model_dump() for k, v in self.pending_searches.items()}
        if completed_search_id:
            # An empty merge-patch object preserves its old keys; null deletes one.
            pending[completed_search_id] = None
        self.update_guild_state(
            ctx,
            update_format=StateUpdateFormat.JSON_MERGE_PATCH,
            update={
                SUPPLIER_REGISTRY: self.registry.model_dump(),
                PENDING_SUPPLIER_SEARCHES: pending,
            },
        )

    def _build_search_query(self, request: SupplierSearchRequest) -> str:
        """Build a search query for supplier discovery."""
        products = (
            ", ".join(p.value.replace("_", " ") for p in request.product_types)
            if request.product_types
            else "snacks and beverages"
        )
        location = request.location or "USA"
        return f"vending machine {products} wholesaler supplier near {location}"

    def _determine_behavior_type(self) -> SupplierBehaviorType:
        """Randomly determine supplier behavior type based on probabilities."""
        roll = random.random()
        if roll < HONEST_SUPPLIER_PROBABILITY:
            return SupplierBehaviorType.HONEST
        elif roll < HONEST_SUPPLIER_PROBABILITY + ADVERSARIAL_SUPPLIER_PROBABILITY:
            return SupplierBehaviorType.ADVERSARIAL
        else:
            return SupplierBehaviorType.UNRELIABLE

    def _generate_pricing(
        self, behavior_type: SupplierBehaviorType, product_types: Optional[List[ProductType]] = None
    ) -> Dict[ProductType, SupplierProductInfo]:
        """Generate product pricing based on supplier behavior type."""
        products = product_types if product_types else list(ProductType)
        result = {}

        for product in products:
            base_cost = DEFAULT_COSTS.get(product, 1.0)

            # Calculate quoted price based on behavior type
            if behavior_type == SupplierBehaviorType.ADVERSARIAL:
                # Adversarial suppliers gouge prices
                multiplier = random.uniform(PRICE_GOUGING_MULTIPLIER_MIN, PRICE_GOUGING_MULTIPLIER_MAX)
                quoted_price = base_cost * multiplier
            else:
                # Honest and unreliable suppliers use normal markup
                quoted_price = base_cost * (1 + INITIAL_QUOTE_MARKUP)

            # Add some variation
            quoted_price *= random.uniform(0.95, 1.05)

            result[product] = SupplierProductInfo(
                base_price=base_cost,
                current_quoted_price=round(quoted_price, 2),
                min_order_quantity=random.choice([5, 10, 15, 20]),
                in_stock=random.random() > 0.1,  # 10% chance out of stock
                lead_time_days=random.randint(2, 7),
            )

        return result

    def _create_supplier_from_research(
        self, name: str, email: str, location: str, product_types: List[ProductType], notes: str = ""
    ) -> SupplierProfile:
        """Create a supplier profile from research results."""
        behavior_type = self._determine_behavior_type()

        # Set reliability score based on behavior type
        if behavior_type == SupplierBehaviorType.HONEST:
            reliability = random.uniform(0.85, 1.0)
        elif behavior_type == SupplierBehaviorType.ADVERSARIAL:
            reliability = random.uniform(0.6, 0.85)
        else:  # Unreliable
            reliability = random.uniform(0.3, 0.6)

        return SupplierProfile(
            name=name,
            email=email,
            products_offered=self._generate_pricing(behavior_type, product_types),
            behavior_type=behavior_type,
            reliability_score=round(reliability, 2),
            negotiation_flexibility=random.uniform(0.10, 0.25),
            discovered_on_day=self.current_day,
            location=location,
            notes=notes,
        )

    def _generate_fictional_suppliers(
        self, product_types: List[ProductType], location: str, count: int = 3
    ) -> List[SupplierProfile]:
        """Generate fictional suppliers when search doesn't return real results."""
        supplier_names = [
            ("Metro Vending Supply", "metro"),
            ("QuickSnack Distributors", "quicksnack"),
            ("National Beverage Wholesale", "nationalbev"),
            ("FreshStock Supplies", "freshstock"),
            ("VendMaster Inc", "vendmaster"),
            ("SnackPro Distributors", "snackpro"),
            ("BulkBuy Wholesale", "bulkbuy"),
            ("Premier Vending Solutions", "premvending"),
        ]

        selected = random.sample(supplier_names, min(count, len(supplier_names)))
        suppliers = []

        for name, email_prefix in selected:
            supplier = self._create_supplier_from_research(
                name=name,
                email=f"orders@{email_prefix}.com",
                location=location or "USA",
                product_types=product_types or list(ProductType),
                notes="Discovered via supplier search",
            )
            suppliers.append(supplier)

        return suppliers

    @agent.processor(SupplierSearchRequest)
    def handle_search_request(self, ctx: ProcessContext[SupplierSearchRequest]):
        """Handle initial supplier search request."""
        self._load_state_from_guild()

        request = ctx.payload
        query = self._build_search_query(request)

        # Store pending search for correlation
        search_id = f"SEARCH-{shortuuid.uuid()[:8]}"
        self.pending_searches[search_id] = request
        ctx.update_context({"supplier_search_id": search_id})

        # Publish correlation state before the research capability can reply.
        # Synchronous guilds may deliver the response during ctx.send itself.
        self._persist_state(ctx)

        # Send search query to Google Research Agent
        serp_query = SERPQuery(engine="google", query=query, id=search_id, num=10)
        ctx.send(serp_query)

        logger.info(f"Initiated supplier search: {query}")

    @agent.processor(ChatCompletionResponse)
    def handle_research_response(self, ctx: ProcessContext[ChatCompletionResponse]):
        """Handle response from Google Research Agent."""
        # State publication and the research reply may run in different agent
        # mailboxes. Keep this owner's admitted searches while refreshing the
        # persisted registry; a late state snapshot must not erase correlation.
        pending = dict(self.pending_searches)
        self._load_state_from_guild()
        self.pending_searches.update(pending)

        response = ctx.payload

        # Extract the research results
        if not response.choices or not response.choices[0].message:
            logger.warning("Empty research response received")
            return

        research_content = response.choices[0].message.content or ""

        # Google Research gives its response a fresh ID; the originating search
        # identity travels in message context throughout the capability call.
        search_id = ctx.get_context().get("supplier_search_id")
        if not isinstance(search_id, str) or search_id not in self.pending_searches:
            logger.warning("Ignoring research response for an unknown or completed search")
            return
        if search_id in self._pending_completions:
            return
        original_request = self.pending_searches.pop(search_id)

        # Use LLM to parse research results and create supplier profiles
        suppliers = self._parse_research_and_create_suppliers(
            research_content, original_request.product_types, original_request.location
        )

        # Add suppliers to registry
        for supplier in suppliers:
            self.registry.add_supplier(supplier)

        email: Optional[Email] = None

        # Send email notification about discovered suppliers
        if suppliers:
            supplier_list = "\n".join(f"- {s.name} ({s.email}) - {s.behavior_type.value} type" for s in suppliers)
            email = Email(
                from_address="system@vendingbench.sim",
                to_address=OPERATOR_EMAIL,
                subject="Supplier Search Results",
                body=f"""Your supplier search has completed!

Search query: {self._build_search_query(original_request)}

Found {len(suppliers)} new suppliers:
{supplier_list}

You can now contact these suppliers via email to place orders.
Use 'view_suppliers' to see all known suppliers and their details.""",
            )

        # Send response
        search_response = SupplierSearchResponse(
            request_id=original_request.request_id,
            suppliers_found=suppliers,
            search_query=self._build_search_query(original_request),
            time_elapsed_minutes=self.config.search_timeout_minutes,
            message=f"Found {len(suppliers)} suppliers",
        )
        # The player may immediately ask another agent to read this registry.
        # Wait for authoritative state publication before announcing completion.
        self._pending_completions[search_id] = (ctx, email, search_response)
        self._persist_state(ctx, completed_search_id=search_id)

        logger.info(f"Discovered {len(suppliers)} suppliers from research")

    def on_state_updated(self, new_state, ctx):
        if ctx.payload.state_owner != StateOwner.GUILD:
            return
        registry = new_state.get(SUPPLIER_REGISTRY, {}).get("suppliers", {})
        pending = new_state.get(PENDING_SUPPLIER_SEARCHES, {})
        for search_id, (origin, email, response) in list(self._pending_completions.items()):
            required = {supplier.supplier_id for supplier in response.suppliers_found}
            if search_id not in pending and required.issubset(registry):
                self._pending_completions.pop(search_id)
                if email:
                    origin.send(email)
                origin.send(response)

    @agent.processor(ViewSuppliersRequest)
    def handle_view_suppliers(self, ctx: ProcessContext[ViewSuppliersRequest]):
        """Read the published registry from its owner rather than another agent's cache."""
        self._load_state_from_guild()
        ctx.send(build_supplier_view(self.registry, ctx.payload))

    def _parse_research_and_create_suppliers(
        self, research_content: str, product_types: List[ProductType], location: str
    ) -> List[SupplierProfile]:
        """Parse research results and create supplier profiles.

        Attempts to extract supplier information from the research content.
        Falls back to generating fictional suppliers if parsing yields no results.
        """
        suppliers: List[SupplierProfile] = []
        products = product_types if product_types else list(ProductType)

        # Try to parse supplier names from research content
        # Look for common patterns in research results
        # Extract potential company names and emails from research
        # Pattern for company names (words ending in common business suffixes)
        company_patterns = [
            r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*"
            r"(?:\s+(?:Inc|LLC|Co|Corp|Supply|Wholesale|Distributors?|Company)\.?))",
            r"([A-Z][a-zA-Z]+(?:Supply|Snacks?|Beverage|Vending|Food|Wholesale|Distribution))",
        ]

        # Pattern for emails
        email_pattern = r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

        found_companies = set()
        found_emails = []

        # Extract company names
        for pattern in company_patterns:
            matches = re.findall(pattern, research_content)
            for match in matches:
                if len(match) > 3 and match not in found_companies:
                    found_companies.add(match.strip())

        # Extract emails
        email_matches = re.findall(email_pattern, research_content)
        found_emails.extend(email_matches)

        # Create suppliers from extracted info
        company_list = list(found_companies)[: self.config.max_suppliers_per_search]

        for i, company_name in enumerate(company_list):
            # Use found email or generate one
            if i < len(found_emails):
                email = found_emails[i]
            else:
                # Generate email from company name
                clean_name = re.sub(r"[^a-zA-Z]", "", company_name.lower())
                email = f"orders@{clean_name[:15]}.com"

            supplier = self._create_supplier_from_research(
                name=company_name,
                email=email,
                location=location or "USA",
                product_types=products,
                notes=f"Discovered via web research: {research_content[:100]}...",
            )
            suppliers.append(supplier)

        # If we didn't find enough suppliers from research, generate fictional ones
        remaining_count = self.config.max_suppliers_per_search - len(suppliers)
        if remaining_count > 0:
            logger.info(f"Found {len(suppliers)} suppliers from research, generating {remaining_count} additional")
            fictional = self._generate_fictional_suppliers(products, location, remaining_count)
            suppliers.extend(fictional)

        logger.info(f"Created {len(suppliers)} suppliers from research content ({len(company_list)} from parsing)")
        return suppliers
