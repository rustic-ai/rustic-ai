"""Focused tests for typed Data Analyst memory events."""

from types import SimpleNamespace
from unittest.mock import Mock

from rustic_ai.pandas_analyst.memory import (
    AnalysisConversationRecorder,
    AnalysisOutcomeEmitter,
    AnalysisOutcomeRecord,
)

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    UserMessage,
)
from rustic_ai.uniko_agent import (
    FinalizeMemorySessionRequest,
    MemoryRecordKind,
    RecordMemoryRequest,
)


def _agent_and_context():
    agent = Mock(guild_id="guild-1", id="react_data_analyst")
    origin = SimpleNamespace(id="upa-user-1")
    ctx = Mock()
    ctx.get_context.return_value = {}
    ctx.message = SimpleNamespace(
        sender=origin,
        id="request-1",
        forward_header=SimpleNamespace(on_behalf_of=origin, origin_message_id="original-request-1"),
    )
    return agent, ctx


def test_successful_visible_turn_emits_typed_pair_before_finalization():
    agent, ctx = _agent_and_context()
    request = ChatCompletionRequest(messages=[UserMessage(content="Revenue is net of refunds")])
    ctx.payload = request
    response = ChatCompletionResponse(
        id="response-1",
        created=0,
        model="test",
        choices=[Choice(index=0, message=AssistantMessage(content="Understood."), finish_reason="stop")],
    )

    messages = AnalysisConversationRecorder().postprocess(agent, ctx, request, response, Mock())

    assert messages is not None
    assert [type(message) for message in messages] == [
        RecordMemoryRequest,
        RecordMemoryRequest,
        FinalizeMemorySessionRequest,
    ]
    assert messages[0].kind == MemoryRecordKind.USER_ASSERTION
    assert messages[0].content == "Revenue is net of refunds"
    assert messages[1].kind == MemoryRecordKind.ASSISTANT_RESPONSE
    assert messages[0].session_id == messages[1].session_id == messages[2].session_id


def test_internal_prompt_and_reasoning_are_not_recorded():
    agent, ctx = _agent_and_context()
    request = ChatCompletionRequest(messages=[UserMessage(content="Visible request")])
    ctx.payload = request
    response = ChatCompletionResponse(
        id="response-1",
        created=0,
        model="test",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(content="Visible answer", reasoning_content="private reasoning"),
                finish_reason="stop",
            )
        ],
    )

    messages = AnalysisConversationRecorder().postprocess(agent, ctx, request, response, Mock())

    rendered = "\n".join(message.content for message in messages if isinstance(message, RecordMemoryRequest))
    assert "Visible request" in rendered
    assert "Visible answer" in rendered
    assert "private reasoning" not in rendered


def test_verified_tool_result_is_bounded_and_stably_identified():
    agent, ctx = _agent_and_context()
    emitter = AnalysisOutcomeEmitter(max_characters=256)
    tool_input = SimpleNamespace(model_dump=lambda **_: {"name": "sales"})

    first = emitter.postprocess(agent, ctx, "summarize_dataset", tool_input, "x" * 1000)
    second = emitter.postprocess(agent, ctx, "summarize_dataset", tool_input, "x" * 1000)

    assert isinstance(first.messages[0], AnalysisOutcomeRecord)
    assert first.messages[0].record_id == second.messages[0].record_id
    assert len(first.messages[0].content) == 256


def test_failed_and_non_result_tools_do_not_emit_memory():
    agent, ctx = _agent_and_context()
    emitter = AnalysisOutcomeEmitter()
    tool_input = SimpleNamespace(model_dump=lambda **_: {})

    assert emitter.postprocess(agent, ctx, "load_file", tool_input, "loaded").messages is None
    failed = '{"_rustic_data_analyst_outcome":true,"disposition":"retryable_error"}'
    assert emitter.postprocess(agent, ctx, "query_dataset", tool_input, failed).messages is None
