import json
from types import SimpleNamespace
from typing import ClassVar, Optional

from pydantic import ValidationError
import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionError,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.completion_controllers import (
    CompletionControllerError,
    StructuredContinuationController,
)
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor

from rustic_ai.testing.helpers import wrap_agent_for_testing

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["answered", "insufficient_evidence"]},
        "answer": {"type": "string", "maxLength": 16000},
        "supported_findings": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 500},
        },
        "evidence_gaps": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 500},
        },
    },
    "required": ["status", "answer", "supported_findings", "evidence_gaps"],
}


def response(content: str, finish_reason: FinishReason = FinishReason.stop, usage: bool = True):
    return ChatCompletionResponse(
        id="completion",
        created=1,
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30) if usage else None,
    )


def chunk(answer: str, continuation: str = "complete", status: str = "answered") -> str:
    return json.dumps(
        {
            "status": status,
            "answer": answer,
            "supported_findings": [],
            "evidence_gaps": [] if status == "answered" else ["Missing evidence."],
            "continuation": continuation,
        }
    )


def request() -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[UserMessage(content="Question")], response_format=SCHEMA)


class SequenceLLM(LLM):
    def __init__(self, responses: list[ChatCompletionResponse]):
        self.responses = list(responses)
        self.requests: list[ChatCompletionRequest] = []

    def completion(self, prompt: ChatCompletionRequest, model: Optional[str] = None) -> ChatCompletionResponse:
        self.requests.append(prompt)
        return self.responses.pop(0)

    async def async_completion(
        self, prompt: ChatCompletionRequest, model: Optional[str] = None
    ) -> ChatCompletionResponse:
        return self.completion(prompt, model)

    @property
    def model(self) -> str:
        return "test-model"

    def get_config(self) -> dict:
        return {"model": self.model}


class MutatingSequenceLLM(SequenceLLM):
    def completion(self, prompt: ChatCompletionRequest, model: Optional[str] = None) -> ChatCompletionResponse:
        response_format = prompt.response_format
        prompt.response_format = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": response_format},
        }
        return super().completion(prompt, model)


class SequenceLLMResolver(DependencyResolver[LLM]):
    last_llm: ClassVar[Optional[SequenceLLM]] = None

    def __init__(self, contents: list[str]):
        super().__init__()
        self.llm = SequenceLLM([response(content) for content in contents])
        type(self).last_llm = self.llm

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> LLM:
        return self.llm


class CapturePostprocessor(ResponsePostprocessor):
    contents: ClassVar[list[str]] = []

    def postprocess(self, agent, ctx, final_prompt, llm_response, llm):
        self.contents.append(llm_response.choices[0].message.content)
        return None


def complete(initial, followups=(), **controller_options):
    defaults = {
        "empty_fields_by_status": {
            "answered": ["supported_findings", "evidence_gaps"],
            "insufficient_evidence": ["answer"],
        },
        "non_empty_fields_by_status": {"insufficient_evidence": ["evidence_gaps"]},
    }
    controller = StructuredContinuationController(**(defaults | controller_options))
    prepared = controller.prepare_request(request())
    llm = SequenceLLM(list(followups))
    result = controller.complete(object(), object(), prepared, initial, llm)
    return json.loads(result.choices[0].message.content), result, llm, prepared


def test_single_complete_chunk_restores_original_shape():
    data, result, llm, prepared = complete(response(chunk("A complete answer.")))

    assert data == {
        "status": "answered",
        "answer": "A complete answer.",
        "supported_findings": [],
        "evidence_gaps": [],
    }
    assert llm.requests == []
    assert "continuation" in prepared.response_format["properties"]
    assert result.usage.total_tokens == 30


def test_multiple_chunks_are_combined_and_usage_is_aggregated():
    data, result, llm, _ = complete(
        response(chunk("First sentence. ", "continue")),
        [response(chunk("Second sentence."))],
    )

    assert data["answer"] == "First sentence. Second sentence."
    assert len(llm.requests) == 1
    assert "Continue the answer" in llm.requests[0].messages[-1].content
    assert result.usage.total_tokens == 60
    assert result.choices[0].message.reasoning_content is None


