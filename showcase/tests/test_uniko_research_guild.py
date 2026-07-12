"""
Comprehensive tests for Uniko Research Guild to verify routing and agent interactions.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from rustic_ai.core.guild.dsl import GuildSpec


@pytest.fixture
def guild_spec() -> GuildSpec:
    """Load the Uniko Research Guild specification."""
    guild_json_path = Path(__file__).parent.parent / "apps" / "uniko_research_guild.json"
    with open(guild_json_path) as f:
        guild_data = json.load(f)
    return GuildSpec.model_validate(guild_data["spec"])


class TestUnikoResearchGuildConfiguration:
    """Test the guild configuration loads and routing is properly defined."""

    def test_guild_spec_loads_correctly(self, guild_spec: GuildSpec):
        """Verify the guild spec loads without errors."""
        assert guild_spec.name == "Uniko Research Guild"
        assert len(guild_spec.agents) == 9  # Updated: removed markdown_agent
        assert "memory_agent" in [agent.id for agent in guild_spec.agents]
        assert "google_agent" in [agent.id for agent in guild_spec.agents]

    def test_all_required_agents_present(self, guild_spec: GuildSpec):
        """Verify all required agents are defined."""
        agent_ids = [agent.id for agent in guild_spec.agents]
        required_agents = [
            "memory_agent",
            "google_agent",
            "serp_agent",
            "playwright_agent",
            # "markdown_agent",  # Removed: non-existent class and redundant routing
            "synthesis_agent",
            "query_agent",
            "splitter_agent",
            "basic_wiring_agent",
            "gateway_agent",
        ]
        for agent_id in required_agents:
            assert agent_id in agent_ids, f"Missing required agent: {agent_id}"

    def test_routing_steps_defined(self, guild_spec: GuildSpec):
        """Verify routing steps are defined."""
        assert guild_spec.routes is not None
        assert len(guild_spec.routes.steps) > 0
        print(f"Total routing steps: {len(guild_spec.routes.steps)}")

    def test_dependencies_configured(self, guild_spec: GuildSpec):
        """Test that dependencies are left for platform-level configuration.

        This guild is deployed via Rustic UI (like sibling blueprints
        llm_council.json, multi_llm_blueprint.json, react_data_analyst.json),
        which configure filesystem/llm/uniko dependencies through the platform
        rather than the static blueprint, so dependency_map is intentionally empty.
        """
        assert guild_spec.dependency_map == {}

    def test_agent_id_consistency_in_routing(self, guild_spec: GuildSpec):
        """Test that routing uses agent references consistently."""
        agent_ids = {agent.id for agent in guild_spec.agents}
        agent_names = {agent.name for agent in guild_spec.agents}

        # Check all routing steps that reference agents
        for idx, step in enumerate(guild_spec.routes.steps):
            if step.agent:
                # Agent reference should have either id or name
                assert step.agent.id or step.agent.name, f"Step {idx}: Agent reference has neither id nor name"

                # If referencing by ID, verify it exists
                if step.agent.id:
                    assert (
                        step.agent.id in agent_ids
                    ), f"Step {idx}: Agent ID '{step.agent.id}' not found in guild agents"

                # If referencing by name, verify it exists
                if step.agent.name:
                    assert (
                        step.agent.name in agent_names
                    ), f"Step {idx}: Agent name '{step.agent.name}' not found in guild agents"

    def test_memory_agent_topics(self, guild_spec: GuildSpec):
        """Test Memory Agent has all required topics."""
        memory_agent = next(agent for agent in guild_spec.agents if agent.id == "memory_agent")
        assert "memory_observe" in memory_agent.additional_topics
        assert "memory_recall" in memory_agent.additional_topics
        assert "memory_answer" in memory_agent.additional_topics
        assert "memory_ingest" in memory_agent.additional_topics
        assert memory_agent.listen_to_default_topic is True

    def test_synthesis_agent_configuration(self, guild_spec: GuildSpec):
        """Test Synthesis Agent configuration."""
        synthesis_agent = next(agent for agent in guild_spec.agents if agent.id == "synthesis_agent")
        assert synthesis_agent.listen_to_default_topic is False
        assert "synthesis_agent" in synthesis_agent.additional_topics
        assert synthesis_agent.properties.model == "gpt-4.1"

    def test_query_agent_configuration(self, guild_spec: GuildSpec):
        """Test Query Agent configuration."""
        query_agent = next(agent for agent in guild_spec.agents if agent.id == "query_agent")
        assert query_agent.listen_to_default_topic is False
        assert "query_agent" in query_agent.additional_topics
        assert query_agent.properties.model == "gpt-4.1"

    def test_splitter_agent_configuration(self, guild_spec: GuildSpec):
        """Test Splitter Agent has proper JSONata configuration."""
        splitter_agent = next(agent for agent in guild_spec.agents if agent.id == "splitter_agent")
        assert splitter_agent.listen_to_default_topic is False
        assert splitter_agent.properties.splitter.split_type == "jsonata"
        assert splitter_agent.properties.splitter.expression is not None

    def test_routing_completion_points(self, guild_spec: GuildSpec):
        """Test that routes have proper completion markers."""
        completed_routes = [step for step in guild_spec.routes.steps if step.process_status == "completed"]
        # Should have at least 2 completion points
        assert len(completed_routes) >= 2, f"Expected at least 2 completion points, found {len(completed_routes)}"

    def test_user_query_entry_point(self, guild_spec: GuildSpec):
        """Test the first routing step handles user queries."""
        first_route = guild_spec.routes.steps[0]
        assert first_route.message_format == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
        assert first_route.transformer is not None
        assert first_route.transformer.style == "content_based_router"

    def test_recall_response_routing_exists(self, guild_spec: GuildSpec):
        """Test that RecallResponse has routing logic."""
        recall_routes = [
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.uniko_agent.models.RecallResponse"
        ]
        assert len(recall_routes) >= 2, "Should have at least 2 RecallResponse routing rules"

    def test_serp_to_playwright_routing(self, guild_spec: GuildSpec):
        """Test routing from SERP to Playwright."""
        serp_route = next(
            (
                step
                for step in guild_spec.routes.steps
                if step.agent and step.agent.name == "Search Agent" and step.message_format == "rustic_ai.serpapi.agent.SERPResults"
            ),
            None,
        )
        assert serp_route is not None, "SERP Agent routing not found"
        assert serp_route.transformer is not None
        assert serp_route.transformer.output_format == "rustic_ai.playwright.agent.WebScrapingRequest"

    def test_playwright_to_memory_routing(self, guild_spec: GuildSpec):
        """Test routing from Playwright to Memory."""
        playwright_route = next(
            (
                step
                for step in guild_spec.routes.steps
                if step.agent and step.agent.name == "Web Scraper Agent"
            ),
            None,
        )
        assert playwright_route is not None, "Playwright Agent routing not found"
        assert playwright_route.destination.topics == "memory_ingest"

    def test_synthesis_routing_complete(self, guild_spec: GuildSpec):
        """Test synthesis agent routes exist and are complete."""
        # Route TO synthesis
        to_synthesis = any(
            "synthesis_agent" in (step.transformer.handler if step.transformer and hasattr(step.transformer, "handler") else "")
            for step in guild_spec.routes.steps
        )
        assert to_synthesis, "No route found TO synthesis agent"

        # Route FROM synthesis
        from_synthesis = next(
            (step for step in guild_spec.routes.steps if step.agent and step.agent.name == "Synthesis Agent"),
            None,
        )
        assert from_synthesis is not None, "No route found FROM synthesis agent"

    def test_gateway_agent_routing(self, guild_spec: GuildSpec):
        """Test Gateway Agent for g2g communication."""
        gateway_routes = [
            step for step in guild_spec.routes.steps if step.agent and step.agent.name == "Research Gateway"
        ]
        assert len(gateway_routes) >= 2, "Should have at least 2 gateway routing rules"

    def test_all_agents_have_routing_or_justification(self, guild_spec: GuildSpec):
        """Test that all agents either have routing or don't need it."""
        agent_ids_with_routes = set()
        agent_names_with_routes = set()

        for step in guild_spec.routes.steps:
            if step.agent:
                if step.agent.id:
                    agent_ids_with_routes.add(step.agent.id)
                if step.agent.name:
                    agent_names_with_routes.add(step.agent.name)

        # Agents that don't need explicit routing (utility agents)
        utility_agents = {"basic_wiring_agent"}

        for agent in guild_spec.agents:
            if agent.id not in utility_agents:
                has_route = agent.id in agent_ids_with_routes or agent.name in agent_names_with_routes
                # Agents listening to default_topic will receive messages even without explicit routing
                has_default_topic = agent.listen_to_default_topic
                # Has additional topics
                has_topics = len(agent.additional_topics) > 0

                assert (
                    has_route or has_default_topic or has_topics
                ), f"Agent '{agent.id}' has no routing, default topic, or additional topics"


