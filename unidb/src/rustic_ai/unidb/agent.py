"""
UniDB Agent for Rustic AI framework.

This agent provides access to UniDB operations including schema management,
data operations, vector search, and bulk loading.
"""

import dataclasses
from typing import Any

from uni_db import Database

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor


def _to_dict(obj: Any) -> Any:
    """Convert various object types to dict for serialization."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "_asdict"):  # namedtuple
        return {k: _to_dict(v) for k, v in obj._asdict().items()}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if hasattr(obj, "__dict__") and obj.__dict__:
        return {k: _to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    # Check for __slots__ on the class hierarchy
    slots = set()
    for cls in type(obj).__mro__:
        if hasattr(cls, "__slots__"):
            slots.update(s for s in cls.__slots__ if not s.startswith("_"))
    if slots:
        return {slot: _to_dict(getattr(obj, slot, None)) for slot in slots}
    # Fallback: try to extract public attributes via dir()
    result = {}
    for attr in dir(obj):
        if not attr.startswith("_") and not callable(getattr(obj, attr, None)):
            try:
                result[attr] = _to_dict(getattr(obj, attr))
            except Exception:
                pass
    if result:
        return result
    # Last resort: convert to string
    return str(obj)
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
    ExecuteRequest,
    ExecuteResponse,
    FlushRequest,
    FlushResponse,
    GetLabelInfoRequest,
    GetLabelInfoResponse,
    GetSchemaRequest,
    GetSchemaResponse,
    InsertEdgesRequest,
    InsertEdgesResponse,
    InsertVerticesRequest,
    InsertVerticesResponse,
    ListEdgeTypesRequest,
    ListEdgeTypesResponse,
    ListLabelsRequest,
    ListLabelsResponse,
    QueryRequest,
    QueryResponse,
    UniDBAgentConfig,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
)


class UniDBAgent(Agent[UniDBAgentConfig]):
    """
    Agent that provides access to UniDB database operations.

    Supports:
    - Schema operations: create labels, edge types, properties, and indexes
    - Data operations: execute Cypher commands, run queries
    - Vector search: K-NN similarity search with optional filtering
    - Bulk operations: batch insert vertices and edges
    - Schema introspection: list labels, edge types, get schema info
    """

    def __init__(self):
        self._db: Database = Database(self.config.db_path)

    def _send_error(self, ctx: ProcessContext, error_type: str, message: str):
        """Send an error response."""
        ctx.send_error(
            ErrorMessage(
                agent_type=self.get_qualified_class_name(),
                error_type=error_type,
                error_message=message,
            )
        )

    @processor(CreateLabelRequest)
    async def create_label(self, ctx: ProcessContext[CreateLabelRequest]):
        """Create a new node label."""
        try:
            self._db.create_label(ctx.payload.label)
            ctx.send(CreateLabelResponse(label=ctx.payload.label))
        except Exception as e:
            self._send_error(ctx, "CreateLabelError", str(e))

    @processor(CreateEdgeTypeRequest)
    async def create_edge_type(self, ctx: ProcessContext[CreateEdgeTypeRequest]):
        """Create a new edge type."""
        try:
            self._db.create_edge_type(
                ctx.payload.edge_type,
                ctx.payload.source_labels,
                ctx.payload.target_labels,
            )
            ctx.send(CreateEdgeTypeResponse(edge_type=ctx.payload.edge_type))
        except Exception as e:
            self._send_error(ctx, "CreateEdgeTypeError", str(e))

    @processor(AddPropertyRequest)
    async def add_property(self, ctx: ProcessContext[AddPropertyRequest]):
        """Add a property to a label."""
        try:
            prop_type = ctx.payload.property_type.value
            if ctx.payload.vector_dimension:
                prop_type = f"vector[{ctx.payload.vector_dimension}]"
            self._db.add_property(
                ctx.payload.label,
                ctx.payload.property_name,
                prop_type,
                ctx.payload.nullable,
            )
            ctx.send(
                AddPropertyResponse(
                    label=ctx.payload.label,
                    property_name=ctx.payload.property_name,
                )
            )
        except Exception as e:
            self._send_error(ctx, "AddPropertyError", str(e))

    @processor(CreateScalarIndexRequest)
    async def create_scalar_index(self, ctx: ProcessContext[CreateScalarIndexRequest]):
        """Create a scalar index on a property."""
        try:
            self._db.create_scalar_index(
                ctx.payload.label,
                ctx.payload.property_name,
                ctx.payload.index_type.value,
            )
            ctx.send(
                CreateScalarIndexResponse(
                    label=ctx.payload.label,
                    property_name=ctx.payload.property_name,
                )
            )
        except Exception as e:
            self._send_error(ctx, "CreateScalarIndexError", str(e))

    @processor(CreateVectorIndexRequest)
    async def create_vector_index(self, ctx: ProcessContext[CreateVectorIndexRequest]):
        """Create a vector index for similarity search."""
        try:
            self._db.create_vector_index(
                ctx.payload.label,
                ctx.payload.property_name,
                ctx.payload.metric.value,
            )
            ctx.send(
                CreateVectorIndexResponse(
                    label=ctx.payload.label,
                    property_name=ctx.payload.property_name,
                    metric=ctx.payload.metric.value,
                )
            )
        except Exception as e:
            self._send_error(ctx, "CreateVectorIndexError", str(e))

    # ========================================================================
    # Schema Introspection
    # ========================================================================

    @processor(ListLabelsRequest)
    async def list_labels(self, ctx: ProcessContext[ListLabelsRequest]):
        """List all labels in the database."""
        try:
            labels = self._db.list_labels()
            ctx.send(ListLabelsResponse(labels=labels))
        except Exception as e:
            self._send_error(ctx, "ListLabelsError", str(e))

    @processor(ListEdgeTypesRequest)
    async def list_edge_types(self, ctx: ProcessContext[ListEdgeTypesRequest]):
        """List all edge types in the database."""
        try:
            edge_types = self._db.list_edge_types()
            ctx.send(ListEdgeTypesResponse(edge_types=edge_types))
        except Exception as e:
            self._send_error(ctx, "ListEdgeTypesError", str(e))

    @processor(GetLabelInfoRequest)
    async def get_label_info(self, ctx: ProcessContext[GetLabelInfoRequest]):
        """Get information about a specific label."""
        try:
            info = self._db.get_label_info(ctx.payload.label)
            info = _to_dict(info)
            ctx.send(GetLabelInfoResponse(label=ctx.payload.label, properties=info))
        except Exception as e:
            self._send_error(ctx, "GetLabelInfoError", str(e))

    @processor(GetSchemaRequest)
    async def get_schema(self, ctx: ProcessContext[GetSchemaRequest]):
        """Get the full database schema."""
        try:
            schema = self._db.get_schema()
            schema = _to_dict(schema)
            ctx.send(GetSchemaResponse(db_schema=schema))
        except Exception as e:
            self._send_error(ctx, "GetSchemaError", str(e))

    # ========================================================================
    # Data Operations
    # ========================================================================

    @processor(ExecuteRequest)
    async def execute(self, ctx: ProcessContext[ExecuteRequest]):
        """Execute a Cypher command (CREATE, DELETE, SET, etc.)."""
        try:
            result = self._db.execute(ctx.payload.query)
            rows_affected = result if isinstance(result, int) else None
            ctx.send(ExecuteResponse(success=True, rows_affected=rows_affected))
        except Exception as e:
            self._send_error(ctx, "ExecuteError", str(e))

    @processor(QueryRequest)
    async def query(self, ctx: ProcessContext[QueryRequest]):
        """Run a Cypher query and return results."""
        try:
            if ctx.payload.params:
                results = self._db.query(ctx.payload.query, ctx.payload.params)
            else:
                results = self._db.query(ctx.payload.query)
            result_list = list(results) if results else []
            ctx.send(QueryResponse(results=result_list, count=len(result_list)))
        except Exception as e:
            self._send_error(ctx, "QueryError", str(e))

    @processor(FlushRequest)
    async def flush(self, ctx: ProcessContext[FlushRequest]):
        """Flush changes to disk."""
        try:
            self._db.flush()
            ctx.send(FlushResponse(success=True))
        except Exception as e:
            self._send_error(ctx, "FlushError", str(e))

    # ========================================================================
    # Vector Search
    # ========================================================================

    @processor(VectorSearchRequest)
    async def vector_search(self, ctx: ProcessContext[VectorSearchRequest]):
        """Perform a vector similarity search."""
        try:
            req = ctx.payload

            # Build the vector search query
            vector_str = "[" + ", ".join(str(v) for v in req.vector) + "]"
            query = f"""
                CALL uni.vector.query('{req.label}', '{req.property_name}', {vector_str}, {req.k})
                YIELD vid, distance
            """

            if req.filter_query:
                query += f" WHERE {req.filter_query}"

            query += " RETURN vid, distance"

            results = self._db.query(query)
            result_list = []
            for row in results or []:
                result_list.append(
                    VectorSearchResult(
                        vertex_id=row.get("vid"),
                        distance=row.get("distance", 0.0),
                        properties=row,
                    )
                )

            ctx.send(VectorSearchResponse(results=result_list, count=len(result_list)))
        except Exception as e:
            self._send_error(ctx, "VectorSearchError", str(e))

    # ========================================================================
    # Bulk Operations
    # ========================================================================

    @processor(InsertVerticesRequest)
    async def insert_vertices(self, ctx: ProcessContext[InsertVerticesRequest]):
        """Bulk insert vertices."""
        try:
            self._db.bulk_insert_vertices(ctx.payload.label, ctx.payload.vertices)
            ctx.send(
                InsertVerticesResponse(
                    count=len(ctx.payload.vertices),
                    success=True,
                )
            )
        except Exception as e:
            self._send_error(ctx, "InsertVerticesError", str(e))

    @processor(InsertEdgesRequest)
    async def insert_edges(self, ctx: ProcessContext[InsertEdgesRequest]):
        """Bulk insert edges."""
        try:
            # Convert EdgeData objects to tuples for the database
            edges_tuples = [(edge.source_id, edge.target_id, edge.properties) for edge in ctx.payload.edges]
            self._db.bulk_insert_edges(ctx.payload.edge_type, edges_tuples)
            ctx.send(
                InsertEdgesResponse(
                    count=len(ctx.payload.edges),
                    success=True,
                )
            )
        except Exception as e:
            self._send_error(ctx, "InsertEdgesError", str(e))
