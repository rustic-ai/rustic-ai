"""Durable at-most-once command dispatch, independent of native graph transactions.

A pending receipt left by cancellation/crash is uncertain, never an instruction
to retry. Native graph writes and this journal cannot commit atomically.
"""

import json
from pathlib import Path
import sqlite3
import threading

from pydantic import BaseModel


class ReceiptConflict(ValueError):
    pass


class ReceiptStore:
    def __init__(self, path: str | None = None):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS operations (actor TEXT, kind TEXT, key TEXT, fingerprint TEXT, "
            "state TEXT, response_type TEXT, response TEXT, PRIMARY KEY(actor,kind,key))"
        )
        self._db.commit()

    def get(self, actor: str, kind: str, key: str):
        with self._lock:
            row = self._db.execute(
                "SELECT fingerprint,state,response_type,response FROM operations WHERE actor=? AND kind=? AND key=?",
                (actor, kind, key),
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("fingerprint", "state", "response_type", "response"), row))

    def begin(self, actor: str, kind: str, key: str, fingerprint: str):
        with self._lock:
            prior = self.get(actor, kind, key)
            if prior is not None:
                if prior["fingerprint"] != fingerprint:
                    raise ReceiptConflict("Operation identity has a different payload")
                return prior
            self._db.execute(
                "INSERT INTO operations VALUES (?,?,?,?,?,?,?)", (actor, kind, key, fingerprint, "pending", None, None)
            )
            self._db.commit()
        return None

    def finish(self, actor: str, kind: str, key: str, response: BaseModel):
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name

        data = response.model_dump_json()
        # Responses contain bounded identities/status, never duplicate input blobs.
        if len(data.encode()) > 32 * 1024 * 1024:
            raise ValueError("Operation response exceeds journal limit")
        with self._lock:
            self._db.execute(
                "UPDATE operations SET state='completed',response_type=?,response=? WHERE actor=? AND kind=? AND key=?",
                (get_qualified_class_name(type(response)), data, actor, kind, key),
            )
            self._db.commit()

    def uncertain(self, actor: str, kind: str, key: str):
        with self._lock:
            self._db.execute(
                "UPDATE operations SET state='outcome_unknown' WHERE actor=? AND kind=? AND key=? AND state='pending'",
                (actor, kind, key),
            )
            self._db.commit()

    def close(self):
        with self._lock:
            self._db.close()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
