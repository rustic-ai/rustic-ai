"""Separately routed messages establish and conclude request-scoped memory."""

from hashlib import sha256

from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core.message import AgentTag, Message, ProcessStatus
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.uniko_agent import MemoryAgent, MemoryAgentConfig

from rustic_ai.testing.helpers import wrap_agent_for_testing

REQUEST = "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
RESPONSE = "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"
RECALL = "rustic_ai.uniko_agent.models.RecallUserSessionsRequest"


def identity(guild_id, user, request_id):
    digest = sha256(f"{guild_id}\0{user}\0{request_id}".encode()).hexdigest()
    return {"request_id": request_id, "request_user": user, "memory_session_id": f"analysis-{digest}"}


def send(agent, identifier, sender, format_, payload, context, status=None):
    message = Message(
        id_obj=GemstoneID.from_int(identifier),
        sender=AgentTag(id=sender),
        topics=["analysis_memory"],
        format=format_,
        payload=payload,
        session_state=context,
        process_status=status,
    )
    agent._on_message(message)


def test_separate_request_response_and_bounded_user_recall(uniko_dependency_spec, filesystem_dependency_spec):
    agent, sent = wrap_agent_for_testing(
        AgentSpec(
            id="analysis_memory",
            name="Memory",
            description="Memory",
            class_name=MemoryAgent.get_qualified_class_name(),
            properties=MemoryAgentConfig(
                conversation_request_producers=["initializer"],
                conversation_response_producers=["analyst"],
                auto_flush=False,
            ).model_dump(),
        ),
        dependency_map={"uniko": uniko_dependency_spec, "filesystem": filesystem_dependency_spec},
    )
    prior = identity(agent.guild_id, "upa-alice", "101")
    send(agent, 101, "initializer", REQUEST, {"messages": [{"role": "user", "content": "Revenue by region"}]}, prior)
    assert sent == []
    native = agent._dependency_resolvers["uniko"].resolve(agent.get_organization(), agent.guild_id, agent.id)
    assert native.data.message_sync("rustic-memory:conversation_turn:101") is not None

    answer = {
        "id": "r1",
        "created": 1,
        "model": "analyst",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "West is 42"}}],
    }
    send(agent, 201, "analyst", RESPONSE, answer, prior, ProcessStatus.COMPLETED)
    assert sent == []
    assert native.data.message_sync("rustic-memory:assistant_response:201").session_id == prior["memory_session_id"]
    participant = "user-" + sha256(f"{agent.guild_id}\0upa-alice".encode()).hexdigest()
    rows = native.query_sync(
        "MATCH (p:Participant {participant_id: '" + participant + "'})"
        "-[:PARTICIPATED_IN]->(s:Session) WHERE s.ended_at IS NOT NULL "
        "RETURN s.session_id AS sid ORDER BY s.ended_at DESC LIMIT 33"
    )
    assert [row["sid"] for row in rows] == [prior["memory_session_id"]]

    current = identity(agent.guild_id, "upa-alice", "102")
    send(
        agent,
        102,
        "initializer",
        RECALL,
        {
            "query": "revenue by region",
            "user_id": "upa-alice",
            "current_session_id": current["memory_session_id"],
            "allowed_record_kinds": ["conversation_turn", "assistant_response"],
        },
        current,
    )
    assert len(sent) == 1
    assert sent.pop().format.endswith(".RecallResponse")

    other = identity(agent.guild_id, "upa-bob", "103")
    send(
        agent,
        103,
        "initializer",
        RECALL,
        {
            "query": "revenue by region",
            "user_id": "upa-bob",
            "current_session_id": other["memory_session_id"],
            "allowed_record_kinds": ["conversation_turn", "assistant_response"],
        },
        other,
    )
    assert len(sent) == 1
    assert sent.pop().payload["items"] == []

    # A nonterminal or unauthorized message cannot finalize or enter memory.
    send(agent, 202, "analyst", RESPONSE, answer, current, ProcessStatus.RUNNING)
    send(agent, 203, "untrusted", RESPONSE, answer, current, ProcessStatus.COMPLETED)
    assert native.data.message_sync("rustic-memory:assistant_response:202") is None
    assert native.data.message_sync("rustic-memory:assistant_response:203") is None
