"""Bounded caller metadata shared by document workflow consumers."""

import json
from typing import Any

from rustic_ai.core.messaging.core.message import JsonDict


def compact_document_context(context: JsonDict) -> JsonDict:
    """Retain small caller metadata, omitting whole fields that exceed bounds.

    Dropping a field rather than truncating it preserves the meaning of caller
    identity and correlation values. Attachments/history stay caller-owned.
    """

    def bounded(value, budget, depth):
        if depth > 4:
            raise ValueError("Context nesting limit")
        if isinstance(value, str):
            if len(value) > min(4096, budget):
                raise ValueError("Context string limit")
            size = len(json.dumps(value, ensure_ascii=True).encode())
            if size > budget:
                raise ValueError("Context byte limit")
            return value, size
        if value is None or isinstance(value, (bool, int, float)):
            size = len(json.dumps(value).encode())
            if size > budget:
                raise ValueError("Context byte limit")
            return value, size
        if isinstance(value, (dict, list)) and len(value) <= 32:
            result: dict[str, Any] | list[Any] = {} if isinstance(value, dict) else []
            size = 2
            for key, item in (value.items() if isinstance(value, dict) else enumerate(value)):
                if isinstance(value, dict):
                    _, key_size = bounded(key, budget - size, depth + 1)
                    size += key_size + 1
                compact, item_size = bounded(item, budget - size, depth + 1)
                size += item_size + 1
                if size > budget:
                    raise ValueError("Context byte limit")
                if isinstance(result, dict):
                    if not isinstance(key, str):
                        raise ValueError("Context keys must be strings")
                    result[key] = compact
                else:
                    result.append(compact)
            return result, size
        raise ValueError("Context value limit")

    result = {}
    remaining = 16384 - 2
    for key, value in context.items():
        # Attachments and conversation bodies must never cross document branches.
        if key in {"original_attachment", "attachments", "history", "messages", "conversation_history"}:
            continue
        try:
            _, key_size = bounded(key, remaining, 0)
            compact, size = bounded(value, remaining - key_size - 2, 0)
        except ValueError:
            continue
        result[key] = compact
        remaining -= key_size + size + 2
    return result
