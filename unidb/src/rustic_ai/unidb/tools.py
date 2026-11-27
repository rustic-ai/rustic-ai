"""Optional guild adapters for LLM tools; the database agent has no LLM dependency."""

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from pydantic import create_model

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    FunctionCall,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.llm_agent.tools.tools_manager_plugin import (
    ToolsHelper,
    ToolsManagerPlugin,
)

from . import models as m
from .serialization import canonical

PR_OPERATIONS = (
    "CreateLabel",
    "CreateEdgeType",
    "AddProperty",
    "CreateScalarIndex",
    "CreateVectorIndex",
    "ListLabels",
    "ListEdgeTypes",
    "GetLabelInfo",
    "GetSchema",
    "Query",
    "Execute",
    "Flush",
    "VectorSearch",
    "InsertVertices",
    "InsertEdges",
)
NAMED_OPERATIONS = ("DBQuery", "DBEvaluate", "DBExplain", "DBMutate", "DBScenario", "DBQueryPlan", "DBQueryProfile")


class ToolArguments(m.StrictModel):
    tool_call_id: str | None = None
    tool_name: str | None = None

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        schema.get("properties", {}).pop("tool_call_id", None)
        schema.get("properties", {}).pop("tool_name", None)
        return schema


for _name in PR_OPERATIONS + NAMED_OPERATIONS:
    _request = getattr(m, _name + "Request")
    _fields: dict[str, Any] = {
        name: (field.annotation, deepcopy(field))
        for name, field in _request.model_fields.items()
        if name not in m.Request.model_fields and name != "operation_id"
    }
    globals()[_name + "Arguments"] = create_model(
        _name + "Arguments", __base__=ToolArguments, __module__=__name__, **_fields
    )


class UniDBToolsManagerPlugin(ToolsManagerPlugin):
    """Attach the actual model-provider tool-call ID after argument validation."""

    def preprocess(self, agent, ctx, request, llm):
        return super().preprocess(agent, ctx, request, llm).model_copy(update={"parallel_tool_calls": False})

    def postprocess(self, agent, ctx, final_prompt, llm_response, llm):
        calls = [call for choice in llm_response.choices for call in choice.message.tool_calls or []]
        if len(calls) > 1:
            raise ValueError("UniDB showcase supports one tool invocation per reasoning turn")
        result = []
        for call in calls:
            args = ToolsHelper.parse_tool_args(self.toolset, call.function.name, json.loads(call.function.arguments))
            if not isinstance(args, ToolArguments):
                raise ValueError("UniDB tools require argument-only parameter classes")
            result.append(args.model_copy(update={"tool_call_id": call.id, "tool_name": call.function.name}))
        if calls:
            history = [
                message.model_dump(mode="json")
                for message in final_prompt.messages
                if not isinstance(message, SystemMessage)
            ]
            source = next(choice.message for choice in llm_response.choices if choice.message.tool_calls)
            history.append(AssistantMessage(content=source.content, tool_calls=calls).model_dump(mode="json"))
            ctx.update_context({"unidb_tool_history": history})
        return result


def _submit(argument_type, request_type):
    def handle(self, ctx: ProcessContext):
        data = ctx.payload.model_dump(exclude={"tool_call_id", "tool_name"})
        context = ctx.get_context()
        correlation = context.get("unidb_correlation_id") or str(
            ctx.message.thread[0] if ctx.message.thread else ctx.message.id
        )
        invocation = str(ctx.message.id)
        tool_call_id = ctx.payload.tool_call_id or invocation
        request = dict(data, request_id=invocation, correlation_id=correlation)
        if "operation_id" in request_type.model_fields:
            request["operation_id"] = "tool:" + sha256(canonical([correlation, tool_call_id]).encode()).hexdigest()
        ctx.update_context(
            {
                "unidb_correlation_id": correlation,
                "unidb_tool_call_id": tool_call_id,
                "unidb_tool_name": ctx.payload.tool_name or request_type.__name__.removesuffix("Request"),
                "unidb_tool_arguments": data,
            }
        )
        ctx.send(request_type.model_validate(request))

    handle.__name__ = "submit_" + request_type.__name__.lower()
    return processor(argument_type)(handle)


def _observe(response_type):
    def handle(self, ctx: ProcessContext):
        observation = ctx.payload.model_dump()
        context = ctx.get_context()
        if isinstance(ctx.payload, m.DBFailure) and ctx.payload.error.effect in ("unknown", "committed"):
            ctx.send(TextFormat(text="Database operation requires reconciliation. " + canonical(observation)))
            return
        call_id = context.get("unidb_tool_call_id")
        if not call_id:
            raise ValueError("Tool observation has no correlated tool-call context")
        call = ChatCompletionMessageToolCall(
            id=call_id,
            type="function",
            function=FunctionCall(
                name=context["unidb_tool_name"], arguments=canonical(context["unidb_tool_arguments"])
            ),
        )
        messages = [
            UserMessage(content=context.get("user_query", "Continue the database workflow.")),
            AssistantMessage(tool_calls=[call]),
            ToolMessage(tool_call_id=call_id, content=canonical(observation)),
        ]
        history = context.get("unidb_tool_history")
        if history:
            messages = ChatCompletionRequest.model_validate(
                {"messages": history + [messages[-1].model_dump(mode="json")]}
            ).messages
        ctx.send(ChatCompletionRequest(messages=messages, parallel_tool_calls=False))

    handle.__name__ = "observe_" + response_type.__name__.lower()
    return processor(response_type)(handle)


class UniDBToolAdapter(Agent):
    """Guild-owned tool invocation/observation bridge with correlated native tool messages."""

    for _name in PR_OPERATIONS + NAMED_OPERATIONS:
        locals()["submit_" + _name.lower()] = _submit(globals()[_name + "Arguments"], getattr(m, _name + "Request"))
        locals()["observe_" + _name.lower()] = _observe(getattr(m, _name + "Response"))
    observe_error = _observe(m.DBFailure)
