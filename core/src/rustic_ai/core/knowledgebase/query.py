from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FilterOp(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NIN = "nin"
    EXISTS = "exists"


class FilterClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: FilterOp
    value: Any = None

    @model_validator(mode="after")
    def _validate_value(self) -> "FilterClause":
        if self.op in {FilterOp.IN, FilterOp.NIN}:
            if not isinstance(self.value, (list, tuple, set)):
                raise ValueError(f"{self.op} requires a list/tuple/set value")
        elif self.op == FilterOp.EXISTS:
            if not isinstance(self.value, bool):
                raise ValueError("EXISTS requires a boolean value")
        return self


class BoolFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must: List[FilterClause] = Field(default_factory=list)
    should: List[FilterClause] = Field(default_factory=list)
    must_not: List[FilterClause] = Field(default_factory=list)


class HighlightOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    fields: List[str] = Field(default_factory=lambda: ["content"])  # logical field names
    max_fragments: int = Field(1, gt=0)
    fragment_size: int = Field(160, gt=0)


class AggregationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: Dict[str, str] = Field(default_factory=dict, description="aggregation_name -> field_name")


class RerankStrategy(str, Enum):
    NONE = "none"
    RRF = "rrf"
    LINEAR = "linear"
    CROSS_ENCODER = "cross_encoder"
    LLM = "llm"


class RerankOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: RerankStrategy = RerankStrategy.NONE
    top_n: int = Field(100, gt=0)
    model: Optional[str] = None
    batch_size: int = Field(32, gt=0)
    score_field: str = "rerank_score"


class ExpansionMethod(str, Enum):
    SEMANTIC = "semantic"
    SYNONYM = "synonym"
    LLM = "llm"


class QueryExpansion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    method: ExpansionMethod = ExpansionMethod.SEMANTIC
    max_expansions: int = Field(3, gt=0)
    model: Optional[str] = None


class FusionStrategy(str, Enum):
    LINEAR = "linear"
    RRF = "rrf"


class HybridOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dense_weight: float = Field(0.5, ge=0.0)
    sparse_weight: float = Field(0.5, ge=0.0)
    fusion_strategy: FusionStrategy = FusionStrategy.LINEAR

    @model_validator(mode="after")
    def _normalize(self) -> "HybridOptions":
        total = float(self.dense_weight) + float(self.sparse_weight)
        if total == 0:
            raise ValueError("At least one of dense_weight or sparse_weight must be > 0")
        self.dense_weight = float(self.dense_weight) / total
        self.sparse_weight = float(self.sparse_weight) / total
        return self


class SearchTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str
    vector_column: str
    weight: float = Field(1.0, gt=0)
    query_vector: Optional[List[float]] = Field(
        default=None,
        description="Optional per-target dense vector. If present, overrides any global vector usage.",
    )


class SearchQuery(BaseModel):
    """Query-as-data model for hybrid and cross-table search.

    Orchestrator-level fields (expansion, rerank, multi-target fanout) live here.
    Backend-level retrieval details are passed through (filters, hybrid options, aggregations).
    """

    model_config = ConfigDict(extra="forbid")

    # Core input signals (global text)
    text: Optional[str] = Field(
        None, description="Primary query text. Used for keyword search and/or to generate query vectors."
    )

    # Search scopes
    targets: List[SearchTarget] = Field(
        ..., min_length=1, description="Tables/vector columns to search across in parallel."
    )

    # Backend controls
    hybrid: Optional[HybridOptions] = Field(
        None, description="Enable backend hybrid (dense+sparse) retrieval with score fusion."
    )
    filter: Optional[BoolFilter] = Field(None, description="Structured boolean filter to apply.")
    aggregations: Optional[AggregationRequest] = None

    # Orchestrator controls
    expansion: Optional[QueryExpansion] = None
    rerank: RerankOptions = Field(default_factory=RerankOptions)
    rerank_candidates: int = Field(100, gt=0, description="Initial candidates per overall query before reranking.")

    # Presentation
    limit: int = Field(10, gt=0)
    offset: int = Field(0, ge=0)
    highlight: Optional[HighlightOptions] = None
    explain: bool = False


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Identifier of the matched chunk")
    score: float = Field(description="Similarity score (higher is better unless backend returns distance)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Optional scalar fields returned by backend")


class NormalizationMethod(str, Enum):
    NONE = "none"
    MINMAX = "minmax"
    ZSCORE = "zscore"
    DISTANCE_TO_SIMILARITY = "distance_to_similarity"


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    hybrid_score: Optional[float] = None
    rerank_score: Optional[float] = None


class ExplainTargetStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_name: str
    vector_column: str
    weight: float = 1.0
    requested: int = 0
    returned: int = 0
    duration_ms: float = 0.0
    norm_min: float | None = None
    norm_max: float | None = None


class ExplainData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fusion: FusionStrategy = FusionStrategy.LINEAR
    weighting: Optional[HybridOptions] = None
    targets_used: List[ExplainTargetStat] = Field(default_factory=list)
    retrieval_counts: Dict[str, int] = Field(default_factory=dict)
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    rerank_used: bool = False
    rerank_strategy: Optional[RerankStrategy] = None
    rerank_model: Optional[str] = None
    normalization_method: NormalizationMethod = NormalizationMethod.MINMAX
    trace_id: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class SearchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: List[SearchResult] = Field(default_factory=list)
    explain: Optional[ExplainData] = None
    search_duration_ms: Optional[float] = None
