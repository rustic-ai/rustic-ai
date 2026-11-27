"""Native v1 integration: storage, rules, transactions, recovery, and retained operations."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest
import uni_db

from rustic_ai.unidb import models as m
from rustic_ai.unidb.runtime import RuntimeFailure, UniDBRuntime
from rustic_ai.unidb.serialization import bounded, encode

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/design/uni-db-agent-examples"


def runtime(tmp_path, case=None):
    if case:
        spec = json.loads((EXAMPLES / (case + "-init.json")).read_text())
        deployment = spec["agents"][0]["dependency_map"]["unidb"]["properties"]
        props = spec["agents"][0]["properties"]
    else:
        deployment = {"bootstrap": {"policy": "apply_to_new", "revision": "test-v1"}, "receipts": {}}
        props = {"binding_id": "test", "raw_operations_enabled": True}
    path = str(tmp_path / "store")
    rt = UniDBRuntime(uni_db.Uni.create(path), props["binding_id"], deployment["bootstrap"], deployment["receipts"])
    rt.configure(m.UniDBAgentConfig.model_validate(props))
    return rt, path, deployment, props


@pytest.mark.parametrize("case", ["supply-network", "receivables", "supplier-scenario"])
def test_complete_examples(tmp_path, case):
    rt, _, _, _ = runtime(tmp_path, case)
    results = {}
    try:
        for exchange in json.loads((EXAMPLES / (case + "-messages.json")).read_text())["exchanges"]:
            if exchange["step_id"] == "reasoner-write-refused":
                continue  # Guild authorization is tested at the composition boundary.
            envelope = exchange["request"]
            request = getattr(m, envelope["format"].split(".")[-1]).model_validate(envelope["payload"])
            if exchange["response"]["format"].endswith(".DBFailure"):
                with pytest.raises(RuntimeFailure) as error:
                    rt.execute(request, envelope["sender"]["id"])
                assert error.value.code == exchange["response"]["payload"]["error"]["code"]
            else:
                results[exchange["step_id"]] = rt.execute(request, envelope["sender"]["id"])
        if case == "supply-network":
            assert results["atomic-import"]["statistics"]["nodes_created"] == 3
            assert results["query"]["returned_count"] == 2
            assert results["safe-retry"]["replayed"] is True
            assert rt.db.session().query("MATCH (:Product)-[r]-() RETURN count(r) AS n")[0]["n"] == 2
        elif case == "receivables":
            assert results["derive-balance"]["commands"][0]["rows"][0]["balance_cents"] == 15000
            proof = results["explain-balance"]["proof"]["value"]["tree"]
            assert proof["children"][0]["bindings"]["balance_cents"] == 15000
        else:
            assert results["simulate"]["before"][0]["rows"][0]["availability"] == pytest.approx(0.87)
            assert results["simulate"]["after"][0]["rows"][0]["availability"] == pytest.approx(0.987)
            assert results["simulate"]["persisted"] is False
            assert results["fresh-verification"]["commands"][0]["rows"][0]["availability"] == pytest.approx(0.987)
    finally:
        rt.close()


def request(cls, **args):
    return cls(request_id="request:" + cls.__name__, correlation_id="test-workflow", **args)


def test_retained_admin_raw_bulk_vector_operations(tmp_path):
    rt, _, _, _ = runtime(tmp_path)

    def call(cls, **args):
        if "operation_id" in cls.model_fields:
            args.setdefault("operation_id", "op:" + cls.__name__ + ":" + str(args))
        return rt.execute(request(cls, **args), "host")

    try:
        call(m.CreateLabelRequest, label="Person")
        call(m.AddPropertyRequest, label="Person", property_name="name", property_type="string")
        call(m.AddPropertyRequest, label="Person", property_name="age", property_type="int64")
        call(m.CreateScalarIndexRequest, label="Person", property_name="name")
        call(m.CreateEdgeTypeRequest, edge_type="KNOWS", source_labels=["Person"], target_labels=["Person"])
        assert "Person" in call(m.ListLabelsRequest)["labels"]
        assert call(m.ListEdgeTypesRequest)["edge_types"] == ["KNOWS"]
        assert call(m.GetLabelInfoRequest, label="Person")["properties"]
        assert call(m.GetSchemaRequest)
        inserted = call(
            m.InsertVerticesRequest,
            label="Person",
            vertices=[
                {"ext_id": "person:a", "name": "Alice", "age": 30},
                {"ext_id": "person:b", "name": "Bob", "age": 25},
            ],
        )
        assert inserted["applied"] is True and inserted["vertices_inserted"] == 2
        edge = call(
            m.InsertEdgesRequest, edge_type="KNOWS", edges=[{"source_ext_id": "person:a", "target_ext_id": "person:b"}]
        )
        assert edge["applied"] and edge["edges_inserted"] == 1
        assert call(m.DBBulkStatusRequest, load_id=inserted["load_id"])["applied"]
        result = call(
            m.ExecuteRequest, query="MATCH (p:Person {ext_id:$id}) SET p.age=$age", params={"id": "person:a", "age": 31}
        )
        assert result["statistics"]["properties_set"] == 1
        rows = call(
            m.QueryRequest, query="MATCH (p:Person {ext_id:$id}) RETURN p.age AS age", params={"id": "person:a"}
        )
        assert rows["rows"] == [{"age": 31}]
        call(m.CreateLabelRequest, label="Document")
        call(
            m.AddPropertyRequest,
            label="Document",
            property_name="embedding",
            property_type="float64",
            vector_dimension=3,
        )
        call(
            m.InsertVerticesRequest, label="Document", vertices=[{"ext_id": "document:a", "embedding": [1.0, 0.0, 0.0]}]
        )
        call(m.CreateVectorIndexRequest, label="Document", property_name="embedding")
        assert (
            call(m.VectorSearchRequest, label="Document", property_name="embedding", vector=[1.0, 0.0, 0.0], k=1)[
                "returned_count"
            ]
            == 1
        )
        call(m.FlushRequest)
        assert call(m.DBHealthRequest)["database_ready"]
        assert call(m.DBCapabilitiesRequest)["native_version"] == "6.0.0"
    finally:
        rt.close()


def test_replay_after_reopen_and_failed_batch_rollback(tmp_path):
    rt, path, deployment, props = runtime(tmp_path, "supply-network")
    fixture = json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"][0]["request"]
    original = m.DBMutateRequest.model_validate(fixture["payload"])
    try:
        rt.execute(original, "demo-ingester")
        bad = original.model_copy(update={"operation_id": "bad-import", "params": deepcopy(original.params)})
        bad.params["product"]["ext_id"] = "product:rollback"
        with pytest.raises(RuntimeFailure) as error:
            rt.execute(bad, "demo-ingester")
        assert error.value.effect == "rolled_back"
        assert not rt.db.session().query("MATCH (p:Product {ext_id:'product:rollback'}) RETURN p")
    finally:
        rt.close()
    bootstrap = dict(deployment["bootstrap"], policy="verify_existing")
    rt = UniDBRuntime(uni_db.Uni.open_existing(path), props["binding_id"], bootstrap, deployment["receipts"])
    rt.configure(m.UniDBAgentConfig.model_validate(props))
    try:
        assert rt.execute(original.model_copy(update={"request_id": "reopened"}), "demo-ingester")["replayed"]
    finally:
        rt.close()


def test_limits_serialization_and_safe_explain_binding(tmp_path):
    rt, _, _, _ = runtime(tmp_path, "receivables")
    try:
        with pytest.raises(RuntimeFailure):
            rt.execute(request(m.DBHealthRequest, limits={"max_rows": 101}), "host")
        with pytest.raises(RuntimeFailure):
            rt.execute(
                request(
                    m.DBExplainRequest, operation="explain_invoice_balance", params={"invoice_id": 'x" OR true //'}
                ),
                "host",
            )
        assert rt.db.label_exists("Invoice")
        assert encode(2**63 - 1)["value"] == str(2**63 - 1)
        assert encode(b"abc")["value"] == "YWJj"
        with pytest.raises(TypeError):
            encode(object())
        with pytest.raises(ValueError):
            bounded("too large", 3)
    finally:
        rt.close()


def test_read_surfaces_do_not_materialize_cypher_or_locy(tmp_path):
    rt, _, _, _ = runtime(tmp_path)
    try:
        rt.execute(request(m.CreateLabelRequest, label="Thing", operation_id="thing"), "host")
        with pytest.raises(uni_db.UniError):
            rt.execute(request(m.QueryRequest, query='CREATE (:Thing {ext_id:"cypher:write"})'), "host")
        config = m.UniDBAgentConfig(
            binding_id="test",
            operation_catalog={
                "operations": [
                    {
                        "name": "non_materializing",
                        "kind": "evaluate",
                        "parameters_schema": {"type": "object", "additionalProperties": False},
                        "program": 'CREATE (:Thing {ext_id:"locy:write"})',
                    }
                ]
            },
        )
        rt.configure(config)
        assert rt.execute(request(m.DBEvaluateRequest, operation="non_materializing"), "host")["materialized"] is False
        assert rt.db.session().query("MATCH (n:Thing) RETURN count(n) AS n")[0]["n"] == 0
    finally:
        rt.close()


def test_receivables_no_payment_and_multiple_payments(tmp_path):
    rt, _, _, _ = runtime(tmp_path, "receivables")
    try:
        with rt.db.session().tx() as tx:
            tx.execute(
                'CREATE (:Invoice {ext_id:"invoice:empty", amount_cents:9000}), '
                '(:Invoice {ext_id:"invoice:many", amount_cents:25000}), '
                '(:Payment {ext_id:"payment:a", amount_cents:10000}), '
                '(:Payment {ext_id:"payment:b", amount_cents:5000})'
            )
            tx.execute('MATCH (i:Invoice {ext_id:"invoice:many"}), (p:Payment) CREATE (p)-[:APPLIES_TO]->(i)')
            tx.commit()
        for invoice, balance in [("invoice:empty", 9000), ("invoice:many", 10000)]:
            result = rt.execute(
                request(m.DBEvaluateRequest, operation="invoice_balance", params={"invoice_id": invoice}), "host"
            )
            assert result["commands"][0]["rows"][0]["balance_cents"] == balance
    finally:
        rt.close()


def test_invalid_catalog_is_rejected_before_runtime_construction():
    invalid: dict[str, Any] = {
        "name": "q",
        "kind": "query",
        "query": "RETURN 1",
        "parameters_schema": {"type": "object"},
    }
    with pytest.raises(ValueError, match="closed objects"):
        m.UniDBAgentConfig(binding_id="x", operation_catalog={"operations": [invalid]})
    invalid["parameters_schema"]["additionalProperties"] = False
    with pytest.raises(ValueError, match="Duplicate"):
        m.UniDBAgentConfig(binding_id="x", operation_catalog={"operations": [invalid, invalid]})


def test_output_limit_rolls_back_before_commit(tmp_path):
    rt, _, _, _ = runtime(tmp_path, "supply-network")
    req = m.DBMutateRequest.model_validate(
        json.loads((EXAMPLES / "supply-network-messages.json").read_text())["exchanges"][0]["request"]["payload"]
    )
    try:
        with pytest.raises(RuntimeFailure) as error:
            rt.execute(req.model_copy(update={"limits": {"max_output_bytes": 100}}), "host")
        assert error.value.effect == "rolled_back"
        assert not rt.db.session().query("MATCH (p:Product) RETURN p")
        assert (
            rt.execute(req.model_copy(update={"request_id": "retry-after-rollback"}), "host")["effect"] == "committed"
        )
    finally:
        rt.close()
