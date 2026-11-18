"""Execute the three design cases against native Uni-DB, without an LLM.

Run from the repository root:
    PYTHONPATH=unidb/src python unidb/examples/run_examples.py
The guild-owned denial exchange is reported as a separate application fixture;
its actual messaging path is covered by test_guild_flow.py.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import uni_db

from rustic_ai.unidb import models as m
from rustic_ai.unidb.runtime import RuntimeFailure, UniDBRuntime

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/design/uni-db-agent-examples"


def run_case(case, root):
    spec = json.loads((EXAMPLES / f"{case}-init.json").read_text())
    props = spec["agents"][0]["properties"]
    config = m.UniDBAgentConfig.model_validate(props)
    deployment = spec["agents"][0]["dependency_map"]["unidb"]["properties"]
    db = uni_db.Uni.builder().create(str(root / case)).config(deployment["native_config"]).build()
    runtime = UniDBRuntime(db, config.binding_id, deployment["bootstrap"], deployment["receipts"])
    runtime.configure(config)
    document = json.loads((EXAMPLES / f"{case}-messages.json").read_text())
    document["status"] = "native_5.2.1_reference_results"
    document["notes"] = [
        "Request/response projections, not complete Rustic Message envelopes.",
        "Database payloads captured from Uni-DB 5.2.1; versions and internal IDs vary between runs.",
        "The capability_denied exchange is a guild-owned application fixture, exercised by test_guild_flow.py.",
        "Runtime sender attribution scopes receipts; authentication belongs to the embedding guild.",
    ]
    try:
        for exchange in document["exchanges"]:
            if exchange["step_id"] == "reasoner-write-refused":
                exchange["evidence"] = "guild_boundary_fixture"
                continue
            envelope = exchange["request"]
            request = getattr(m, envelope["format"].split(".")[-1]).model_validate(envelope["payload"])
            metadata = runtime.metadata()
            if isinstance(request, m.DBScenarioRequest):
                metadata["view"] = {"kind": "scratch", "base_view": {"kind": "live", "snapshot_id": None}}
            try:
                result = runtime.execute(request, envelope["sender"]["id"])
                response_type = getattr(m, type(request).__name__.removesuffix("Request") + "Response")
                response = response_type(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    binding_id=runtime.binding_id,
                    result=result,
                    metadata=metadata,
                )
            except RuntimeFailure as error:
                response = m.DBFailure(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    binding_id=runtime.binding_id,
                    outcome="unknown" if error.effect == "unknown" else "failed",
                    error=m.ErrorDetail(
                        code=error.code,
                        stage=error.stage,
                        effect=error.effect,
                        message=str(error),
                        details=error.details,
                    ),
                    metadata=metadata,
                )
            exchange["response"]["format"] = "rustic_ai.unidb.models." + type(response).__name__
            exchange["response"]["payload"] = response.model_dump()
            exchange["evidence"] = "native_runtime"
        return document
    finally:
        runtime.close()


if __name__ == "__main__":
    with TemporaryDirectory(prefix="rustic-unidb-") as directory:
        for case in ("supply-network", "receivables", "supplier-scenario"):
            print(json.dumps(run_case(case, Path(directory)), indent=2))