def test_length_and_unfinished_stop_each_trigger_continuation():
    for initial in (
        response(chunk("First sentence. ", "complete"), FinishReason.length),
        response(chunk("An unfinished thought", "complete")),
    ):
        data, _, llm, _ = complete(initial, [response(chunk("Finished sentence."))])
        assert data["answer"].endswith("Finished sentence.")
        assert len(llm.requests) == 1


def test_malformed_chunk_gets_one_bounded_repair():
    data, _, llm, _ = complete(response('{"status":'), [response(chunk("Replacement sentence."))])

    assert data["answer"] == "Replacement sentence."
    assert llm.requests[0].response_format["properties"]["answer"]["maxLength"] == 4000
    assert "Replace the rejected structured chunk" in llm.requests[0].messages[-1].content


def test_second_malformed_chunk_fails_closed():
    controller = StructuredContinuationController()
    prepared = controller.prepare_request(request())
    llm = SequenceLLM([response("still malformed")])

    with pytest.raises(CompletionControllerError, match="malformed structured content"):
        controller.complete(object(), object(), prepared, response("malformed"), llm)


def test_continuation_bounds_are_enforced():
    with pytest.raises(CompletionControllerError, match="violated the response schema"):
        complete(
            response(chunk("One. ", "continue")),
            [response(chunk("Two. ", "continue"))],
            max_continuations=1,
            max_total_calls=2,
        )


def test_last_permitted_continuation_requires_complete_in_the_schema():
    controller = StructuredContinuationController(max_continuations=2, max_total_calls=4)
    prepared = controller.prepare_request(request())

    first = controller._continuation_request(
        prepared,
        json.loads(chunk("One. ", "continue")),
        "One. ",
        1,
    )
    final = controller._continuation_request(
        prepared,
        json.loads(chunk("Two. ", "continue")),
        "One. Two. ",
        2,
    )

    assert first.response_format["properties"]["continuation"]["enum"] == ["continue", "complete"]
    assert final.response_format["properties"]["continuation"]["enum"] == ["complete"]
    assert "final permitted chunk" in final.messages[-1].content


def test_metadata_change_is_repaired_with_the_accepted_metadata_contract():
    data, _, llm, _ = complete(
        response(chunk("One. ", "continue")),
        [
            response(chunk("Rejected.", status="insufficient_evidence")),
            response(chunk("Replacement.")),
        ],
    )

    assert data["answer"] == "One. Replacement."
    assert len(llm.requests) == 2
    assert "Preserve these already accepted non-content fields exactly" in llm.requests[1].messages[-1].content


def test_invalid_insufficient_chunk_gets_one_semantic_repair():
    data, _, llm, _ = complete(
        response(chunk("Unexpected text.", "continue", "insufficient_evidence")),
        [response(chunk("", "complete", "insufficient_evidence"))],
    )

    assert data == {
        "status": "insufficient_evidence",
        "answer": "",
        "supported_findings": [],
        "evidence_gaps": ["Missing evidence."],
    }
    assert len(llm.requests) == 1


def test_answered_metadata_violation_gets_one_semantic_repair():
    invalid = json.loads(chunk("A grounded answer."))
    invalid["supported_findings"] = ["This must be empty for answered responses."]
    data, _, llm, _ = complete(
        response(json.dumps(invalid)),
        [response(chunk("A grounded replacement."))],
    )

    assert data["answer"] == "A grounded replacement."
    assert data["supported_findings"] == []
    assert len(llm.requests) == 1
    assert "when status is answered" in llm.requests[0].messages[-1].content
    repair_schema = llm.requests[0].response_format
    assert repair_schema["properties"]["status"]["enum"] == ["answered"]
    assert repair_schema["properties"]["supported_findings"]["maxItems"] == 0
    assert repair_schema["properties"]["evidence_gaps"]["maxItems"] == 0


