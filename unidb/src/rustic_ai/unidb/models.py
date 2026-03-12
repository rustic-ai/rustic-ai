from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.dsl import BaseAgentProps

# ============================================================================
# Enums
# ============================================================================


class PropertyType(str, Enum):
    """Supported property types in UniDB."""

    STRING = "string"
    INT64 = "int64"
    FLOAT64 = "float64"
    BOOL = "bool"
    BYTES = "bytes"


class IndexType(str, Enum):
    """Supported scalar index types."""

    BTREE = "btree"


class VectorMetric(str, Enum):
    """Supported vector distance metrics."""

    COSINE = "cosine"
    L2 = "l2"


# ============================================================================
# Configuration
# ============================================================================


class UniDBAgentConfig(BaseAgentProps):
    """Configuration for UniDB Agent."""

    db_path: str = Field(description="Path to the UniDB database file")


# ============================================================================
# Schema Operation Models
# ============================================================================


class CreateLabelRequest(BaseModel):
    """Request to create a new node label."""

    label: str = Field(description="Name of the label to create")


class CreateLabelResponse(BaseModel):
    """Response for label creation."""

    label: str
    success: bool = True


class CreateEdgeTypeRequest(BaseModel):
    """Request to create a new edge type."""

    edge_type: str = Field(description="Name of the edge type")
    source_labels: List[str] = Field(description="Allowed source node labels")
    target_labels: List[str] = Field(description="Allowed target node labels")


class CreateEdgeTypeResponse(BaseModel):
    """Response for edge type creation."""

    edge_type: str
    success: bool = True


class AddPropertyRequest(BaseModel):
    """Request to add a property to a label."""

    label: str = Field(description="Label to add property to")
    property_name: str = Field(description="Name of the property")
    property_type: PropertyType = Field(description="Type of the property")
    nullable: bool = Field(default=True, description="Whether the property can be null")
    vector_dimension: Optional[int] = Field(
        default=None,
        description="For vector properties, the dimension of the vector",
    )


class AddPropertyResponse(BaseModel):
    """Response for property addition."""

    label: str
    property_name: str
    success: bool = True


class CreateScalarIndexRequest(BaseModel):
    """Request to create a scalar index."""

    label: str = Field(description="Label to create index on")
    property_name: str = Field(description="Property to index")
    index_type: IndexType = Field(default=IndexType.BTREE, description="Type of index")


class CreateScalarIndexResponse(BaseModel):
    """Response for scalar index creation."""

    label: str
    property_name: str
    success: bool = True


class CreateVectorIndexRequest(BaseModel):
    """Request to create a vector index."""

    label: str = Field(description="Label to create vector index on")
    property_name: str = Field(description="Vector property to index")
    metric: VectorMetric = Field(default=VectorMetric.COSINE, description="Distance metric")


class CreateVectorIndexResponse(BaseModel):
    """Response for vector index creation."""

    label: str
    property_name: str
    metric: str
    success: bool = True


# ============================================================================
# Schema Introspection Models
# ============================================================================


class ListLabelsRequest(BaseModel):
    """Request to list all labels."""

    request_type: str = Field(default="list_labels", description="Request type identifier")


class ListLabelsResponse(BaseModel):
    """Response containing all labels."""

    labels: List[str]


class ListEdgeTypesRequest(BaseModel):
    """Request to list all edge types."""

    request_type: str = Field(default="list_edge_types", description="Request type identifier")


class ListEdgeTypesResponse(BaseModel):
    """Response containing all edge types."""

    edge_types: List[str]


class GetLabelInfoRequest(BaseModel):
    """Request to get information about a label."""

    label: str = Field(description="Label to get info for")


class GetLabelInfoResponse(BaseModel):
    """Response containing label information."""

    label: str
    properties: Dict[str, Any]


class GetSchemaRequest(BaseModel):
    """Request to get the full database schema."""

    request_type: str = Field(default="get_schema", description="Request type identifier")


class GetSchemaResponse(BaseModel):
    """Response containing the full schema."""

    db_schema: Dict[str, Any]


# ============================================================================
# Data Operation Models
# ============================================================================


class ExecuteRequest(BaseModel):
    """Request to execute a Cypher command."""

    query: str = Field(description="Cypher query to execute")


class ExecuteResponse(BaseModel):
    """Response for execute operation."""

    success: bool = True
    rows_affected: Optional[int] = None


class QueryRequest(BaseModel):
    """Request to run a Cypher query with optional parameters."""

    query: str = Field(description="Cypher query to run")
    params: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")


class QueryResponse(BaseModel):
    """Response containing query results."""

    results: List[Dict[str, Any]]
    count: int


class FlushRequest(BaseModel):
    """Request to flush changes to disk."""

    request_type: str = Field(default="flush", description="Request type identifier")


class FlushResponse(BaseModel):
    """Response for flush operation."""

    success: bool = True


# ============================================================================
# Vector Search Models
# ============================================================================


class VectorSearchRequest(BaseModel):
    """Request to perform a vector similarity search."""

    label: str = Field(description="Label to search on")
    property_name: str = Field(description="Vector property to search")
    vector: List[float] = Field(description="Query vector")
    k: int = Field(default=10, description="Number of results to return")
    filter_query: Optional[str] = Field(
        default=None,
        description="Optional Cypher filter expression",
    )


class VectorSearchResult(BaseModel):
    """A single vector search result."""

    vertex_id: Any
    distance: float
    properties: Dict[str, Any] = Field(default_factory=dict)


class VectorSearchResponse(BaseModel):
    """Response containing vector search results."""

    results: List[VectorSearchResult]
    count: int


# ============================================================================
# Bulk Operation Models
# ============================================================================


class InsertVerticesRequest(BaseModel):
    """Request to bulk insert vertices."""

    label: str = Field(description="Label for the vertices")
    vertices: List[Dict[str, Any]] = Field(description="List of vertex property dictionaries")


class InsertVerticesResponse(BaseModel):
    """Response for bulk vertex insertion."""

    count: int
    success: bool = True


class EdgeData(BaseModel):
    """Data for a single edge to insert."""

    source_id: Any = Field(description="Source vertex ID")
    target_id: Any = Field(description="Target vertex ID")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Edge properties")


class InsertEdgesRequest(BaseModel):
    """Request to bulk insert edges."""

    edge_type: str = Field(description="Type of edges to insert")
    edges: List[EdgeData] = Field(description="List of edges to insert")


class InsertEdgesResponse(BaseModel):
    """Response for bulk edge insertion."""

    count: int
    success: bool = True
