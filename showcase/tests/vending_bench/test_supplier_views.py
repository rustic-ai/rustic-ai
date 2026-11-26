"""Shared supplier-view protocol semantics for owner and compatibility handlers."""

import pytest

from rustic_ai.showcase.vending_bench.config import ProductType
from rustic_ai.showcase.vending_bench.supplier_messages import (
    ViewSuppliersRequest,
    build_supplier_view,
)
from rustic_ai.showcase.vending_bench.supplier_registry import (
    SupplierProductInfo,
    SupplierProfile,
    SupplierRegistry,
)


@pytest.mark.parametrize(
    "active_only,product,expected",
    [
        (True, None, ["active-chips", "active-soda"]),
        (False, None, ["active-chips", "inactive-chips", "active-soda"]),
        (True, ProductType.CHIPS, ["active-chips"]),
        (False, ProductType.CHIPS, ["active-chips", "inactive-chips"]),
        (True, ProductType.CANDY, []),
        (False, ProductType.CANDY, []),
    ],
)
def test_supplier_view_preserves_filters_counts_and_correlation(active_only, product, expected):
    registry = SupplierRegistry()
    for name, active, offer in [
        ("active-chips", True, ProductType.CHIPS),
        ("inactive-chips", False, ProductType.CHIPS),
        ("active-soda", True, ProductType.SODA),
    ]:
        registry.add_supplier(
            SupplierProfile(
                supplier_id=name,
                name=name,
                email=name + "@example.test",
                is_active=active,
                products_offered={offer: SupplierProductInfo(base_price=1, current_quoted_price=1.2)},
            )
        )
    before = registry.model_dump()
    request = ViewSuppliersRequest(request_id="view-correlation", active_only=active_only, product_filter=product)
    response = build_supplier_view(registry, request)
    assert response.request_id == request.request_id and response.total_active == 2
    assert [supplier.supplier_id for supplier in response.suppliers] == expected
    assert response.message == f"Found {len(expected)} suppliers matching your criteria"
    assert registry.model_dump() == before


def test_reverse_and_duplicate_research_replies_keep_original_request_identity(database, monkeypatch):
    from copy import deepcopy
    import time
    from uuid import uuid4

    from rustic_ai.core.agents.testutils import ProbeAgent
    from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse
    from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
    from rustic_ai.core.guild.dsl import GuildSpec
    from rustic_ai.showcase.catalog import load_blueprint
    from rustic_ai.showcase.vending_bench.supplier_discovery_agent import (
        SupplierDiscoveryAgent,
    )
    from rustic_ai.showcase.vending_bench.supplier_messages import SupplierSearchRequest

    data = load_blueprint("vending_bench_guild.json")["spec"]
    data["id"] = "sup-" + uuid4().hex
    data["agents"] = [spec for spec in data["agents"] if spec["id"] == "supplier_discovery"]
    builder = GuildBuilder.from_spec(GuildSpec.model_validate(data))
    builder.add_agent_spec(
        AgentBuilder(ProbeAgent)
        .set_id("research_protocol")
        .set_name("Research protocol")
        .set_description("Observe and replay provider replies")
        .listen_to_default_topic(False)
        .add_additional_topic("SUPPLIER_REGISTRY")
        .add_additional_topic("RESEARCH")
        .add_additional_topic("SIMULATION_CONTROL")
        .build_spec()
    )
    guild = builder.bootstrap(database, "supplier-protocol-tests")

    def wait_for(predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if value := predicate():
                return value
            time.sleep(0.01)
        pytest.fail("Supplier protocol event missing")

    try:
        wrapper = wait_for(
            lambda: guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "research_protocol")
        )
        probe = wrapper.agent
        for request_id, product in [("request-a", ProductType.CHIPS), ("request-b", ProductType.SODA)]:
            probe.publish(
                "SUPPLIER_REGISTRY",
                SupplierSearchRequest(request_id=request_id, product_types=[product], max_results=1),
            )
        queries = [message for message in probe.get_messages() if message.format.endswith("SERPQuery")]
        assert len(queries) == 2 and all(
            message.session_state["supplier_search_id"] == message.payload["id"] for message in queries
        )

        owner = guild.execution_engine.agent_tracker.get_agent_wrapper(guild.id, "supplier_discovery").agent
        old_snapshot = deepcopy(owner.get_guild_state())
        acknowledgments = []
        original_ack = SupplierDiscoveryAgent.on_state_updated

        def delay_ack(agent, state, ctx):
            if agent._pending_completions:
                acknowledgments.append((deepcopy(state), ctx))
                agent._guild_state = deepcopy(old_snapshot)
            else:
                original_ack(agent, state, ctx)

        monkeypatch.setattr(SupplierDiscoveryAgent, "on_state_updated", delay_ack)

        def reply(query, content, search_id=None):
            context = dict(query.session_state)
            if search_id is not None:
                context["supplier_search_id"] = search_id
            value = ChatCompletionResponse(
                id=uuid4().hex,
                model="protocol-provider",
                created=1,
                choices=[{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            )
            probe.publish_dict(
                "RESEARCH",
                value.model_dump(),
                format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                session_state=context,
            )

        def responses():
            return [
                message.payload for message in probe.get_messages() if message.format.endswith("SupplierSearchResponse")
            ]

        reply(queries[1], "Garden Wholesale supplies soda; orders@garden.example")
        assert not responses()
        reply(queries[1], "Duplicate Garden Wholesale; orders@garden.example")
        reply(queries[0], "Unknown Wholesale; orders@unknown.example", search_id="unknown-search")
        assert not responses()
        reply(queries[0], "Harbor Wholesale supplies chips; orders@harbor.example")
        assert not responses() and len(owner._pending_completions) == 2
        state, context = acknowledgments[-1]
        owner._guild_state = deepcopy(state)
        original_ack(owner, state, context)
        reply(queries[0], "Duplicate Harbor Wholesale; orders@harbor.example")
        reply(queries[1], "Duplicate Garden Wholesale; orders@garden.example")
        values = responses()
        assert [value["request_id"] for value in values] == ["request-b", "request-a"]
        assert all(
            "soda" in supplier["products_offered"] and "chips" not in supplier["products_offered"]
            for supplier in values[0]["suppliers_found"]
        )
        assert all(
            "chips" in supplier["products_offered"] and "soda" not in supplier["products_offered"]
            for supplier in values[1]["suppliers_found"]
        )
        assert "Garden Wholesale" in str(values[0]) and "Harbor Wholesale" in str(values[1])
        assert not owner.pending_searches and not owner._pending_completions
        assert not owner.get_guild_state().get("pending_supplier_searches")
    finally:
        guild.shutdown()
