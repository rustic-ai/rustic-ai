"""Typed Rustic database capability; guild composition owns authorization."""

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor

from . import models as m
from .runtime import RuntimeFailure, UniDBRuntime
from .serialization import bounded


def _handler(request_type, response_type):
    def handle(self, ctx: ProcessContext, unidb: UniDBRuntime):
        request = ctx.payload
        result = None
        try:
            result = unidb.execute(request, ctx.message.sender.id or ctx.message.sender.name)
            metadata = unidb.metadata()
            if isinstance(request, m.DBScenarioRequest):
                metadata["view"] = {"kind": "scratch", "base_view": {"kind": "live", "snapshot_id": None}}
            response = response_type(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                binding_id=unidb.binding_id,
                result=result,
                metadata=metadata,
            )
            try:
                bounded(response.model_dump(), unidb.limits(request)["max_output_bytes"])
            except (TypeError, ValueError) as exc:
                raise RuntimeFailure(
                    "serialization_failure", "serialize", str(exc), result.get("effect", "not_started")
                ) from exc
        except Exception as exc:
            failure = (
                exc
                if isinstance(exc, RuntimeFailure)
                else RuntimeFailure(
                    "native_error",
                    "execute",
                    str(exc),
                    result.get("effect", "not_started") if result else "not_started",
                )
            )
            ctx.send_error(
                m.DBFailure(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    binding_id=unidb.binding_id,
                    outcome="unknown" if failure.effect == "unknown" else "failed",
                    error=m.ErrorDetail(
                        code=failure.code,
                        stage=failure.stage,
                        effect=failure.effect,
                        message=str(failure),
                        details=failure.details,
                    ),
                    metadata=unidb.metadata(),
                )
            )
            return
        try:
            ctx.send(response)
        except Exception:
            # Publication may already have delivered. Do not emit a competing outcome.
            self.logger.exception("UniDB result publication failed; recover using operation status or replay")

    handle.__name__ = request_type.__name__.removesuffix("Request").lower()
    return processor(request_type, depends_on=["unidb"])(handle)


class UniDBAgent(Agent[m.UniDBAgentConfig]):
    def __init__(self):
        runtime = self._dependency_resolvers["unidb"].get_or_resolve(self.get_organization(), self.guild_id, self.id)
        try:
            runtime.configure(self.config)
        except Exception:
            runtime.close()
            raise

    dbcapabilities = _handler(m.DBCapabilitiesRequest, m.DBCapabilitiesResponse)
    dbhealth = _handler(m.DBHealthRequest, m.DBHealthResponse)
    dbquery = _handler(m.DBQueryRequest, m.DBQueryResponse)
    dbevaluate = _handler(m.DBEvaluateRequest, m.DBEvaluateResponse)
    dbexplain = _handler(m.DBExplainRequest, m.DBExplainResponse)
    dbmutate = _handler(m.DBMutateRequest, m.DBMutateResponse)
    dbscenario = _handler(m.DBScenarioRequest, m.DBScenarioResponse)
    dboperationstatus = _handler(m.DBOperationStatusRequest, m.DBOperationStatusResponse)
    dbbulkstatus = _handler(m.DBBulkStatusRequest, m.DBBulkStatusResponse)
    createlabel = _handler(m.CreateLabelRequest, m.CreateLabelResponse)
    createedgetype = _handler(m.CreateEdgeTypeRequest, m.CreateEdgeTypeResponse)
    addproperty = _handler(m.AddPropertyRequest, m.AddPropertyResponse)
    createscalarindex = _handler(m.CreateScalarIndexRequest, m.CreateScalarIndexResponse)
    createvectorindex = _handler(m.CreateVectorIndexRequest, m.CreateVectorIndexResponse)
    listlabels = _handler(m.ListLabelsRequest, m.ListLabelsResponse)
    listedgetypes = _handler(m.ListEdgeTypesRequest, m.ListEdgeTypesResponse)
    getlabelinfo = _handler(m.GetLabelInfoRequest, m.GetLabelInfoResponse)
    getschema = _handler(m.GetSchemaRequest, m.GetSchemaResponse)
    query = _handler(m.QueryRequest, m.QueryResponse)
    execute = _handler(m.ExecuteRequest, m.ExecuteResponse)
    flush = _handler(m.FlushRequest, m.FlushResponse)
    vectorsearch = _handler(m.VectorSearchRequest, m.VectorSearchResponse)
    insertvertices = _handler(m.InsertVerticesRequest, m.InsertVerticesResponse)
    insertedges = _handler(m.InsertEdgesRequest, m.InsertEdgesResponse)
