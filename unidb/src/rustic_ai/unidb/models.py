"""Version one public messages. Authorization and workflow status belong to the guild."""

from enum import Enum
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rustic_ai.core.guild.dsl import BaseAgentProps


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limits(StrictModel):
    timeout_ms: int = Field(default=5000, gt=0)
    max_query_memory_bytes: int = Field(default=67108864, gt=0)
    max_rows: int = Field(default=100, gt=0)
    max_output_bytes: int = Field(default=65536, gt=0)
    max_input_bytes: int = Field(default=65536, gt=0)
    max_statements: int = Field(default=16, gt=0)
    max_conflict_retries: Literal[0] = 0


class Statement(StrictModel):
    kind: Literal["cypher", "locy"] = "cypher"
    text: str = Field(min_length=1)


class Assertion(StrictModel):
    row_count: int = Field(ge=0)
    column: str | None = None
    operator: Literal["eq", "approx"] | None = None
    value: Any = None
    abs_tolerance: float = Field(default=0, ge=0)


class Check(StrictModel):
    phase: Literal["pre", "post"]
    statement: Statement
    expect: Assertion


class Operation(StrictModel):
    name: str = Field(min_length=1)
    kind: Literal["query", "evaluate", "explain", "mutation", "scenario"]
    parameters_schema: dict[str, Any]
    query: str | None = None
    program: str | None = None
    columns: list[str] = Field(default_factory=list)
    statements: list[Statement] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    statement_expectations: list[dict[str, int]] = Field(default_factory=list)
    isolation: Literal["scratch"] = "scratch"
    before: list[Statement] = Field(default_factory=list)
    mutations: list[Statement] = Field(default_factory=list)
    after: list[Statement] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class Catalog(StrictModel):
    revision: str = "v1"
    operations: list[Operation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operations(self):
        names = set()
        for op in self.operations:
            if op.name in names:
                raise ValueError("Duplicate operation name")
            names.add(op.name)
            Draft202012Validator.check_schema(op.parameters_schema)
            if (
                op.parameters_schema.get("type") != "object"
                or op.parameters_schema.get("additionalProperties") is not False
            ):
                raise ValueError("Catalog parameters must be closed objects")
            required = {
                "query": op.query,
                "evaluate": op.program,
                "explain": op.program,
                "mutation": op.statements,
                "scenario": op.mutations,
            }
            if not required[op.kind]:
                raise ValueError(f"{op.kind} operation lacks its execution definition")
            for check in op.checks:
                if check.expect.operator and not check.expect.column:
                    raise ValueError("Comparison check needs column")
                if check.expect.operator == "approx" and check.expect.abs_tolerance <= 0:
                    raise ValueError("Approximate check needs positive tolerance")
        return self


class UniDBAgentConfig(BaseAgentProps):
    model_config = ConfigDict(extra="forbid")
    binding_id: str = Field(min_length=1)
    admission: Literal["require_database_ready"] = "require_database_ready"
    limits: Limits = Field(default_factory=Limits)
    raw_operations_enabled: bool = False
    operation_catalog: Catalog = Field(default_factory=Catalog)


class Request(StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str = Field(min_length=1, max_length=256)
    correlation_id: str = Field(min_length=1, max_length=256)
    limits: dict[str, int] | None = None


class EffectRequest(Request):
    operation_id: str = Field(min_length=1, max_length=256)


class NamedRequest(Request):
    operation: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    view: dict[str, Any] | None = None


class DBMutateRequest(NamedRequest):
    operation_id: str = Field(min_length=1, max_length=256)


class DBQueryRequest(NamedRequest):
    pass


class DBQueryPlanRequest(NamedRequest):
    pass


class DBQueryProfileRequest(NamedRequest):
    pass


class DBEvaluateRequest(NamedRequest):
    pass


class DBExplainRequest(NamedRequest):
    pass


class DBScenarioRequest(NamedRequest):
    pass


class DBCapabilitiesRequest(Request):
    pass


class DBHealthRequest(Request):
    pass


class DBOperationStatusRequest(Request):
    operation_id: str = Field(min_length=1)


class Response(StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str
    correlation_id: str
    binding_id: str
    outcome: Literal["succeeded"] = "succeeded"
    result: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorDetail(StrictModel):
    code: str
    stage: str
    retryable: bool = False
    effect: Literal["not_started", "rolled_back", "committed", "unknown"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DBFailure(StrictModel):
    protocol_version: Literal[1] = 1
    request_id: str
    correlation_id: str
    binding_id: str
    outcome: Literal["failed", "unknown"] = "failed"
    error: ErrorDetail
    metadata: dict[str, Any] = Field(default_factory=dict)


class PropertyType(str, Enum):
    STRING = "string"
    INT64 = "int64"
    FLOAT64 = "float64"
    BOOL = "bool"
    BYTES = "bytes"


class IndexType(str, Enum):
    BTREE = "btree"


class VectorMetric(str, Enum):
    COSINE = "cosine"
    L2 = "l2"


class CreateLabelRequest(EffectRequest):
    label: str = Field(min_length=1)


class CreateEdgeTypeRequest(EffectRequest):
    edge_type: str = Field(min_length=1)
    source_labels: list[str] = Field(min_length=1)
    target_labels: list[str] = Field(min_length=1)


class AddPropertyRequest(EffectRequest):
    label: str
    property_name: str
    property_type: PropertyType
    nullable: bool = True
    vector_dimension: int | None = Field(default=None, gt=0)


class CreateScalarIndexRequest(EffectRequest):
    label: str
    property_name: str
    index_type: IndexType = IndexType.BTREE


class CreateVectorIndexRequest(EffectRequest):
    label: str
    property_name: str
    metric: VectorMetric = VectorMetric.COSINE


class ListLabelsRequest(Request):
    pass


class ListEdgeTypesRequest(Request):
    pass


class GetLabelInfoRequest(Request):
    label: str


class GetSchemaRequest(Request):
    pass


class QueryRequest(Request):
    query: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(EffectRequest):
    query: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class FlushRequest(EffectRequest):
    pass


class VectorSearchRequest(Request):
    label: str
    property_name: str
    vector: list[float] = Field(min_length=1)
    k: int = Field(default=10, gt=0)
    filter_query: str | None = None
    filter_params: dict[str, Any] = Field(default_factory=dict)


class VectorSearchResult(StrictModel):
    vertex_id: Any
    distance: float
    properties: dict[str, Any] = Field(default_factory=dict)


class InsertVerticesRequest(EffectRequest):
    label: str
    vertices: list[dict[str, Any]] = Field(min_length=1)


class EdgeData(StrictModel):
    source_ext_id: str = Field(min_length=1)
    target_ext_id: str = Field(min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)


class InsertEdgesRequest(EffectRequest):
    edge_type: str
    edges: list[EdgeData] = Field(min_length=1)


class DBBulkStatusRequest(Request):
    load_id: str


class DBCapabilitiesResponse(Response):
    pass


class DBHealthResponse(Response):
    pass


class DBQueryResponse(Response):
    pass


class DBEvaluateResponse(Response):
    pass


class DBExplainResponse(Response):
    pass


class DBMutateResponse(Response):
    pass


class DBScenarioResponse(Response):
    pass


class DBOperationStatusResponse(Response):
    pass


class DBBulkStatusResponse(Response):
    pass


class CreateLabelResponse(Response):
    pass


class CreateEdgeTypeResponse(Response):
    pass


class AddPropertyResponse(Response):
    pass


class CreateScalarIndexResponse(Response):
    pass


class CreateVectorIndexResponse(Response):
    pass


class ListLabelsResponse(Response):
    pass


class ListEdgeTypesResponse(Response):
    pass


class GetLabelInfoResponse(Response):
    pass


class GetSchemaResponse(Response):
    pass


class QueryResponse(Response):
    pass


class ExecuteResponse(Response):
    pass


class FlushResponse(Response):
    pass


class VectorSearchResponse(Response):
    pass


class InsertVerticesResponse(Response):
    pass


class InsertEdgesResponse(Response):
    pass


class DBQueryPlanResponse(Response):
    pass


class DBQueryProfileResponse(Response):
    pass