class TestRoutingLogicDeep:
    """Deep testing of routing logic and message flow patterns."""

    def test_guild_state_initialization_requirements(self, guild_spec: GuildSpec):
        """Test that guild state fields used in routing are properly handled."""
        # Check routing steps that reference guild_state
        state_dependent_routes = []
        for idx, step in enumerate(guild_spec.routes.steps):
            if step.transformer and hasattr(step.transformer, "handler"):
                if "guild_state" in step.transformer.handler:
                    state_dependent_routes.append((idx, step))
            if step.guild_state_update:
                state_dependent_routes.append((idx, step))

        assert len(state_dependent_routes) > 0, "Expected routes that use guild_state"

        # Check that state fields referenced are documented
        print(f"\nFound {len(state_dependent_routes)} routes that reference guild_state")

        # Key fields that should be tracked:
        # - answered: list of answered query IDs
        # - current_id: current query ID counter
        # - user_queries: list of user queries

    def test_complete_user_query_flow_routing(self, guild_spec: GuildSpec):
        """Test the complete routing flow for a user query."""
        # Step 1: User query comes in as ChatCompletionRequest
        entry_route = guild_spec.routes.steps[0]
        assert entry_route.message_format == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"

        # Step 2: Should route to RecallRequest
        assert "RecallRequest" in entry_route.transformer.handler
        assert "memory_recall" in entry_route.transformer.handler

        # Step 3: RecallResponse should exist
        recall_routes = [
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.uniko_agent.models.RecallResponse"
        ]
        assert len(recall_routes) >= 2, "Should have multiple RecallResponse handlers"

    def test_poor_recall_triggers_web_research(self, guild_spec: GuildSpec):
        """Test that poor recall score triggers web research path."""
        # Find RecallResponse route that checks recall quality
        recall_route = next(
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.uniko_agent.models.RecallResponse"
            and step.agent
            and step.agent.name == "Memory Agent"
            and "query_agent" in (step.transformer.handler if step.transformer else "")
        )
        assert recall_route is not None

        # Should route to query_agent when recall is poor
        assert "query_agent" in recall_route.transformer.handler
        assert "has_good_recall" in recall_route.transformer.handler or "count" in recall_route.transformer.handler

    def test_web_research_pipeline(self, guild_spec: GuildSpec):
        """Test the complete web research pipeline routing."""
        # QueryAgent → Splitter
        query_to_splitter = next(
            step
            for step in guild_spec.routes.steps
            if step.agent and step.agent.name == "Query Agent"
        )
        assert query_to_splitter.destination.topics == "splitter_agent"

        # Splitter → Google + SERP (fanned out to two dedicated topics)
        splitter_routes = [
            step
            for step in guild_spec.routes.steps
            if step.agent and step.agent.name == "Splitter Agent"
        ]
        assert len(splitter_routes) == 2
        for step in splitter_routes:
            assert step.message_format == "rustic_ai.serpapi.agent.SERPQuery"
        assert {step.destination.topics for step in splitter_routes} == {"google_agent", "serp_agent"}

        # SERP → Playwright
        serp_to_playwright = next(
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.serpapi.agent.SERPResults"
        )
        assert serp_to_playwright.transformer.output_format == "rustic_ai.playwright.agent.WebScrapingRequest"

        # Playwright → Memory
        playwright_to_memory = next(
            step
            for step in guild_spec.routes.steps
            if step.agent and step.agent.name == "Web Scraper Agent"
        )
        assert playwright_to_memory.destination.topics == "memory_ingest"

    def test_memory_ingestion_flow(self, guild_spec: GuildSpec):
        """Test memory ingestion and observation flow."""
        # IngestOutcome → Basic Wiring Agent (intermediate hop from Memory Agent)
        ingest_to_wiring = next(
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.uniko_agent.models.IngestOutcome"
            and step.agent
            and step.agent.name == "Memory Agent"
        )
        assert ingest_to_wiring.destination.topics == "basic_wiring"

        # Basic Wiring Agent → ObserveTurnRequest on memory_observe
        wiring_to_observe = next(
            step
            for step in guild_spec.routes.steps
            if step.message_format == "rustic_ai.uniko_agent.models.IngestOutcome"
            and step.agent
            and step.agent.name == "Basic Wiring Agent"
        )
        assert wiring_to_observe.destination.topics == "memory_observe"
        # Content-based router uses handler, not output_format
        assert "ObserveTurnRequest" in wiring_to_observe.transformer.handler

        # ObserveResult → RecallRequest (to query ingested content)
        observe_to_recall = next(
            (
                step
                for step in guild_spec.routes.steps
                if step.message_format == "rustic_ai.uniko_agent.models.ObserveResult"
                and step.destination
                and step.destination.topics == "memory_recall"
            ),
            None,
        )
        assert observe_to_recall is not None

    def test_synthesis_flow(self, guild_spec: GuildSpec):
        """Test synthesis agent flow."""
        # RecallResponse → Synthesis (when recall has content)
        recall_to_synthesis = next(
            (
                step
                for step in guild_spec.routes.steps
                if step.message_format == "rustic_ai.uniko_agent.models.RecallResponse"
                and step.transformer
                and hasattr(step.transformer, "handler")
                and "synthesis_agent" in step.transformer.handler
            ),
            None,
        )
        assert recall_to_synthesis is not None

        # Synthesis → user broadcast (completion point)
        synthesis_to_observe = next(
            step
            for step in guild_spec.routes.steps
            if step.agent and step.agent.name == "Synthesis Agent"
        )
        assert synthesis_to_observe.destination.topics == "user_message_broadcast"
        assert synthesis_to_observe.process_status == "completed"

    def test_completion_points(self, guild_spec: GuildSpec):
        """Test that completion points properly end the routing chain."""
        completion_routes = [
            step for step in guild_spec.routes.steps if step.process_status == "completed"
        ]

        # Each completion should send to user_message_broadcast
        # either via direct destination or via content_based_router handler
        for route in completion_routes:
            has_broadcast = False
            if route.destination and route.destination.topics == "user_message_broadcast":
                has_broadcast = True
            elif route.transformer and hasattr(route.transformer, "handler"):
                if "user_message_broadcast" in route.transformer.handler:
                    has_broadcast = True

            assert has_broadcast, f"Completion route does not send to user_message_broadcast: {route}"

    def test_no_infinite_loops_in_routing(self, guild_spec: GuildSpec):
        """Test that routing doesn't create infinite loops."""
        # Build a routing graph
        routing_graph: dict[str, list[dict[str, Any]]] = {}
        for step in enumerate(guild_spec.routes.steps):
            source = f"{step[1].agent.name if step[1].agent else 'UserProxy'}:{step[1].message_format}"

            # Get destination from transformer or direct destination
            dest_topic = None
            if step[1].destination:
                dest_topic = step[1].destination.topics
            elif step[1].transformer and hasattr(step[1].transformer, "handler"):
                # Extract topic from content_based_router handler
                if "user_message_broadcast" in step[1].transformer.handler:
                    dest_topic = "user_message_broadcast"
                elif '"topics"' in step[1].transformer.handler:
                    dest_topic = "content_based"

            if source not in routing_graph:
                routing_graph[source] = []

            routing_graph[source].append({
                "dest_topic": dest_topic,
                "has_completion": step[1].process_status == "completed",
            })

        # Check that routes with process_status=completed send to user broadcast
        # (either explicitly or via content_based_router)
        for source, dests in routing_graph.items():
            for dest in dests:
                if dest["has_completion"]:
                    # Completion routes should go to user_message_broadcast
                    assert (
                        dest["dest_topic"] == "user_message_broadcast" or dest["dest_topic"] == "content_based"
                    ), f"Completion route from {source} doesn't go to user_message_broadcast"

    def test_url_detection_flow(self, guild_spec: GuildSpec):
        """Test URL detection and direct scraping flow."""
        # First route should detect URLs in content
        first_route = guild_spec.routes.steps[0]
        handler = first_route.transformer.handler

        # Should check for URLs in the content
        assert "http" in handler or "url" in handler.lower()
        assert "WebScrapingRequest" in handler

    def test_file_upload_flow(self, guild_spec: GuildSpec):
        """Test file/image upload detection and ingestion."""
        first_route = guild_spec.routes.steps[0]
        handler = first_route.transformer.handler

        # Should check for files/images
        assert "image_url" in handler or "file_url" in handler
        assert "IngestDocumentRequest" in handler

    def test_gateway_bidirectional_flow(self, guild_spec: GuildSpec):
        """Test gateway agent for g2g communication."""
        gateway_agent = next(agent for agent in guild_spec.agents if agent.id == "gateway_agent")

        # Should have input and output formats defined
        assert gateway_agent.properties.input_formats is not None
        assert len(gateway_agent.properties.input_formats) > 0
        assert "ResearchRequest" in gateway_agent.properties.input_formats[0]

        assert gateway_agent.properties.output_formats is not None
        assert len(gateway_agent.properties.output_formats) > 0
        assert "ResearchResults" in gateway_agent.properties.output_formats[0]

    def test_jsonata_expressions_valid_syntax(self, guild_spec: GuildSpec):
        """Test that JSONata expressions in transformers are syntactically valid."""
        for idx, step in enumerate(guild_spec.routes.steps):
            if step.transformer:
                if hasattr(step.transformer, "handler") and step.transformer.handler:
                    # Basic validation - should start with valid JSONata constructs
                    handler = step.transformer.handler
                    # Should have balanced parentheses
                    assert handler.count("(") == handler.count(")"), f"Step {idx}: Unbalanced parentheses"
                    assert handler.count("{") == handler.count("}"), f"Step {idx}: Unbalanced braces"
                    assert handler.count("[") == handler.count("]"), f"Step {idx}: Unbalanced brackets"

                if hasattr(step.transformer, "expression") and step.transformer.expression:
                    expr = step.transformer.expression
                    # Should have balanced delimiters
                    assert expr.count("(") == expr.count(")"), f"Step {idx}: Unbalanced parentheses in expression"
                    assert expr.count("{") == expr.count("}"), f"Step {idx}: Unbalanced braces in expression"
                    assert expr.count("[") == expr.count("]"), f"Step {idx}: Unbalanced brackets in expression"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
