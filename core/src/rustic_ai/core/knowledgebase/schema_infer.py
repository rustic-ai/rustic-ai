from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, Field

from .chunks import AudioChunk, ChunkBase, ImageChunk, TextChunk, VideoChunk
from .metadata import (
    AnyMetaPart,
    AudioMetaPart,
    CommonMetaPart,
    DocumentMetaPart,
    ImageMetaPart,
    VideoMetaPart,
)
from .model import Knol, Modality, Provenance
from .schema import (
    ColumnSpec,
    IndexSpec,
    KBSchema,
    RoutingRule,
    RoutingSpec,
    TableMatch,
    TableSpec,
    VectorSpec,
)


class KBIdentity(BaseModel):
    id: str
    backend_profile: Optional[str] = None
    description: Optional[str] = None


class KeyPolicy(BaseModel):
    primary_key: List[str] = Field(default_factory=lambda: ["knol_id", "chunk_index"])
    unique: List[List[str]] = Field(default_factory=list)
    partition_by: List[str] = Field(default_factory=list)


class IndexPolicy(BaseModel):
    btree_on: List[str] = Field(default_factory=lambda: ["knol_id", "chunk_created_at", "producer_id"])
    fulltext_on_text: bool = True
    fulltext_on_metadata: bool = True
    extra: List[IndexSpec] = Field(default_factory=list)


class NamingPolicy(BaseModel):
    default_table_template: str = "chunks_{modality}"
    specialized_table_template: str = "chunks_{modality}__{mimetype}"
    sanitize_mimetype: Optional[Callable[[str], str]] = None


class DefaultsPolicy(BaseModel):
    include_text_column: bool = True
    denormalize_meta_fields: bool = True
    meta_column: str = "metadata"
    keys: KeyPolicy = Field(default_factory=KeyPolicy)
    indexes: IndexPolicy = Field(default_factory=IndexPolicy)


class ModalitySpec(BaseModel):
    enabled: bool = True
    specialized_mimetypes: List[str] = Field(default_factory=list)
    include_text_column: Optional[bool] = None
    denormalize_meta_fields: Optional[bool] = None
    meta_column: Optional[str] = None
    keys: Optional[KeyPolicy] = None
    indexes: Optional[IndexPolicy] = None
    vectors: List[VectorSpec] = Field(default_factory=list)
    table_name: Optional[str] = None
    specialized_table_template: Optional[str] = None


class SchemaInferConfig(BaseModel):
    kb: KBIdentity
    modalities: Dict[Modality, ModalitySpec]
    naming: NamingPolicy = Field(default_factory=NamingPolicy)
    defaults: DefaultsPolicy = Field(default_factory=DefaultsPolicy)
    # Optional override to supply custom chunk classes for modalities
    chunk_class_for_modality: Dict[Modality, Type[ChunkBase]] = Field(default_factory=dict)


def infer_kb_schema(config: SchemaInferConfig) -> KBSchema:
    # Default mapping from modality to stock chunk class
    default_chunk_cls: Dict[Modality, Type[ChunkBase]] = {
        Modality.TEXT: TextChunk,
        Modality.IMAGE: ImageChunk,
        Modality.AUDIO: AudioChunk,
        Modality.VIDEO: VideoChunk,
    }

    def _sanitize_mime(m: str) -> str:
        fn = config.naming.sanitize_mimetype
        if fn is not None:
            try:
                return fn(m)
            except Exception:
                pass
        return m.replace("/", "_")

    def _table_name(mod: Modality, mimetype: Optional[str], spec: ModalitySpec) -> str:
        if mimetype:
            tmpl = spec.specialized_table_template or config.naming.specialized_table_template
            return tmpl.format(modality=mod.value, mimetype=_sanitize_mime(mimetype))
        if spec.table_name:
            return spec.table_name
        return config.naming.default_table_template.format(modality=mod.value)

    tables: List[TableSpec] = []
    routing_rules: List[RoutingRule] = []

    for mod, spec in (config.modalities or {}).items():
        if not spec.enabled:
            continue

        chunk_cls = config.chunk_class_for_modality.get(mod, default_chunk_cls[mod])

        include_text = (
            spec.include_text_column if spec.include_text_column is not None else config.defaults.include_text_column
        )
        denorm_meta = (
            spec.denormalize_meta_fields
            if spec.denormalize_meta_fields is not None
            else config.defaults.denormalize_meta_fields
        )
        meta_col = spec.meta_column or config.defaults.meta_column

        # Columns
        columns = _columns_for_modality(
            modality=mod,
            chunk_cls=chunk_cls,
            include_text=include_text,
            denormalize_meta_fields=denorm_meta,
            meta_column_name=meta_col,
        )

        # Keys & indexes
        keys = spec.keys or config.defaults.keys
        idx_policy = spec.indexes or config.defaults.indexes

        # Default table
        default_name = _table_name(mod, None, spec)
        default_indexes = _indexes_for_columns(table_name=default_name, columns=columns, policy=idx_policy)
        default_table = TableSpec(
            name=default_name,
            match=TableMatch(modality=mod.value),
            primary_key=list(keys.primary_key),
            unique=list(keys.unique),
            partition_by=list(keys.partition_by),
            columns=columns,
            vector_columns=list(spec.vectors or []),
            indexes=default_indexes,
        )
        tables.append(default_table)

        # Specialized tables & routing
        for mt in spec.specialized_mimetypes:
            tname = _table_name(mod, mt, spec)
            sp_indexes = _indexes_for_columns(table_name=tname, columns=columns, policy=idx_policy)
            sp_table = TableSpec(
                name=tname,
                match=TableMatch(modality=mod.value),
                primary_key=list(keys.primary_key),
                unique=list(keys.unique),
                partition_by=list(keys.partition_by),
                columns=list(columns),
                vector_columns=list(spec.vectors or []),
                indexes=sp_indexes,
            )
            tables.append(sp_table)
            routing_rules.append(RoutingRule(match=TableMatch(modality=mod.value, mimetype=mt), table=tname))

        # Fallback routing after specialized
        routing_rules.append(
            RoutingRule(match=TableMatch(modality=mod.value, mimetype=f"{mod.value}/*"), table=default_table.name)
        )

    # Ensure specialized rules take precedence by ordering them first
    specialized = [r for r in routing_rules if r.match.mimetype and "*" not in (r.match.mimetype or "")]
    fallbacks = [r for r in routing_rules if r.match.mimetype and r.match.mimetype.endswith("/*")]
    other = [r for r in routing_rules if not r.match.mimetype]
    ordered_rules = specialized + other + fallbacks

    schema = KBSchema(
        id=config.kb.id,
        backend_profile=config.kb.backend_profile,
        description=config.kb.description,
        routing=RoutingSpec(rules=ordered_rules),
        tables=tables,
    )
    return schema


