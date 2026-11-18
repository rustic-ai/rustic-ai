"""Injected failures exercise real native effects and durable operation state."""

import json

import pytest
from test_unidb_agent import EXAMPLES, request, runtime
import uni_db

from rustic_ai.unidb import models as m
from rustic_ai.unidb.runtime import RuntimeFailure


class CommitFault:
    def __init__(self, tx, after):
        self.tx, self.after = tx, after

    def __getattr__(self, key):
        return getattr(self.tx, key)

    def __enter__(self):
        self.tx.__enter__()
        return self

    def __exit__(self, *args):
        return self.tx.__exit__(*args)

    def commit(self):
        if self.after:
            self.tx.commit()
        raise uni_db.UniInternalError("injected commit reporting failure")


class BuilderFault:
    def __init__(self, builder, after):
        self.builder, self.after = builder, after

    def timeout(self, value):
        self.builder.timeout(value)
        return self

    def start(self):
        return CommitFault(self.builder.start(), self.after)


class SessionFault:
    def __init__(self, session, after):
        self.session, self.after = session, after

    def __getattr__(self, key):
        return getattr(self.session, key)

    def tx_with(self):
        return BuilderFault(self.session.tx_with(), self.after)


class DatabaseFault:
    def __init__(self, db, after):
        self.db, self.after = db, after

    def __getattr__(self, key):
        return getattr(self.db, key)

    def session(self):
        return SessionFault(self.db.session(), self.after)


@pytest.mark.parametrize("after_commit", [True, False])
def test_commit_reporting_failure_never_blindly_reexecutes(tmp_path, after_commit):
    rt, _, _, _ = runtime(tmp_path, "supply-network")
    original = json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"][0]["request"]["payload"]
    req = m.DBMutateRequest.model_validate(original)
    rt.db = DatabaseFault(rt.db, after_commit)
    try:
        if after_commit:
            assert rt.execute(req, "caller")["replayed"]
            assert rt.execute(req.model_copy(update={"request_id": "retry"}), "caller")["replayed"]
        else:
            for _ in range(2):
                with pytest.raises(RuntimeFailure) as error:
                    rt.execute(req, "caller")
                assert error.value.code == "operation_outcome_unknown"
            status = rt.execute(request(m.DBOperationStatusRequest, operation_id=req.operation_id), "caller")
            assert status["state"] == "unknown"
        count = rt.db.session().query("MATCH (p:Product) RETURN count(p) AS n")[0]["n"]
        assert count == (1 if after_commit else 0)
    finally:
        rt.close()


@pytest.mark.parametrize("error_type", [uni_db.UniBulkCommitIncompleteError, uni_db.UniBulkCommitOutcomeUnknownError])
def test_bulk_post_commit_failure_is_not_rollback_or_retry(tmp_path, monkeypatch, error_type):
    rt, _, _, _ = runtime(tmp_path)
    rt.execute(request(m.CreateLabelRequest, label="Person", operation_id="label"), "caller")
    original = rt._bulk

    def interrupted(*args):
        result = original(*args)
        error = error_type("injected after native bulk commit")
        error.load_id = result["load_id"]
        raise error

    monkeypatch.setattr(rt, "_bulk", interrupted)
    req = request(m.InsertVerticesRequest, label="Person", vertices=[{"ext_id": "person:a"}], operation_id="load")
    try:
        for _ in range(2):
            with pytest.raises(RuntimeFailure) as error:
                rt.execute(req, "caller")
            assert error.value.effect == "committed"
            assert error.value.details["applied"] is True
        assert rt.db.session().query("MATCH (p:Person) RETURN count(p) AS n")[0]["n"] == 1
    finally:
        rt.close()


def test_interrupted_administration_requires_reconciliation(tmp_path, monkeypatch):
    rt, _, _, _ = runtime(tmp_path)
    original = rt._admin
    count = [0]

    def interrupted(req):
        count[0] += 1
        original(req)
        raise RuntimeError("after DDL before result bookkeeping")

    monkeypatch.setattr(rt, "_admin", interrupted)
    req = request(m.CreateLabelRequest, label="Person", operation_id="label")
    try:
        for _ in range(2):
            with pytest.raises(RuntimeFailure) as error:
                rt.execute(req, "caller")
            assert error.value.effect == "unknown"
        assert count == [1] and rt.db.label_exists("Person")
    finally:
        rt.close()


def test_scratch_is_discarded_and_commit_refused(tmp_path):
    rt, _, _, _ = runtime(tmp_path, "supplier-scenario")
    exchanges = json.loads((EXAMPLES / "supplier-scenario-messages.json").read_text())["exchanges"]
    try:
        for ex in exchanges[:3]:
            req = getattr(m, ex["request"]["format"].split(".")[-1]).model_validate(ex["request"]["payload"])
            rt.execute(req, "caller")
        assert rt.db.session().query("MATCH ()-[r:SUPPLIES]->() RETURN count(r) AS n")[0]["n"] == 1
        with rt.db.session().scratch() as tx:
            with pytest.raises(uni_db.UniError):
                tx.commit()
    finally:
        rt.close()
