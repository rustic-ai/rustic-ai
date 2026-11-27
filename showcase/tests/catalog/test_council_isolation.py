"""Keep overlapping council opinions, reviews and answers in their own requests."""

from collections import Counter
from uuid import uuid4

from test_conversation_catalogs import ConversationLLM
from test_conversation_catalogs import conversation as conversation_fixture
from test_conversation_catalogs import outputs, send, wait_until

from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse

conversation = conversation_fixture


def test_overlapping_council_requests_keep_queries_and_collected_evidence_separate(conversation, monkeypatch):
    held = []
    markers = ("ALPHA_REQUEST", "BETA_REQUEST")
    observations = []

    def completion(self, prompt, model=None):
        text = prompt.model_dump_json()
        present = [marker for marker in markers if marker in text]
        assert len(present) == 1, "Council mixed or lost request identity: " + text
        marker = present[0]
        self.calls.append((self.role, prompt))
        observations.append((self.role, marker, prompt))
        return ChatCompletionResponse(
            id=uuid4().hex,
            model=self.model,
            created=1,
            input_messages=prompt.messages,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": marker + " evidence from " + self.role},
                    "finish_reason": "stop",
                }
            ],
        )

    from rustic_ai.core.messaging.backend.in_memory_backend import (
        InMemoryMessagingBackend,
    )

    original_store = InMemoryMessagingBackend.store_message

    def delay_one_opinion(self, namespace, topic, message):
        if (
            topic.endswith("AGGREGATE_OPINIONS")
            and message.sender.id == "council_member_3"
            and "ALPHA_REQUEST" in message.payload["choices"][0]["message"]["content"]
        ):
            held.append((self, namespace, topic, message.model_copy(deep=True)))
            return
        return original_store(self, namespace, topic, message)

    monkeypatch.setattr(ConversationLLM, "completion", completion)
    monkeypatch.setattr(InMemoryMessagingBackend, "store_message", delay_one_opinion)
    _, probe, _ = conversation(
        "llm_council.json", engine="rustic_ai.core.guild.execution.multithreaded.MultiThreadedEngine"
    )
    # Model a delayed transport delivery rather than blocking the User Proxy's
    # synchronous in-memory publication chain. All agents and routes remain real.
    send(probe, "ALPHA_REQUEST: How should Harbor allocate its budget?")
    wait_until(lambda: len(held) == 1)
    assert not any(msg.sender.id == "chairman" for msg in outputs(probe))
    send(probe, "BETA_REQUEST: How should Pier allocate its budget?")
    wait_until(lambda: len([msg for msg in outputs(probe) if msg.sender.id == "chairman"]) == 1)
    original_store(*held.pop())

    wait_until(lambda: len([msg for msg in outputs(probe) if msg.sender.id == "chairman"]) == 2)
    chairman = [msg for msg in outputs(probe) if msg.sender.id == "chairman"]
    assert {
        next(marker for marker in markers if marker in msg.payload["choices"][0]["message"]["content"])
        for msg in chairman
    } == set(markers)
    assert Counter((role, marker) for role, marker, _ in observations) == {
        (role, marker): 2 if role != "chairman" else 1
        for role in ("council_member_1", "council_member_2", "council_member_3", "chairman")
        for marker in markers
    }
    for _, marker, prompt in observations:
        assert marker in prompt.model_dump_json()
        assert next(other for other in markers if other != marker) not in prompt.model_dump_json()
    assert all(msg.process_status == "completed" for msg in chairman)
