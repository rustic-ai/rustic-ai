import inspect
from typing import Any, Dict, List, Optional, Type, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rustic_ai.core.utils.basic_class_utils import get_class_from_name

from .pipeline import PipelineSpec
from .plugins import ChunkerPlugin, EmbedderPlugin, ProjectorPlugin, RerankerPlugin
from .schema import KBSchema

T = TypeVar("T")


def build_plugin_map(value: Any, base_type: Type[T]) -> Dict[str, T]:
    """Build a plugin map from instances or dict specs (with kind)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"Expected dict[str, {base_type.__name__}] or specs")

    out: Dict[str, T] = {}
    for name, spec in value.items():
        if not isinstance(name, str) or not name:
            raise TypeError("Plugin map keys must be non-empty strings")

        if isinstance(spec, base_type):
            out[name] = cast(T, spec)
            continue

        if isinstance(spec, dict):
            cls_path = spec.get("kind")
            if not isinstance(cls_path, str):
                raise TypeError(f"Plugin '{name}': missing 'kind' (FQCN)")
            cls: Type[Any] = get_class_from_name(cls_path)
            if not issubclass(cls, base_type):
                raise TypeError(f"Plugin '{name}': {cls_path!r} is not a {base_type.__name__}")
            # If the class is abstract, synthesize a minimal concrete subclass so config serde can succeed
            if inspect.isabstract(cls):
                if issubclass(cls, ChunkerPlugin):

                    async def split(self, knol):  # type: ignore
                        raise NotImplementedError("ChunkerPlugin stub")

                    cls = cast(Type[Any], type(f"Configured{cls.__name__}", (cls,), {"split": split}))
                elif issubclass(cls, EmbedderPlugin):

                    async def embed(self, chunk):  # type: ignore
                        raise NotImplementedError("EmbedderPlugin stub")

                    def get_dimension(self) -> int:  # type: ignore
                        return 0

                    cls = cast(
                        Type[Any],
                        type(f"Configured{cls.__name__}", (cls,), {"embed": embed, "get_dimension": get_dimension}),
                    )
                elif issubclass(cls, ProjectorPlugin):

                    async def project(self, chunk, file_path=None):  # type: ignore
                        raise NotImplementedError("ProjectorPlugin stub")

                    cls = cast(Type[Any], type(f"Configured{cls.__name__}", (cls,), {"project": project}))
            kwargs = {k: v for k, v in spec.items() if k != "kind"}
            out[name] = cast(T, cls(**kwargs))
            continue

        raise TypeError(f"Plugin '{name}': expected {base_type.__name__} instance or dict spec")

    return out


class PluginRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Logical IDs → plugin instances (coerced from dict specs with 'kind')
    chunkers: Dict[str, ChunkerPlugin] = Field(default_factory=dict)
    projectors: Dict[str, ProjectorPlugin] = Field(default_factory=dict)
    embedders: Dict[str, EmbedderPlugin] = Field(default_factory=dict)
    rerankers: Dict[str, RerankerPlugin] = Field(default_factory=dict)

    @field_validator("chunkers", mode="before")
    @classmethod
    def _coerce_chunkers(cls, v):
        return build_plugin_map(v, ChunkerPlugin)

    @field_validator("projectors", mode="before")
    @classmethod
    def _coerce_projectors(cls, v):
        return build_plugin_map(v, ProjectorPlugin)

    @field_validator("embedders", mode="before")
    @classmethod
    def _coerce_embedders(cls, v):
        return build_plugin_map(v, EmbedderPlugin)

    @field_validator("rerankers", mode="before")
    @classmethod
    def _coerce_rerankers(cls, v):
        return build_plugin_map(v, RerankerPlugin)


class KBConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = 1
    description: Optional[str] = None

    # Either provide a concrete schema under the alias 'schema' OR provide a 'schema_infer' block
    kb_schema: KBSchema = Field(alias="schema")
    # Accept dict or object; resolved in a pre-validator to a concrete KBSchema
    schema_infer: Optional[Any] = None
    plugins: PluginRegistry
    pipelines: List[PipelineSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _resolve_schema(cls, data):
        # Allow callers to provide 'schema_infer' instead of a concrete 'schema'
        if not isinstance(data, dict):
            return data
        if data.get("schema") is not None:
            return data
        si = data.get("schema_infer")
        if not si:
            return data
        # Import lazily to avoid circular imports
        from .schema_infer import SchemaInferConfig, infer_kb_schema

        cfg = si if isinstance(si, SchemaInferConfig) else SchemaInferConfig(**si)
        schema = infer_kb_schema(cfg)
        data["schema"] = schema
        return data

    @model_validator(mode="after")
    def _validate_references(self) -> "KBConfig":
        # Ensure pipelines reference existing plugins by logical ids
        for p in self.pipelines:
            if p.chunker.chunker_id not in self.plugins.chunkers:
                raise ValueError(f"Pipeline {p.id}: unknown chunker_id '{p.chunker.chunker_id}'")
            if p.projector and p.projector.projector_id not in self.plugins.projectors:
                raise ValueError(f"Pipeline {p.id}: unknown projector_id '{p.projector.projector_id}'")
            if p.embedder.embedder_id not in self.plugins.embedders:
                raise ValueError(f"Pipeline {p.id}: unknown embedder_id '{p.embedder.embedder_id}'")

            # Validate pipeline against schema routing + vector column presence
            p.validate_against_schema(self.kb_schema)
        return self
