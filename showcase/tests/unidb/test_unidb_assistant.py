"""Tests for UniDB Assistant guild JSONata transforms."""

import json
from pathlib import Path

from jsonata import Jsonata
import pytest


class TestUniDBAssistantTransforms:
    """Test the JSONata transforms used in the UniDB Assistant guild."""

    @pytest.fixture
    def guild_spec(self):
        """Load the UniDB Assistant guild spec."""
        json_path = Path(__file__).parent.parent.parent / "apps" / "unidb_assistant.json"
        with open(json_path) as f:
            return json.load(f)

    @pytest.fixture
    def routes(self, guild_spec):
        """Extract routes from the guild spec."""
        return guild_spec["spec"]["routes"]["steps"]

    def get_route_by_message_format(self, routes, message_format):
        """Find a route by its message format."""
        for route in routes:
            if route.get("message_format") == message_format:
                return route
        return None

    def get_routes_by_message_format(self, routes, message_format):
        """Find all routes by message format."""
        return [r for r in routes if r.get("message_format") == message_format]

    def test_guild_spec_loads(self, guild_spec):
        """Test that the guild spec loads correctly."""
        assert guild_spec["name"] == "UniDB Assistant"
        assert guild_spec["spec"]["name"] == "UniDB Assistant Guild"
        assert len(guild_spec["spec"]["agents"]) == 2

    def test_agents_configured_correctly(self, guild_spec):
        """Test that agents are configured with correct properties."""
        agents = guild_spec["spec"]["agents"]

        # Query Processor agent
        query_processor = next(a for a in agents if a["name"] == "Query Processor")
        assert query_processor["class_name"] == "rustic_ai.llm_agent.llm_agent.LLMAgent"
        assert "query_processor" in query_processor["additional_topics"]
        assert query_processor["properties"]["send_response"] is True

        # Check tools are configured - should have 15 tools
        wrappers = query_processor["properties"]["llm_request_wrappers"]
        assert len(wrappers) == 1
        tools = wrappers[0]["toolset"]["tools"]
        assert len(tools) == 15

        tool_names = [t["name"] for t in tools]
        # Schema operations
        assert "create_label" in tool_names
        assert "create_edge_type" in tool_names
        assert "add_property" in tool_names
        assert "create_scalar_index" in tool_names
        assert "create_vector_index" in tool_names
        # Schema introspection
        assert "list_labels" in tool_names
        assert "list_edge_types" in tool_names
        assert "get_label_info" in tool_names
        assert "get_schema" in tool_names
        # Data operations
        assert "query_database" in tool_names
        assert "execute_command" in tool_names
        assert "flush_database" in tool_names
        # Vector search
        assert "vector_search" in tool_names
        # Bulk operations
        assert "insert_vertices" in tool_names
        assert "insert_edges" in tool_names

        # UniDB Agent
        unidb_agent = next(a for a in agents if a["name"] == "UniDB Agent")
        assert unidb_agent["class_name"] == "rustic_ai.unidb.agent.UniDBAgent"
        assert "unidb" in unidb_agent["additional_topics"]

    def test_all_tool_routes_configured(self, routes):
        """Test that all tool call routes from Query Processor to UniDB are configured."""
        tool_formats = [
            # Schema operations
            "rustic_ai.unidb.models.CreateLabelRequest",
            "rustic_ai.unidb.models.CreateEdgeTypeRequest",
            "rustic_ai.unidb.models.AddPropertyRequest",
            "rustic_ai.unidb.models.CreateScalarIndexRequest",
            "rustic_ai.unidb.models.CreateVectorIndexRequest",
            # Schema introspection
            "rustic_ai.unidb.models.ListLabelsRequest",
            "rustic_ai.unidb.models.ListEdgeTypesRequest",
            "rustic_ai.unidb.models.GetLabelInfoRequest",
            "rustic_ai.unidb.models.GetSchemaRequest",
            # Data operations
            "rustic_ai.unidb.models.QueryRequest",
            "rustic_ai.unidb.models.ExecuteRequest",
            "rustic_ai.unidb.models.FlushRequest",
            # Vector search
            "rustic_ai.unidb.models.VectorSearchRequest",
            # Bulk operations
            "rustic_ai.unidb.models.InsertVerticesRequest",
            "rustic_ai.unidb.models.InsertEdgesRequest",
        ]

        for format_name in tool_formats:
            route = self.get_route_by_message_format(routes, format_name)
            assert route is not None, f"Route for {format_name} not found"
            assert route["destination"]["topics"] == "unidb", f"Route for {format_name} should go to 'unidb' topic"
            assert (
                route["agent"]["name"] == "Query Processor"
            ), f"Route for {format_name} should come from Query Processor"

    def test_all_response_routes_configured(self, routes):
        """Test that all response routes from UniDB go back to Query Processor (closed loop)."""
        response_formats = [
            # Schema operations
            "rustic_ai.unidb.models.CreateLabelResponse",
            "rustic_ai.unidb.models.CreateEdgeTypeResponse",
            "rustic_ai.unidb.models.AddPropertyResponse",
            "rustic_ai.unidb.models.CreateScalarIndexResponse",
            "rustic_ai.unidb.models.CreateVectorIndexResponse",
            # Schema introspection
            "rustic_ai.unidb.models.ListLabelsResponse",
            "rustic_ai.unidb.models.ListEdgeTypesResponse",
            "rustic_ai.unidb.models.GetLabelInfoResponse",
            "rustic_ai.unidb.models.GetSchemaResponse",
            # Data operations
            "rustic_ai.unidb.models.QueryResponse",
            "rustic_ai.unidb.models.ExecuteResponse",
            "rustic_ai.unidb.models.FlushResponse",
            # Vector search
            "rustic_ai.unidb.models.VectorSearchResponse",
            # Bulk operations
            "rustic_ai.unidb.models.InsertVerticesResponse",
            "rustic_ai.unidb.models.InsertEdgesResponse",
        ]

        for format_name in response_formats:
            route = self.get_route_by_message_format(routes, format_name)
            assert route is not None, f"Route for {format_name} not found"
            assert (
                route["destination"]["topics"] == "query_processor"
            ), f"Route for {format_name} should go to 'query_processor' topic (closed loop)"
            assert route["agent"]["name"] == "UniDB Agent", f"Route for {format_name} should come from UniDB Agent"
            assert route["transformer"] is not None, f"Route for {format_name} should have a transformer"

    # ==================== User Input Route Test ====================

    def test_user_input_route_stores_context(self, routes):
        """Test that the user input route stores user_query in context."""
        route = self.get_route_by_message_format(
            routes, "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
        )
        assert route is not None
        assert route["transformer"]["style"] == "content_based_router"

        handler = route["transformer"]["handler"]
        expr = Jsonata(handler)

        # Test with string content
        sample_data = {"messages": [{"role": "user", "content": "Show me all persons in the database"}]}
        result = expr.evaluate(sample_data)
        assert result["topics"] == "query_processor"
        assert result["context"]["user_query"] == "Show me all persons in the database"
        assert result["payload"] == sample_data

        # Test with array content (content parts format)
        sample_data_array = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": "List all labels"}]}]
        }
        result = expr.evaluate(sample_data_array)
        assert result["context"]["user_query"] == "List all labels"

    # ==================== Schema Operation Transform Tests ====================

    def test_create_label_response_transform(self, routes):
        """Test the CreateLabelResponse transform includes user query."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.CreateLabelResponse")
        expr = Jsonata(route["transformer"]["handler"])

        # Success case with context
        result = expr.evaluate(
            {"payload": {"label": "Person", "success": True}, "context": {"user_query": "Create a Person label"}}
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "[TOOL RESULT]" in text
        assert "Original user request: Create a Person label" in text
        assert "Successfully created label: Person" in text

        # Failure case
        result = expr.evaluate(
            {"payload": {"label": "Person", "success": False}, "context": {"user_query": "Create a Person label"}}
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Failed to create label: Person" in text

    def test_create_edge_type_response_transform(self, routes):
        """Test the CreateEdgeTypeResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.CreateEdgeTypeResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"edge_type": "WORKS_AT", "success": True},
                "context": {"user_query": "Create WORKS_AT relationship"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully created edge type: WORKS_AT" in text

    def test_add_property_response_transform(self, routes):
        """Test the AddPropertyResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.AddPropertyResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"label": "Person", "property_name": "name", "success": True},
                "context": {"user_query": "Add name property to Person"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully added property" in text
        assert "name" in text
        assert "Person" in text

    def test_create_scalar_index_response_transform(self, routes):
        """Test the CreateScalarIndexResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.CreateScalarIndexResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"label": "Person", "property_name": "name", "success": True},
                "context": {"user_query": "Create index on Person.name"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully created scalar index" in text

    def test_create_vector_index_response_transform(self, routes):
        """Test the CreateVectorIndexResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.CreateVectorIndexResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"label": "Document", "property_name": "embedding", "metric": "cosine", "success": True},
                "context": {"user_query": "Create vector index for embeddings"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully created vector index" in text
        assert "cosine" in text

    # ==================== Schema Introspection Transform Tests ====================

    def test_list_labels_response_transform(self, routes):
        """Test the ListLabelsResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.ListLabelsResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"labels": ["Person", "Company", "Product"]},
                "context": {"user_query": "What labels exist?"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request: What labels exist?" in text
        assert "Person" in text
        assert "Company" in text

    def test_list_edge_types_response_transform(self, routes):
        """Test the ListEdgeTypesResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.ListEdgeTypesResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"edge_types": ["WORKS_AT", "KNOWS", "BOUGHT"]},
                "context": {"user_query": "Show me all relationships"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "WORKS_AT" in text

    def test_get_label_info_response_transform(self, routes):
        """Test the GetLabelInfoResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.GetLabelInfoResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"label": "Person", "properties": {"name": "string", "age": "int64"}},
                "context": {"user_query": "What properties does Person have?"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Person" in text

    def test_get_schema_response_transform(self, routes):
        """Test the GetSchemaResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.GetSchemaResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"db_schema": {"labels": ["Person"], "edge_types": ["KNOWS"]}},
                "context": {"user_query": "Show me the database schema"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "schema" in text.lower()

    # ==================== Data Operation Transform Tests ====================

    def test_query_response_transform(self, routes):
        """Test the QueryResponse transform includes user query."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.QueryResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"results": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}], "count": 2},
                "context": {"user_query": "Find all people named Alice or Bob"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request: Find all people named Alice or Bob" in text
        assert "2 results" in text
        assert "Alice" in text

    def test_execute_response_transform_success(self, routes):
        """Test the ExecuteResponse transform for success case."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.ExecuteResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {"success": True, "rows_affected": 5},
                "context": {"user_query": "Delete all inactive users"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "successfully" in text
        assert "5" in text

    def test_execute_response_transform_failure(self, routes):
        """Test the ExecuteResponse transform for failure case."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.ExecuteResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {"payload": {"success": False, "rows_affected": None}, "context": {"user_query": "Update something"}}
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "failed" in text

    def test_flush_response_transform(self, routes):
        """Test the FlushResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.FlushResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate({"payload": {"success": True}, "context": {"user_query": "Save all changes"}})
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "flushed successfully" in text

    # ==================== Vector Search Transform Tests ====================

    def test_vector_search_response_transform(self, routes):
        """Test the VectorSearchResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.VectorSearchResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {
                "payload": {
                    "results": [{"vertex_id": 1, "distance": 0.1}, {"vertex_id": 2, "distance": 0.2}],
                    "count": 2,
                },
                "context": {"user_query": "Find similar documents"},
            }
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Vector search" in text
        assert "2 results" in text

    # ==================== Bulk Operation Transform Tests ====================

    def test_insert_vertices_response_transform(self, routes):
        """Test the InsertVerticesResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.InsertVerticesResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {"payload": {"count": 100, "success": True}, "context": {"user_query": "Import all users"}}
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully inserted" in text
        assert "100" in text
        assert "vertices" in text

    def test_insert_edges_response_transform(self, routes):
        """Test the InsertEdgesResponse transform."""
        route = self.get_route_by_message_format(routes, "rustic_ai.unidb.models.InsertEdgesResponse")
        expr = Jsonata(route["transformer"]["handler"])

        result = expr.evaluate(
            {"payload": {"count": 50, "success": True}, "context": {"user_query": "Connect all users to companies"}}
        )
        text = result["payload"]["messages"][0]["content"][0]["text"]
        assert "Original user request:" in text
        assert "Successfully inserted" in text
        assert "50" in text
        assert "edges" in text

    # ==================== Final Response Route Test ====================

    def test_final_response_route(self, routes):
        """Test that the final response route to user is configured."""
        response_routes = [
            r
            for r in routes
            if r.get("message_format") == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"
        ]
        assert len(response_routes) == 1
        assert response_routes[0]["destination"]["topics"] == "user_message_broadcast"
        assert response_routes[0]["process_status"] == "completed"
        assert response_routes[0]["agent"]["name"] == "Query Processor"

    def test_final_response_transformer_converts_to_textformat(self, routes):
        """Test that the final response transformer converts ChatCompletionResponse to TextFormat."""
        route = self.get_route_by_message_format(
            routes, "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"
        )
        assert route["transformer"] is not None
        assert route["transformer"]["style"] == "content_based_router"

        expr = Jsonata(route["transformer"]["handler"])

        # Test with content - should produce TextFormat
        result = expr.evaluate({"payload": {"choices": [{"message": {"content": "Here is the answer."}}]}})
        assert result["format"] == "rustic_ai.core.ui_protocol.types.TextFormat"
        assert result["payload"]["text"] == "Here is the answer."

        # Test with null content (tool call) - should return null (filtered out)
        result = expr.evaluate({"payload": {"choices": [{"message": {"content": None}}]}})
        assert result is None
