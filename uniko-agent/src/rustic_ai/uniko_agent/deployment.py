"""Validate deployment files before opening a persistent store.

Catalog schema is the Apache-2.0 uni-xervo 0.19.2 catalog schema. Native
Uniko/uni-db still validate storage and schema semantics during initialization.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


def validate_deployment(config: dict[str, Any], reranker: Any = None) -> None:
    documents = {}
    for field in ("catalog_path", "schema_path", "observation_rules_path"):
        value = config.get(field)
        if value is None:
            continue
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f"{field} requires an explicit readable absolute local file")
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) if field == "observation_rules_path" else json.load(stream)
        documents[field] = data
    if "catalog_path" in documents:
        catalog = documents["catalog_path"]
        schema = json.loads(Path(__file__).with_name("schemas").joinpath("model-catalog.schema.json").read_text())
        jsonschema.validate(catalog, schema)
        aliases = [entry["alias"] for entry in catalog]
        if len(set(aliases)) != len(aliases):
            raise ValueError("Catalog aliases must be unique")
        required = {"embed/default": "embed", "nlp/default": "raw"}
        enabled = (
            True if reranker is not None and reranker is not False else config.get("reranker", {}).get("enabled", True)
        )
        if reranker is not False and enabled:
            required["rerank/default"] = "rerank"
        for alias, task in required.items():
            if not any(entry["alias"] == alias and entry["task"] == task for entry in catalog):
                raise ValueError(f"Catalog requires {alias} with task {task}")
    if "schema_path" in documents:
        schema = documents["schema_path"]
        jsonschema.validate(
            schema,
            {
                "type": "object",
                "required": ["schema_version", "labels", "edge_types", "properties"],
                "properties": {
                    "schema_version": {"type": "integer", "minimum": 0},
                    "labels": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "required": ["id", "created_at"],
                            "properties": {
                                "id": {"type": "integer", "minimum": 0, "maximum": 65535},
                                "created_at": {"type": "string"},
                            },
                        },
                    },
                    "edge_types": {
                        "type": "object",
                        "additionalProperties": {"type": "object", "required": ["id", "src_labels", "dst_labels"]},
                    },
                    "properties": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": {"type": "object", "required": ["type", "nullable"]},
                        },
                    },
                },
            },
        )
        if not {"Session", "Message", "Artifact", "Chunk", "Participant"}.issubset(schema["labels"]):
            raise ValueError("Schema is missing required Uniko memory labels")
    if "observation_rules_path" in documents:
        rules = documents["observation_rules_path"]
        jsonschema.validate(
            rules,
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject_resolution": {"type": "object"},
                    "filters": {"type": "object"},
                    "phrase_collectors": {"type": "object"},
                    "patterns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "match", "template"],
                            "properties": {
                                "name": {"type": "string"},
                                "template": {"type": "string"},
                                "match": {
                                    "type": "object",
                                    "required": ["anchor"],
                                    "properties": {"anchor": {"type": "object", "required": ["pos"]}},
                                },
                            },
                        },
                    },
                    "srl_patterns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "template"],
                            "properties": {
                                "name": {"type": "string"},
                                "template": {"type": "string"},
                                "captures": {"type": "array", "items": {"type": "object", "required": ["role", "as"]}},
                            },
                        },
                    },
                },
            },
        )
