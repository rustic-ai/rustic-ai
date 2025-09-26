from __future__ import annotations

from fnmatch import fnmatch
from typing import Dict, List, Literal, Optional, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScalarType = Literal[
    "string",
    "text",
    "int",
    "float",
    "bool",
    "timestamp",
    "json",
    "array<string>",
    "array<int>",
    "array<float>",
]


DistanceType = Literal["cosine", "dot", "l2"]


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: ScalarType
    source: Literal["knol", "chunk", "meta"]
    selector: str = Field(description="Selector path in the source, e.g., chunk.index, meta.author")
    nullable: bool = True
    default: Optional[str] = None


class VectorIndexSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["hnsw", "ivf_flat", "flat", "pq", "diskann"]
    params: Dict[str, object] = Field(default_factory=dict)


class VectorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    dim: int
    distance: DistanceType = "cosine"
    index: VectorIndexSpec

    @field_validator("dim")
    @classmethod
    def _positive_dim(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Vector dim must be > 0")
        return v


class IndexSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal[
        "btree",
        "hash",
        "fulltext",
        "trigram",
        "gin",
        "gist",
        "keyword",
        "numeric",
    ]
    columns: Sequence[str] = Field(description="Column names or expressions, backend-mapped")
    options: Dict[str, object] = Field(default_factory=dict)


class TableMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: Optional[Literal["text", "image", "audio", "video"]] = None
    mimetype: Optional[str] = Field(default=None, description="Exact or glob like 'text/*'")


class TableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    match: TableMatch
    primary_key: Sequence[str]
    unique: Sequence[Sequence[str]] = Field(default_factory=list)
    partition_by: Sequence[str] = Field(default_factory=list)

    columns: List[ColumnSpec]
    vector_columns: List[VectorSpec] = Field(default_factory=list)
    indexes: List[IndexSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_columns_and_keys(self) -> "TableSpec":
        column_names: Set[str] = {c.name for c in self.columns}
        # primary keys must exist as columns
        for pk in self.primary_key:
            if pk not in column_names:
                raise ValueError(f"Primary key column '{pk}' not defined in columns")
        # unique sets must exist as columns
        for uniq in self.unique:
            for col in uniq:
                if col not in column_names:
                    raise ValueError(f"Unique key column '{col}' not defined in columns")
        # indexes columns must exist (best effort; allow expressions if contain non-alnum)
        for idx in self.indexes:
            for col in idx.columns:
                if col.isidentifier() and col not in column_names:
                    raise ValueError(f"Index column '{col}' not defined in columns for index {idx.name}")
        return self


class RoutingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: TableMatch
    table: str


class RoutingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: List[RoutingRule]

    def resolve_table(self, modality: Optional[str], mimetype: Optional[str]) -> Optional[str]:
        for rule in self.rules:
            m = rule.match
            if m.modality and modality and m.modality != modality:
                continue
            if m.mimetype:
                if not mimetype:
                    continue
                if not (m.mimetype == mimetype or fnmatch(mimetype, m.mimetype)):
                    continue
            return rule.table
        return None


class KBSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = 1
    description: Optional[str] = None
    backend_profile: Optional[str] = Field(default=None, description="DDL mapping hint, e.g., 'postgres'")

    routing: RoutingSpec
    tables: List[TableSpec]

    @model_validator(mode="after")
    def _validate_integrity(self) -> "KBSchema":
        table_names: Set[str] = {t.name for t in self.tables}
        if len(table_names) != len(self.tables):
            raise ValueError("Duplicate table names in schema")

        # Ensure routing targets exist
        for r in self.routing.rules:
            if r.table not in table_names:
                raise ValueError(f"Routing references unknown table '{r.table}'")

        return self
