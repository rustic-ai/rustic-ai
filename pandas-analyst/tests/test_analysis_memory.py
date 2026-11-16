"""Focused tests for typed Data Analyst memory events."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rustic_ai.pandas_analyst.memory import (
    AnalysisOutcomeEmitter,
    AnalysisOutcomeRecord,
    analysis_memory_identity,
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


def test_analysis_identity_requires_explicit_request_session():
    agent, ctx = _agent_and_context()
    with pytest.raises(ValueError, match="analysis_memory_identity_unavailable"):
        analysis_memory_identity(agent, ctx)
    ctx.get_context.return_value = {
        "analysis_user": "upa-user-1",
        "analysis_session": "analysis-explicit",
        "analysis_request_id": "123",
    }
    session, user, request = analysis_memory_identity(agent, ctx)
    assert session == "analysis-explicit"
    assert user.startswith("user-")
    assert request == "123"


def test_verified_tool_result_is_bounded_and_stably_identified():
    agent, ctx = _agent_and_context()
    ctx.get_context.return_value = {
        "analysis_user": "upa-user-1",
        "analysis_session": "analysis-explicit",
        "analysis_request_id": "123",
    }
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