def test_missing_insufficient_evidence_gaps_gets_one_semantic_repair():
    invalid = json.loads(chunk("", status="insufficient_evidence"))
    invalid["evidence_gaps"] = []
    data, _, llm, _ = complete(
        response(json.dumps(invalid)),
        [response(chunk("", status="insufficient_evidence"))],
    )

    assert data["status"] == "insufficient_evidence"
    assert data["evidence_gaps"] == ["Missing evidence."]
    assert len(llm.requests) == 1
    repair_schema = llm.requests[0].response_format
    assert repair_schema["properties"]["answer"]["maxLength"] == 0
    assert repair_schema["properties"]["evidence_gaps"]["minItems"] == 1
    assert repair_schema["properties"]["continuation"]["enum"] == ["complete"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(status="unsupported"),
        lambda value: value.update(evidence_gaps=["gap"] * 6),
        lambda value: value.update(evidence_gaps=["x" * 501]),
        lambda value: value.update(supported_findings="not-an-array"),
    ],
)
def test_json_schema_metadata_violations_get_one_repair(mutation):
    invalid = json.loads(chunk("A grounded answer."))
    mutation(invalid)

    data, _, llm, _ = complete(
        response(json.dumps(invalid)),
        [response(chunk("A valid replacement."))],
    )

    assert data["answer"] == "A valid replacement."
    assert len(llm.requests) == 1


def test_second_semantic_violation_fails_closed():
    with pytest.raises(CompletionControllerError, match="invalid structured response chunk"):
        complete(
            response(chunk("Unexpected text.", "continue", "insufficient_evidence")),
            [response(chunk("Still invalid.", "continue", "insufficient_evidence"))],
        )


def test_non_usable_finish_reason_and_missing_usage_are_handled():
    controller = StructuredContinuationController()
    prepared = controller.prepare_request(request())
    llm = SequenceLLM([response(chunk("Should not be called."))])
    with pytest.raises(CompletionControllerError, match="usable structured content"):
        controller.complete(
            object(), object(), prepared, response(chunk("Filtered."), FinishReason.content_filter), llm
        )
    assert llm.requests == []

    _, result, _, _ = complete(
        response(chunk("One. ", "continue"), usage=False),
        [response(chunk("Two."))],
    )
    assert result.usage is None


def test_empty_multiple_choice_tool_and_oversized_responses_fail_closed():
    controller = StructuredContinuationController(max_repairs=0)
    prepared = controller.prepare_request(request())
    empty = response(chunk("Unused."))
    empty.choices = []
    with pytest.raises(CompletionControllerError, match="exactly one response choice"):
        controller.complete(object(), object(), prepared, empty, SequenceLLM([]))

    multiple = response(chunk("One."))
    multiple.choices.append(multiple.choices[0].model_copy(update={"index": 1}))
    with pytest.raises(CompletionControllerError, match="exactly one response choice"):
        controller.complete(object(), object(), prepared, multiple, SequenceLLM([]))

    tool = response(chunk("Tool."))
    tool.choices[0].message.tool_calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "lookup", "arguments": "{}"},
        }
    ]
    with pytest.raises(CompletionControllerError, match="does not accept tool calls"):
        controller.complete(object(), object(), prepared, tool, SequenceLLM([]))

    oversized = StructuredContinuationController(chunk_max_characters=256, max_repairs=0)
    small_request = oversized.prepare_request(request())
    with pytest.raises(CompletionControllerError, match="invalid structured response chunk"):
        oversized.complete(object(), object(), small_request, response(chunk("x" * 257)), SequenceLLM([]))


def test_combined_character_limit_is_enforced():
    with pytest.raises(CompletionControllerError, match="combined structured response"):
        complete(
            response(chunk("A" * 250 + ".", "continue")),
            [response(chunk("B" * 250 + "."))],
            chunk_max_characters=300,
            combined_max_characters=400,
            max_repairs=0,
        )


def test_controller_serializes_by_fqcn_and_rejects_shared_retry():
    config = LLMAgentConfig(
        completion_controller={
            "kind": "rustic_ai.llm_agent.completion_controllers.StructuredContinuationController",
            "chunk_max_characters": 1000,
        }
    )
    dumped = config.model_dump(exclude_none=True)
    assert dumped["completion_controller"]["kind"].endswith("StructuredContinuationController")
    assert dumped["completion_controller"]["chunk_max_characters"] == 1000

    with pytest.raises(ValidationError, match="cannot be combined with max_retries"):
        LLMAgentConfig(
            max_retries=1,
            completion_controller={
                "kind": "rustic_ai.llm_agent.completion_controllers.StructuredContinuationController"
            },
        )


