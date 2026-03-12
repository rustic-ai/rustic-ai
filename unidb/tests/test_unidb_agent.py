"""Tests for UniDBAgent."""

from unittest.mock import MagicMock, patch

import pytest

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.unidb.agent import UniDBAgent
from rustic_ai.unidb.models import (
    AddPropertyRequest,
    AddPropertyResponse,
    CreateEdgeTypeRequest,
    CreateEdgeTypeResponse,
    CreateLabelRequest,
    CreateLabelResponse,
    CreateScalarIndexRequest,
    CreateScalarIndexResponse,
    CreateVectorIndexRequest,
    CreateVectorIndexResponse,
    EdgeData,
    ExecuteRequest,
    ExecuteResponse,
    FlushRequest,
    FlushResponse,
    GetLabelInfoRequest,
    GetLabelInfoResponse,
    GetSchemaRequest,
    GetSchemaResponse,
    IndexType,
    InsertEdgesRequest,
    InsertEdgesResponse,
    InsertVerticesRequest,
    InsertVerticesResponse,
    ListEdgeTypesRequest,
    ListEdgeTypesResponse,
    ListLabelsRequest,
    ListLabelsResponse,
    PropertyType,
    QueryRequest,
    QueryResponse,
    UniDBAgentConfig,
    VectorMetric,
    VectorSearchRequest,
    VectorSearchResponse,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def mock_database():
    """Create a mock Database instance."""
    mock_db = MagicMock()
    mock_db.create_label = MagicMock()
    mock_db.create_edge_type = MagicMock()
    mock_db.add_property = MagicMock()
    mock_db.create_scalar_index = MagicMock()
    mock_db.create_vector_index = MagicMock()
    mock_db.list_labels = MagicMock(return_value=["Label1", "Label2"])
    mock_db.list_edge_types = MagicMock(return_value=["KNOWS", "LIKES"])
    mock_db.get_label_info = MagicMock(return_value={"name": "string", "age": "int64"})
    mock_db.get_schema = MagicMock(return_value={"labels": ["Label1"], "edges": ["KNOWS"]})
    mock_db.execute = MagicMock(return_value=5)
    mock_db.query = MagicMock(return_value=[{"name": "Alice", "age": 30}])
    mock_db.flush = MagicMock()
    mock_db.bulk_insert_vertices = MagicMock()
    mock_db.bulk_insert_edges = MagicMock()
    return mock_db


@pytest.fixture
def agent_spec(tmp_path):
    """Create an agent spec for UniDBAgent."""
    return (
        AgentBuilder(UniDBAgent)
        .set_id("unidb_agent")
        .set_name("UniDB Agent")
        .set_description("Test UniDB Agent")
        .set_properties(UniDBAgentConfig(db_path=str(tmp_path / "test.db")))
        .build_spec()
    )


def _build_message(generator, payload, fmt):
    """Helper to build a test message."""
    return Message(
        id_obj=generator.get_id(Priority.NORMAL),
        topics="default_topic",
        sender=AgentTag(id="tester", name="tester"),
        payload=payload,
        format=fmt,
    )


class TestUniDBAgent:
    """Tests for UniDBAgent."""

    def test_create_label_success(self, agent_spec, generator, mock_database):
        """Test successful label creation."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                CreateLabelRequest(label="Person").model_dump(),
                get_qualified_class_name(CreateLabelRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = CreateLabelResponse.model_validate(results[0].payload)
            assert response.label == "Person"
            assert response.success is True
            mock_database.create_label.assert_called_once_with("Person")

    def test_create_label_error(self, agent_spec, generator, mock_database):
        """Test label creation with error."""
        mock_database.create_label.side_effect = Exception("Label already exists")

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                CreateLabelRequest(label="Person").model_dump(),
                get_qualified_class_name(CreateLabelRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            assert results[0].format == get_qualified_class_name(ErrorMessage)
            error = ErrorMessage.model_validate(results[0].payload)
            assert error.error_type == "CreateLabelError"
            assert "Label already exists" in error.error_message

    def test_create_edge_type_success(self, agent_spec, generator, mock_database):
        """Test successful edge type creation."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                CreateEdgeTypeRequest(
                    edge_type="KNOWS",
                    source_labels=["Person"],
                    target_labels=["Person"],
                ).model_dump(),
                get_qualified_class_name(CreateEdgeTypeRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = CreateEdgeTypeResponse.model_validate(results[0].payload)
            assert response.edge_type == "KNOWS"
            assert response.success is True
            mock_database.create_edge_type.assert_called_once_with("KNOWS", ["Person"], ["Person"])

    def test_add_property_success(self, agent_spec, generator, mock_database):
        """Test successful property addition."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                AddPropertyRequest(
                    label="Person",
                    property_name="name",
                    property_type=PropertyType.STRING,
                    nullable=False,
                ).model_dump(),
                get_qualified_class_name(AddPropertyRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = AddPropertyResponse.model_validate(results[0].payload)
            assert response.label == "Person"
            assert response.property_name == "name"
            assert response.success is True
            mock_database.add_property.assert_called_once_with("Person", "name", "string", False)

    def test_add_vector_property_success(self, agent_spec, generator, mock_database):
        """Test successful vector property addition."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                AddPropertyRequest(
                    label="Document",
                    property_name="embedding",
                    property_type=PropertyType.FLOAT64,
                    vector_dimension=384,
                ).model_dump(),
                get_qualified_class_name(AddPropertyRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = AddPropertyResponse.model_validate(results[0].payload)
            assert response.label == "Document"
            assert response.property_name == "embedding"
            mock_database.add_property.assert_called_once_with("Document", "embedding", "vector[384]", True)

    def test_create_scalar_index_success(self, agent_spec, generator, mock_database):
        """Test successful scalar index creation."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                CreateScalarIndexRequest(
                    label="Person",
                    property_name="name",
                    index_type=IndexType.BTREE,
                ).model_dump(),
                get_qualified_class_name(CreateScalarIndexRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = CreateScalarIndexResponse.model_validate(results[0].payload)
            assert response.label == "Person"
            assert response.property_name == "name"
            mock_database.create_scalar_index.assert_called_once_with("Person", "name", "btree")

    def test_create_vector_index_success(self, agent_spec, generator, mock_database):
        """Test successful vector index creation."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                CreateVectorIndexRequest(
                    label="Document",
                    property_name="embedding",
                    metric=VectorMetric.COSINE,
                ).model_dump(),
                get_qualified_class_name(CreateVectorIndexRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = CreateVectorIndexResponse.model_validate(results[0].payload)
            assert response.label == "Document"
            assert response.property_name == "embedding"
            assert response.metric == "cosine"
            mock_database.create_vector_index.assert_called_once_with("Document", "embedding", "cosine")

    def test_list_labels_success(self, agent_spec, generator, mock_database):
        """Test successful label listing."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                ListLabelsRequest().model_dump(),
                get_qualified_class_name(ListLabelsRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = ListLabelsResponse.model_validate(results[0].payload)
            assert response.labels == ["Label1", "Label2"]
            mock_database.list_labels.assert_called_once()

    def test_list_edge_types_success(self, agent_spec, generator, mock_database):
        """Test successful edge type listing."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                ListEdgeTypesRequest().model_dump(),
                get_qualified_class_name(ListEdgeTypesRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = ListEdgeTypesResponse.model_validate(results[0].payload)
            assert response.edge_types == ["KNOWS", "LIKES"]
            mock_database.list_edge_types.assert_called_once()

    def test_get_label_info_success(self, agent_spec, generator, mock_database):
        """Test successful label info retrieval."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                GetLabelInfoRequest(label="Person").model_dump(),
                get_qualified_class_name(GetLabelInfoRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = GetLabelInfoResponse.model_validate(results[0].payload)
            assert response.label == "Person"
            assert response.properties == {"name": "string", "age": "int64"}
            mock_database.get_label_info.assert_called_once_with("Person")

    def test_get_schema_success(self, agent_spec, generator, mock_database):
        """Test successful schema retrieval."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                GetSchemaRequest().model_dump(),
                get_qualified_class_name(GetSchemaRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = GetSchemaResponse.model_validate(results[0].payload)
            assert response.db_schema == {"labels": ["Label1"], "edges": ["KNOWS"]}
            mock_database.get_schema.assert_called_once()

    def test_execute_success(self, agent_spec, generator, mock_database):
        """Test successful Cypher execution."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                ExecuteRequest(query="CREATE (n:Person {name: 'Alice'})").model_dump(),
                get_qualified_class_name(ExecuteRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = ExecuteResponse.model_validate(results[0].payload)
            assert response.success is True
            assert response.rows_affected == 5
            mock_database.execute.assert_called_once_with("CREATE (n:Person {name: 'Alice'})")

    def test_query_success(self, agent_spec, generator, mock_database):
        """Test successful Cypher query."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                QueryRequest(query="MATCH (n:Person) RETURN n.name, n.age").model_dump(),
                get_qualified_class_name(QueryRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = QueryResponse.model_validate(results[0].payload)
            assert response.count == 1
            assert response.results == [{"name": "Alice", "age": 30}]
            mock_database.query.assert_called_once_with("MATCH (n:Person) RETURN n.name, n.age")

    def test_query_with_params(self, agent_spec, generator, mock_database):
        """Test Cypher query with parameters."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                QueryRequest(
                    query="MATCH (n:Person {name: $name}) RETURN n",
                    params={"name": "Alice"},
                ).model_dump(),
                get_qualified_class_name(QueryRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = QueryResponse.model_validate(results[0].payload)
            assert response.count == 1
            mock_database.query.assert_called_once_with(
                "MATCH (n:Person {name: $name}) RETURN n",
                {"name": "Alice"},
            )

    def test_flush_success(self, agent_spec, generator, mock_database):
        """Test successful flush operation."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                FlushRequest().model_dump(),
                get_qualified_class_name(FlushRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = FlushResponse.model_validate(results[0].payload)
            assert response.success is True
            mock_database.flush.assert_called_once()

    def test_vector_search_success(self, agent_spec, generator, mock_database):
        """Test successful vector search."""
        mock_database.query.return_value = [
            {"vid": 1, "distance": 0.1},
            {"vid": 2, "distance": 0.2},
        ]

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                VectorSearchRequest(
                    label="Document",
                    property_name="embedding",
                    vector=[0.1, 0.2, 0.3],
                    k=10,
                ).model_dump(),
                get_qualified_class_name(VectorSearchRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = VectorSearchResponse.model_validate(results[0].payload)
            assert response.count == 2
            assert len(response.results) == 2
            assert response.results[0].vertex_id == 1
            assert response.results[0].distance == 0.1

    def test_vector_search_with_filter(self, agent_spec, generator, mock_database):
        """Test vector search with filter query."""
        mock_database.query.return_value = [{"vid": 1, "distance": 0.1}]

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                VectorSearchRequest(
                    label="Document",
                    property_name="embedding",
                    vector=[0.1, 0.2, 0.3],
                    k=5,
                    filter_query="n.category = 'tech'",
                ).model_dump(),
                get_qualified_class_name(VectorSearchRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = VectorSearchResponse.model_validate(results[0].payload)
            assert response.count == 1

    def test_insert_vertices_success(self, agent_spec, generator, mock_database):
        """Test successful bulk vertex insertion."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            vertices = [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
            ]

            msg = _build_message(
                generator,
                InsertVerticesRequest(label="Person", vertices=vertices).model_dump(),
                get_qualified_class_name(InsertVerticesRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = InsertVerticesResponse.model_validate(results[0].payload)
            assert response.count == 2
            assert response.success is True
            mock_database.bulk_insert_vertices.assert_called_once_with("Person", vertices)

    def test_insert_edges_success(self, agent_spec, generator, mock_database):
        """Test successful bulk edge insertion."""
        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            edges = [
                EdgeData(source_id=1, target_id=2, properties={"since": "2020"}),
                EdgeData(source_id=2, target_id=3, properties={"since": "2021"}),
            ]

            msg = _build_message(
                generator,
                InsertEdgesRequest(edge_type="KNOWS", edges=edges).model_dump(),
                get_qualified_class_name(InsertEdgesRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = InsertEdgesResponse.model_validate(results[0].payload)
            assert response.count == 2
            assert response.success is True
            # The agent converts EdgeData to tuples before passing to db
            mock_database.bulk_insert_edges.assert_called_once_with(
                "KNOWS",
                [(1, 2, {"since": "2020"}), (2, 3, {"since": "2021"})],
            )

    def test_insert_vertices_error(self, agent_spec, generator, mock_database):
        """Test bulk vertex insertion with error."""
        mock_database.bulk_insert_vertices.side_effect = Exception("Invalid property type")

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                InsertVerticesRequest(
                    label="Person",
                    vertices=[{"name": "Alice"}],
                ).model_dump(),
                get_qualified_class_name(InsertVerticesRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            assert results[0].format == get_qualified_class_name(ErrorMessage)
            error = ErrorMessage.model_validate(results[0].payload)
            assert error.error_type == "InsertVerticesError"
            assert "Invalid property type" in error.error_message

    def test_query_empty_results(self, agent_spec, generator, mock_database):
        """Test query returning empty results."""
        mock_database.query.return_value = None

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                QueryRequest(query="MATCH (n:NonExistent) RETURN n").model_dump(),
                get_qualified_class_name(QueryRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = QueryResponse.model_validate(results[0].payload)
            assert response.count == 0
            assert response.results == []

    def test_execute_non_integer_result(self, agent_spec, generator, mock_database):
        """Test execute returning non-integer result."""
        mock_database.execute.return_value = "OK"

        with patch("rustic_ai.unidb.agent.Database", return_value=mock_database):
            agent, results = wrap_agent_for_testing(agent_spec)

            msg = _build_message(
                generator,
                ExecuteRequest(query="CREATE INDEX idx").model_dump(),
                get_qualified_class_name(ExecuteRequest),
            )

            agent._on_message(msg)

            assert len(results) == 1
            response = ExecuteResponse.model_validate(results[0].payload)
            assert response.success is True
            assert response.rows_affected is None