# ---------------------- Column builders ----------------------


def _columns_for_modality(
    *,
    modality: Modality,
    chunk_cls: Type[ChunkBase],
    include_text: bool,
    denormalize_meta_fields: bool,
    meta_column_name: str,
) -> List[ColumnSpec]:
    columns: List[ColumnSpec] = []
    added: set[str] = set()

    _add_required_keys(columns, added)
    _append_knol_columns(columns, added)
    _append_chunk_columns(columns, added, chunk_cls, include_text, modality)
    _append_meta_columns(columns, added, modality, denormalize_meta_fields, meta_column_name)
    return columns


def _add_required_keys(columns: List[ColumnSpec], added: set[str]) -> None:
    _add(columns, added, _col(name="knol_id", t="string", src="knol", sel="id", nullable=False))
    _add(columns, added, _col(name="chunk_index", t="int", src="chunk", sel="index", nullable=False))


def _append_knol_columns(columns: List[ColumnSpec], added: set[str]) -> None:
    for cname, fi in Knol.model_fields.items():
        if cname in {"metaparts", "metadata_consolidated"}:
            continue
        if cname == "provenance":
            for pn, pfi in Provenance.model_fields.items():
                col_name = f"prov_{pn}"
                t = _map_type(pfi.annotation, pn)
                _add(columns, added, _col(name=col_name, t=t, src="knol", sel=f"provenance.{pn}"))
            continue
        t = _map_type(fi.annotation, cname)
        col_name = f"knol_{cname}" if cname != "id" else "knol_id"
        if col_name == "knol_id":
            continue
        _add(columns, added, _col(name=col_name, t=t, src="knol", sel=cname))


def _append_chunk_columns(
    columns: List[ColumnSpec],
    added: set[str],
    chunk_cls: Type[ChunkBase],
    include_text: bool,
    modality: Modality,
) -> None:
    def _iter_chunk_fields(cls: Type[BaseModel]) -> Iterable[Tuple[str, Any]]:
        for n, f in getattr(cls, "model_fields", {}).items():
            yield n, f

    seen_chunk_fields: set[str] = set()
    for n, f in _iter_chunk_fields(ChunkBase):
        seen_chunk_fields.add(n)
        if getattr(f, "exclude", False):
            continue
        if n == "created_at":
            _add(columns, added, _col(name="chunk_created_at", t="timestamp", src="chunk", sel=n))
            continue
        if n == "updated_at":
            _add(columns, added, _col(name="chunk_updated_at", t="timestamp", src="chunk", sel=n))
            continue
        if n == "id":
            _add(columns, added, _col(name="chunk_id", t="string", src="chunk", sel=n))
            continue
        if n == "kind":
            _add(columns, added, _col(name="chunk_kind", t="string", src="chunk", sel=n))
            continue
        t = _map_type(f.annotation, n)
        _add(columns, added, _col(name=n, t=t, src="chunk", sel=n))

    for n, f in _iter_chunk_fields(chunk_cls):
        if n in seen_chunk_fields or getattr(f, "exclude", False):
            continue
        t = _map_type(f.annotation, n)
        _add(columns, added, _col(name=n, t=t, src="chunk", sel=n))

    if include_text and modality == Modality.TEXT:
        _add(columns, added, _col(name="text", t="text", src="chunk", sel="text"))