def test_status_rules_must_match_the_response_schema():
    with pytest.raises(CompletionControllerError, match="status values allowed"):
        StructuredContinuationController(empty_fields_by_status={"unknown": ["evidence_gaps"]}).prepare_request(
            request()
        )

    with pytest.raises(CompletionControllerError, match="fields declared"):
        StructuredContinuationController(empty_fields_by_status={"answered": ["missing_field"]}).prepare_request(
            request()
        )

    with pytest.raises(ValidationError, match="both empty and non-empty"):
        StructuredContinuationController(
            empty_fields_by_status={"answered": ["evidence_gaps"]},
            non_empty_fields_by_status={"answered": ["evidence_gaps"]},
        )


def test_helper_calls_postprocessors_once_with_only_the_combined_response():
    CapturePostprocessor.contents = []
    llm = SequenceLLM(
        [
            response(chunk("First sentence. ", "continue")),
            response(chunk("Second sentence.")),
        ]
    )
    config = LLMAgentConfig(
        completion_controller=StructuredContinuationController(),
        response_postprocessors=[CapturePostprocessor()],
    )
    prompt = request()

    result = LLMAgentHelper.call_llm_with_plugins(
        agent=SimpleNamespace(name="Synthesis Agent"),
        config=config,
        llm=llm,
        ctx=SimpleNamespace(payload=prompt),
        request=prompt,
    )

    assert len(llm.requests) == 2
    assert len(CapturePostprocessor.contents) == 1
    assert json.loads(CapturePostprocessor.contents[0])["answer"] == "First sentence. Second sentence."
    assert result.response == result.response.model_validate(result.response.model_dump())


def test_helper_isolates_controller_request_from_provider_mutation():
    llm = MutatingSequenceLLM(
        [
            response(chunk("First sentence. ", "continue")),
            response(chunk("Second sentence.")),
        ]
    )
    config = LLMAgentConfig(completion_controller=StructuredContinuationController())
    prompt = request()

    result = LLMAgentHelper.call_llm_with_plugins(
        agent=SimpleNamespace(name="Synthesis Agent"),
        config=config,
        llm=llm,
        ctx=SimpleNamespace(payload=prompt),
        request=prompt,
    )

    assert not result.is_error
    assert json.loads(result.response.choices[0].message.content)["answer"] == ("First sentence. Second sentence.")
    assert "properties" in result.final_request.response_format
    assert "continuation" in result.final_request.response_format["properties"]


def test_agent_emits_one_message_after_three_controlled_provider_calls(generator, build_message_from_payload):
    agent_spec: AgentSpec = (
        AgentBuilder(LLMAgent)
        .set_id("synthesis_agent")
        .set_name("Synthesis Agent")
        .set_description("Synthesizes a bounded structured response")
        .set_properties(
            LLMAgentConfig(
                completion_controller=StructuredContinuationController(),
            )
        )
        .build_spec()
    )
    dependency_map = {
        "llm": DependencySpec(
            class_name=get_qualified_class_name(SequenceLLMResolver),
            properties={
                "contents": [
                    chunk("First sentence. ", "continue"),
                    chunk("Second sentence. ", "continue"),
                    chunk("Third sentence."),
                ]
            },
        ),
        "filesystem": DependencySpec(
            class_name=get_qualified_class_name(FileSystemResolver),
            properties={
                "path_base": "/tmp/rustic-structured-continuation-test",
                "protocol": "file",
                "storage_options": {"auto_mkdir": True},
            },
        ),
    }
    agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

    agent._on_message(build_message_from_payload(generator, request()))

    assert len(results) == 1
    output = ChatCompletionResponse.model_validate(results[0].payload)
    assert json.loads(output.choices[0].message.content)["answer"] == (
        "First sentence. Second sentence. Third sentence."
    )
    assert SequenceLLMResolver.last_llm is not None
    assert len(SequenceLLMResolver.last_llm.requests) == 3


def test_helper_returns_a_sanitized_processing_error_after_controller_exhaustion():
    llm = SequenceLLM([response("PRIVATE malformed"), response("PRIVATE malformed again")])
    config = LLMAgentConfig(completion_controller=StructuredContinuationController())
    prompt = request()

    result = LLMAgentHelper.call_llm_with_plugins(
        agent=SimpleNamespace(name="Synthesis Agent"),
        config=config,
        llm=llm,
        ctx=SimpleNamespace(payload=prompt),
        request=prompt,
    )

    assert isinstance(result.response, ChatCompletionError)
    assert result.response.message == "The model response could not be completed reliably."
    assert "PRIVATE" not in result.response.model_dump_json()
