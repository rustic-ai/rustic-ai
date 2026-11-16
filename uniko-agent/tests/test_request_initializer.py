"""Request identity stays exact before JSONata, including adjacent IDs."""

from copy import deepcopy

import pytest

from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.uniko_agent import MemoryRequestInitializerAgent

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def harness():
    return wrap_agent_for_testing(
        AgentSpec(
            id="initializer",
            name="Initializer",
            description="Test initializer",
            class_name=MemoryRequestInitializerAgent.get_qualified_class_name(),
            additional_topics=["memory_request_entry"],
            listen_to_default_topic=False,
        )
    )


def request(identifier, sender="upa-alice"):
    return Message(
        id_obj=GemstoneID.from_int(identifier),
        sender=AgentTag(id=sender),
        topics=["memory_request_entry"],
        format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze my source"},
                        {
                            "type": "file_url",
                            "file_url": {
                                "url": "uploads/data.csv",
                                "on_filesystem": True,
                                "id": "file-1",
                                "name": "data.csv",
                            },
                        },
                    ],
                }
            ]
        },
        session_state={"request_id": "forged", "request_user": "upa-attacker", "other": "keep"},
    )


@pytest.mark.parametrize(
    "identifier", [9713724488973030400, 9713724488973030401, (7 << 61) | (((1 << 39) - 1) << 22) | (255 << 12) | 4095]
)
def test_exact_identity_duplicate_delivery_and_payload_preservation(harness, identifier):
    agent, messages = harness
    msg = request(identifier)
    original = deepcopy(msg.payload)
    for _ in range(2):
        agent._on_message(msg.model_copy(deep=True))
    assert len(messages) == 2
    for result in messages:
        assert result.session_state == {
            "request_id": str(identifier),
            "request_user": "upa-alice",
            "other": "keep",
            "memory_session_id": result.session_state["memory_session_id"],
        }
        assert result.session_state["memory_session_id"].startswith("analysis-")
        assert result.payload == original
        assert result.format == msg.format
    assert msg.id == identifier
    assert msg.session_state["request_id"] == "forged"
    assert msg.payload == original


def test_adjacent_requests_do_not_collide(harness):
    agent, messages = harness
    for identifier in [9713724488973030400, 9713724488973030401]:
        agent._on_message(request(identifier))
    assert [m.session_state["request_id"] for m in messages] == ["9713724488973030400", "9713724488973030401"]
    assert messages[0].session_state["memory_session_id"] != messages[1].session_state["memory_session_id"]


@pytest.mark.parametrize("sender", [None, "", "upa-", "upa- ", "PRIVATE_UNTRUSTED_SENDER"])
def test_invalid_sender_produces_only_sanitized_error(harness, sender):
    agent, messages = harness
    agent._on_message(request(9713724488973030400, sender))
    assert len(messages) == 1
    assert messages[0].format.endswith(".ErrorMessage")
    assert messages[0].payload["error_type"] == "memory_request_identity_unavailable"
    assert messages[0].payload["error_message"] == "The request could not be initialized. Please send it again."
