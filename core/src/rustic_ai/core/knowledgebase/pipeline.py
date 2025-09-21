from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .model import Modality
from .schema import KBSchema


class SchemaRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: str
    schema_version: int


class TargetSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: Modality
    mimetype: Optional[str] = Field(default=None, description="Exact or glob like 'text/*'")


class ChunkerRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunker_id: str
    policy_version: str


class ProjectorRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projector_id: str
    projector_version: str
    target_modality: Modality = Modality.TEXT
    target_mimetype: Optional[str] = Field(default=None, description="Optional precise target mimetype")


class EmbedderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedder_id: str
    embedder_version: str


class StorageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vector_column: str = Field(description="Name of vector column to upsert into (table resolved via KBSchema)")


class PipelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = 1
    description: Optional[str] = None

    schema_ref: SchemaRef
    target: TargetSelector
    chunker: ChunkerRef
    projector: Optional[ProjectorRef] = None
    embedder: EmbedderRef
    storage: StorageSpec

    @model_validator(mode="after")
    def _validate_projection(self) -> "PipelineSpec":
        if self.projector:
            if self.projector.target_modality != Modality.TEXT:
                raise ValueError("Currently only projection to text is supported")
            if self.projector.target_mimetype:
                major = (
                    self.projector.target_mimetype.split("/", 1)[0].lower()
                    if "/" in self.projector.target_mimetype
                    else None
                )
                if major != self.projector.target_modality.value:
                    raise ValueError("projector.target_mimetype must match target_modality's major type")
        return self

    # Helper: given a KBSchema, resolve the destination table by (post-projection) modality/mimetype
    def resolve_storage_table(self, schema: KBSchema) -> Optional[str]:
        # Determine effective modality/mimetype after projection
        modality = self.projector.target_modality if self.projector else self.target.modality
        mimetype = self.projector.target_mimetype if self.projector else self.target.mimetype
        return schema.routing.resolve_table(modality.value, mimetype)

    # Helper: validate that the vector column exists in resolved table
    def validate_against_schema(self, schema: KBSchema) -> None:
        table_name = self.resolve_storage_table(schema)
        if not table_name:
            raise ValueError("No routing match in KBSchema for the pipeline's target")
        table = next((t for t in schema.tables if t.name == table_name), None)
        if not table:
            raise ValueError(f"Resolved table '{table_name}' not found in schema")
        if not any(vc.name == self.storage.vector_column for vc in table.vector_columns):
            raise ValueError(f"Vector column '{self.storage.vector_column}' not defined on table '{table_name}'")
