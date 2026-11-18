"""Real native planning/profiling behavior and diagnostic protocol bounds."""

import pytest
from test_unidb_agent import request, runtime

from rustic_ai.unidb import models as m
from rustic_ai.unidb.runtime import RuntimeFailure


def diagnostic_runtime(tmp_path, query="MATCH (p:Product) WHERE p.name=$name RETURN p.name AS name"):
    rt, _, _, _ = runtime(tmp_path)
    rt.db.schema().label("Product").property("name", "string").apply()
    rt.configure(
        m.UniDBAgentConfig(
            binding_id="test",
            operation_catalog={
                "operations": [
                    {
                        "name": "lookup",
                        "kind": "query",
                        "query": query,
                        "columns": ["name"],
                        "parameters_schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name"],
                            "properties": {"name": {"type": "string"}},
                        },
                    }
                ]
            },
        )
    )
    return rt


def call(rt, cls, **args):
    return rt.execute(request(cls, operation="lookup", params={"name": "needle"}, **args), "caller")


def test_plan_profile_index_and_empty_columns(tmp_path):
    rt = diagnostic_runtime(tmp_path)
    try:
        empty = call(rt, m.DBQueryProfileRequest)
        assert empty["query"]["rows"] == []
        assert empty["query"]["columns"] == ["name"]
        assert empty["query"]["columns_source"] == "catalog"
        with rt.db.session().tx() as tx:
            for i in range(50):
                tx.execute(
                    "CREATE (:Product {ext_id:$id,name:$name})",
                    {"id": f"p:{i}", "name": "needle" if i == 12 else f"other:{i}"},
                )
            tx.commit()
        rt.db.flush()
        plan = call(rt, m.DBQueryPlanRequest)
        assert not plan["executed"] and not plan["parameter_values_applied"]
        assert not plan["planning_timeout_enforced"] and not plan["planning_memory_enforced"]
        assert plan["plan"]["index_usage"] == []
        before = call(rt, m.DBQueryProfileRequest)
        assert before["query"]["rows"] == [{"name": "needle"}]
        assert before["profile"]["query_metrics"]["rows_scanned"] == 50
        rt.db.schema().label("Product").index("name", "btree").apply()
        rt.db.flush()
        assert call(rt, m.DBQueryPlanRequest)["plan"]["index_usage"][0]["used"]
        after = call(rt, m.DBQueryProfileRequest)
        assert after["query"]["rows"] == before["query"]["rows"]
        assert after["profile"]["query_metrics"]["index_scans"] == 1
        assert after["profile"]["query_metrics"]["rows_scanned"] == 1
        assert after["profile"]["total_time_ms"] >= 0
        assert after["profile"]["peak_memory_bytes"] >= 0
    finally:
        rt.close()


@pytest.mark.parametrize("cls", [m.DBQueryPlanRequest, m.DBQueryProfileRequest])
@pytest.mark.parametrize(
    "args,code",
    [
        ({"params": {}}, "invalid_parameters"),
        ({"operation": "missing"}, "unknown_operation"),
        ({"view": {"kind": "snapshot", "id": "old"}}, "unsupported_view"),
        ({"limits": {"max_output_bytes": 100}}, "serialization_failure"),
    ],
)
def test_diagnostic_refusals(tmp_path, cls, args, code):
    rt = diagnostic_runtime(tmp_path)
    try:
        kwargs = {"operation": "lookup", "params": {"name": "needle"}} | args
        with pytest.raises(RuntimeFailure) as error:
            rt.execute(request(cls, **kwargs), "caller")
        assert error.value.code == code
        assert error.value.effect == "not_started"
    finally:
        rt.close()


@pytest.mark.parametrize("limit", ["timeout_ms", "max_query_memory_bytes", "max_rows", "max_statements"])
def test_plan_refuses_unsupported_limits(tmp_path, limit):
    rt = diagnostic_runtime(tmp_path)
    try:
        with pytest.raises(RuntimeFailure) as error:
            call(rt, m.DBQueryPlanRequest, limits={limit: 1})
        assert error.value.code == "unsupported_limit"
    finally:
        rt.close()


def test_profile_truncation_and_wrong_operation_family(tmp_path):
    rt = diagnostic_runtime(tmp_path, query="MATCH (p:Product) RETURN p.name AS name")
    try:
        with rt.db.session().tx() as tx:
            tx.execute('UNWIND [1,2,3] AS i CREATE (:Product {name:"needle"})')
            tx.commit()
        result = call(rt, m.DBQueryProfileRequest, limits={"max_rows": 1})
        assert result["query"]["returned_count"] == 1
        assert result["query"]["truncated"] and not result["query"]["complete"]
        rt.operations["lookup"].kind = "evaluate"
        with pytest.raises(RuntimeFailure) as error:
            call(rt, m.DBQueryProfileRequest)
        assert error.value.code == "invalid_request"
    finally:
        rt.close()


@pytest.mark.parametrize("cls", [m.DBQueryPlanRequest, m.DBQueryProfileRequest])
def test_syntax_error_stage(tmp_path, cls):
    rt = diagnostic_runtime(tmp_path, query="NOT CYPHER")
    try:
        with pytest.raises(RuntimeFailure) as error:
            call(rt, cls)
        assert error.value.code == "native_error"
        assert error.value.stage == ("plan" if cls is m.DBQueryPlanRequest else "profile")
    finally:
        rt.close()


def test_planning_never_executes_and_profile_refuses_writes(tmp_path):
    rt = diagnostic_runtime(tmp_path, query="CREATE (:Product {name:$name})")
    try:
        assert not call(rt, m.DBQueryPlanRequest)["executed"]
        assert not rt.db.session().query("MATCH (p:Product) RETURN p")
        with pytest.raises(RuntimeFailure):
            call(rt, m.DBQueryProfileRequest)
        assert not rt.db.session().query("MATCH (p:Product) RETURN p")
    finally:
        rt.close()


@pytest.mark.parametrize("limit", [{"timeout_ms": 1}, {"max_query_memory_bytes": 1}])
def test_profile_native_limits_are_enforced(tmp_path, limit):
    rt = diagnostic_runtime(tmp_path, query="MATCH (a:Product),(b:Product),(c:Product) RETURN a.name AS name")
    try:
        with rt.db.session().tx() as tx:
            tx.execute('UNWIND range(1,50) AS i CREATE (:Product {name:"needle"})')
            tx.commit()
        with pytest.raises(RuntimeFailure) as error:
            call(rt, m.DBQueryProfileRequest, limits=limit)
        assert error.value.code == "native_error"
        assert error.value.stage == "profile"
    finally:
        rt.close()


def test_profile_invokes_native_execution_once(tmp_path):
    rt = diagnostic_runtime(tmp_path)
    calls = []
    session = rt.db.session()

    class Builder:
        def __init__(self, builder):
            self.builder = builder

        def params(self, params):
            self.builder.params(params)
            return self

        def timeout(self, timeout):
            self.builder.timeout(timeout)
            return self

        def max_memory(self, memory):
            self.builder.max_memory(memory)
            return self

        def profile(self):
            calls.append("profile")
            return self.builder.profile()

        def fetch_all(self):
            raise AssertionError("Profiling must not execute a second query")

    class Session:
        def query_with(self, text):
            return Builder(session.query_with(text))

    req = request(m.DBQueryProfileRequest, operation="lookup", params={"name": "needle"})
    try:
        result = rt._diagnostic(Session(), req, rt.operations["lookup"], rt.limits(req))
        assert result["query"]["columns_source"] == "catalog"
        assert calls == ["profile"]
    finally:
        rt.close()
