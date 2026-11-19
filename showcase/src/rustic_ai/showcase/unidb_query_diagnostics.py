"""Deterministic guild-owned index comparison; no LLM or permission policy in UniDB."""

from hashlib import sha256
from typing import Literal

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.unidb import models as m


class RunIndexComparison(m.Request):
    """Start one disposable product-index comparison."""


class ComparisonOutput(m.StrictModel):
    request_id: str
    correlation_id: str
    comparison: dict


class IndexComparisonResult(ComparisonOutput):
    outcome: Literal["succeeded"] = "succeeded"


class IndexComparisonFailed(ComparisonOutput):
    outcome: Literal["failed"] = "failed"


def _observation(response_type):
    def observe(self, ctx: ProcessContext):
        run = self._run
        if not run or run["terminal"] or ctx.payload.correlation_id != run["correlation_id"]:
            return
        if ctx.payload.request_id != run["expected"]:
            return
        if isinstance(ctx.payload, m.DBFailure):
            run["terminal"] = True
            ctx.send_error(
                IndexComparisonFailed(
                    request_id=run["request_id"],
                    correlation_id=run["correlation_id"],
                    outcome="failed",
                    comparison={"failure": ctx.payload.model_dump()},
                )
            )
            return
        stage = run["stage"]
        expected = (
            m.DBMutateResponse,
            m.FlushResponse,
            m.DBQueryPlanResponse,
            m.DBQueryProfileResponse,
            m.CreateScalarIndexResponse,
            m.FlushResponse,
            m.DBQueryPlanResponse,
            m.DBQueryProfileResponse,
        )
        if type(ctx.payload) is not expected[stage]:
            return
        if stage in (2, 3, 6, 7):
            result = ctx.payload.result
            key = "before" if stage < 4 else "after"
            if stage in (2, 6):
                run["results"].setdefault(key, {})["plan"] = {
                    "index_usage": result["plan"]["index_usage"],
                    "cost_estimates": result["plan"]["cost_estimates"],
                }
            else:
                run["results"].setdefault(key, {})["profile"] = {
                    "rows": result["query"]["rows"],
                    "total_time_ms": result["profile"]["total_time_ms"],
                    "operators": result["profile"]["operators"],
                    "query_metrics": result["profile"]["query_metrics"],
                }
        run["stage"] += 1
        self._next(ctx)

    observe.__name__ = "observe_" + response_type.__name__
    return processor(response_type)(observe)


class IndexComparisonDriver(Agent):
    """Own one bounded, sequential demo workflow and its terminal result."""

    def __init__(self):
        self._run: dict | None = None

    @processor(RunIndexComparison)
    def start(self, ctx: ProcessContext):
        if self._run is not None:
            if ctx.payload.request_id == self._run["request_id"]:
                return  # Duplicate start, including after completion.
            ctx.send_error(
                IndexComparisonFailed(
                    request_id=ctx.payload.request_id,
                    correlation_id=ctx.payload.correlation_id,
                    comparison={"error": "This disposable guild has already accepted a comparison."},
                )
            )
            return
        self._run = {
            "request_id": ctx.payload.request_id,
            "correlation_id": ctx.payload.correlation_id,
            "stage": 0,
            "expected": None,
            "terminal": False,
            "results": {},
        }
        self._next(ctx)

    def _next(self, ctx):
        run = self._run
        assert run is not None
        stage = run["stage"]
        if stage == 8:
            run["terminal"] = True
            ctx.send(
                IndexComparisonResult(
                    request_id=run["request_id"],
                    correlation_id=run["correlation_id"],
                    outcome="succeeded",
                    comparison=run["results"],
                )
            )
            return
        common = {
            "request_id": f'diagnostics:{sha256(run["request_id"].encode()).hexdigest()}:{stage}',
            "correlation_id": run["correlation_id"],
        }
        run["expected"] = common["request_id"]
        if stage == 0:
            request = m.DBMutateRequest(
                **common,
                operation_id="demo:seed",
                operation="seed_products",
                params={"products": [{"ext_id": f"product:diagnostic:{i}", "name": f"widget:{i}"} for i in range(50)]},
            )
        elif stage in (1, 5):
            request = m.FlushRequest(**common, operation_id=f"demo:flush:{stage}")
        elif stage == 4:
            request = m.CreateScalarIndexRequest(
                **common, operation_id="demo:index", label="Product", property_name="name"
            )
        else:
            cls = m.DBQueryPlanRequest if stage in (2, 6) else m.DBQueryProfileRequest
            request = cls(**common, operation="find_product", params={"name": "widget:12"})
        ctx.send(request)

    observe_mutation = _observation(m.DBMutateResponse)
    observe_flush = _observation(m.FlushResponse)
    observe_index = _observation(m.CreateScalarIndexResponse)
    observe_plan = _observation(m.DBQueryPlanResponse)
    observe_profile = _observation(m.DBQueryProfileResponse)
    observe_failure = _observation(m.DBFailure)