def _append_meta_columns(
    columns: List[ColumnSpec],
    added: set[str],
    modality: Modality,
    denormalize_meta_fields: bool,
    meta_column_name: str,
) -> None:
    _add(columns, added, _col(name=meta_column_name, t="json", src="meta", sel=""))

    if not denormalize_meta_fields:
        return

    for n, f in CommonMetaPart.model_fields.items():
        if n in {"kind", "provider", "collected_at", "confidence", "priority"} or n in added:
            continue
        t = _map_type(f.annotation, n)
        _add(columns, added, _col(name=n, t=t, src="meta", sel=n))

    modality_meta_map: Dict[Modality, Type[AnyMetaPart]] = {
        Modality.TEXT: DocumentMetaPart,
        Modality.IMAGE: ImageMetaPart,
        Modality.VIDEO: VideoMetaPart,
        Modality.AUDIO: AudioMetaPart,
    }
    meta_cls = modality_meta_map.get(modality)
    if meta_cls is None:
        return
    for n, f in meta_cls.model_fields.items():
        if n in {"kind", "provider", "collected_at", "confidence", "priority"} or n in added:
            continue
        t = _map_type(f.annotation, n)
        _add(columns, added, _col(name=n, t=t, src="meta", sel=n))


def _indexes_for_columns(*, table_name: str, columns: Sequence[ColumnSpec], policy: IndexPolicy) -> List[IndexSpec]:
    col_names = {c.name for c in columns}
    idx: List[IndexSpec] = []
    # B-Tree indexes per policy
    for col in policy.btree_on:
        if col in col_names:
            idx.append(IndexSpec(name=f"{table_name}__{col}__btree", kind="btree", columns=[col]))

    # Fulltext per policy
    if policy.fulltext_on_text and "text" in col_names:
        idx.append(IndexSpec(name=f"{table_name}__text__fulltext", kind="fulltext", columns=["text"]))

    # Identify the consolidated metadata JSON column generically
    meta_json_col = next(
        (c.name for c in columns if getattr(c, "source", None) == "meta" and (getattr(c, "selector", "") or "") == ""),
        None,
    )
    if policy.fulltext_on_metadata and meta_json_col:
        idx.append(IndexSpec(name=f"{table_name}__{meta_json_col}__fulltext", kind="fulltext", columns=[meta_json_col]))

    # Extra pass-through indexes
    if policy.extra:
        idx.extend(policy.extra)

    return idx


def _col(*, name: str, t: str, src: str, sel: str, nullable: bool = True) -> ColumnSpec:
    return ColumnSpec(name=name, type=t, source=src, selector=sel, nullable=nullable)


def _add(columns: List[ColumnSpec], added: set[str], col: ColumnSpec) -> None:
    if col.name in added:
        return
    columns.append(col)
    added.add(col.name)


def _map_type(annotation: Any, field_name: str) -> str:
    # Handle Optional[...] and Union[..., None]
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Union and args:
        non_none = [a for a in args if a is not type(None)]  # noqa: E721
        if non_none:
            return _map_type(non_none[0], field_name)
        return "json"

    # Literal[...] → treat as underlying python type; fallback to string
    from typing import Literal as _Literal  # type: ignore

    if origin is _Literal:
        # Infer by the first literal value's type
        lit_args = [a for a in args if a is not None]
        if lit_args:
            return _map_pytype(type(lit_args[0]), field_name)
        return "string"

    # List/Sequence[...] → array<...>
    if origin in {list, List, Sequence} and args:
        et = _map_pytype(args[0], field_name)
        if et in {"string", "int", "float"}:
            return f"array<{et}>"
        return "json"

    # Tuple[...] → if all ints then array<int>, else json
    if origin in {tuple, Tuple} and args:
        if all((a in {int} or _is_optional_int(a)) for a in args):
            return "array<int>"
        # could refine, but default to json
        return "json"

    # Fall back to python type mapping
    return _map_pytype(annotation, field_name)


def _is_optional_int(t: Any) -> bool:
    o = get_origin(t)
    a = get_args(t)
    return o is Union and any(x is int for x in a)


def _map_pytype(tp: Any, field_name: str) -> str:
    # Special-case well-known types
    try:
        from pydantic import AnyUrl
    except Exception:  # pragma: no cover - pydantic always present
        AnyUrl = object  # type: ignore

    import datetime as _dt

    if tp in {str}:
        # Heuristic: columns named 'text' should be full-text
        return "text" if field_name == "text" else "string"
    if tp in {int}:
        return "int"
    if tp in {float}:
        return "float"
    if tp in {bool}:
        return "bool"
    if tp in {_dt.datetime}:
        return "timestamp"
    if tp.__name__ == "AnyUrl" or tp is AnyUrl:
        return "string"
    # Fallback
    return "json"
