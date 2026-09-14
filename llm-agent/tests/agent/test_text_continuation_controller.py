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
    TextContinuationController,
)
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor

from rustic_ai.testing.helpers import wrap_agent_for_testing


def response(content: str, finish_reason: FinishReason = FinishReason.stop, usage: bool = True):
    return ChatCompletionResponse(
        id="completion",
        created=1,
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(content=content, reasoning_content="private chunk reasoning"),
                finish_reason=finish_reason,
            )
        ],
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30) if usage else None,
    )


def request(content="Question") -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[UserMessage(content=content)])


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


class SequenceLLMResolver(DependencyResolver[LLM]):
    last_llm: ClassVar[Optional[SequenceLLM]] = None

    def __init__(self, chunks: list[dict]):
        super().__init__()
        self.llm = SequenceLLM([response(chunk["content"], FinishReason(chunk["finish_reason"])) for chunk in chunks])
        type(self).last_llm = self.llm

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> LLM:
        return self.llm


class CapturePostprocessor(ResponsePostprocessor):
    contents: ClassVar[list[str]] = []

    def postprocess(self, agent, ctx, final_prompt, llm_response, llm):
        self.contents.append(llm_response.choices[0].message.content)
        return None


def complete(initial, followups=(), prompt=None, **controller_options):
    controller = TextContinuationController(**controller_options)
    prepared = controller.prepare_request(prompt or request())
    llm = SequenceLLM(list(followups))
    result = controller.complete(object(), object(), prepared, initial, llm)
    return result, llm, prepared


def test_complete_response_is_returned_unchanged():
    initial = response("A complete answer.")

    result, llm, _ = complete(initial)

    assert result is initial
    assert llm.requests == []
    assert result.choices[0].message.reasoning_content == "private chunk reasoning"


def test_multiple_text_chunks_are_combined_with_aggregated_usage():
    result, llm, _ = complete(
        response("First part. ", FinishReason.length),
        [
            response("Second part. ", FinishReason.length),
            response("Third part."),
        ],
    )

    assert result.choices[0].message.content == "First part. Second part. Third part."
    assert result.choices[0].finish_reason == FinishReason.stop
    assert result.choices[0].message.reasoning_content is None
    assert result.usage == CompletionUsage(prompt_tokens=30, completion_tokens=60, total_tokens=90)
    assert result.input_messages == request().messages
    assert len(llm.requests) == 2


def test_continuation_request_preserves_the_original_request_and_accepted_text():
    prompt = ChatCompletionRequest(
        messages=[UserMessage(content="Original question")],
        temperature=0.2,
        max_tokens=64,
    )
    result, llm, _ = complete(
        response("Accepted prefix", FinishReason.length),
        [response(" and ending.")],
        prompt=prompt,
    )

    continuation = llm.requests[0]
    assert continuation.temperature == 0.2
    assert continuation.max_tokens == 64
    assert continuation.messages[:-2] == prompt.messages
    assert continuation.messages[-2] == AssistantMessage(content="Accepted prefix")
    assert "Return only new plain text" in continuation.messages[-1].content
    assert result.choices[0].message.content == "Accepted prefix and ending."


def test_exact_long_overlap_is_removed_but_short_partial_overlap_is_preserved():
    overlap = "This exact repeated passage is longer than thirty-two characters."
    result, _, _ = complete(
        response(f"Opening. {overlap}", FinishReason.length),
        [response(f"{overlap} Ending.")],
    )
    assert result.choices[0].message.content == f"Opening. {overlap} Ending."

    short_result, _, _ = complete(
        response("Ends with phrase", FinishReason.length),
        [response("phrase and continues.")],
    )
    assert short_result.choices[0].message.content == "Ends with phrasephrase and continues."


def test_final_continuation_is_identified_and_exhaustion_fails_closed():
    controller = TextContinuationController(max_continuations=1)
    prepared = controller.prepare_request(request())
    llm = SequenceLLM([response("Still unfinished", FinishReason.length)])

    with pytest.raises(CompletionControllerError, match="remained incomplete"):
        controller.complete(
            object(),
            object(),
            prepared,
            response("Initial", FinishReason.length),
            llm,
        )

    assert "final permitted continuation" in llm.requests[0].messages[-1].content


def test_empty_repeated_and_oversized_chunks_fail_closed():
    for invalid in ("", "   "):
        with pytest.raises(CompletionControllerError, match="no text content"):
            complete(response(invalid))

    repeated = "A repeated suffix."
    with pytest.raises(CompletionControllerError, match="made no progress"):
        complete(
            response(f"Initial {repeated}", FinishReason.length),
            [response(repeated)],
        )

    with pytest.raises(CompletionControllerError, match="exceeded its configured limit"):
        complete(response("x" * 257), combined_max_characters=256)


def test_invalid_choice_finish_reason_and_tool_calls_fail_closed():
    no_choices = response("Unused")
    no_choices.choices = []
    with pytest.raises(CompletionControllerError, match="exactly one response choice"):
        complete(no_choices)

    multiple = response("One")
    multiple.choices.append(multiple.choices[0].model_copy(update={"index": 1}))
    with pytest.raises(CompletionControllerError, match="exactly one response choice"):
        complete(multiple)

    filtered = response("Filtered", FinishReason.content_filter)
    with pytest.raises(CompletionControllerError, match="usable text content"):
        complete(filtered)

    tool = response("Tool")
    tool.choices[0].message.tool_calls = [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "lookup", "arguments": "{}"},
        }
    ]
    with pytest.raises(CompletionControllerError, match="does not accept tool calls"):
        complete(tool)


def test_prepare_request_rejects_non_text_modes():
    controller = TextContinuationController()

    with pytest.raises(CompletionControllerError, match="plain-text response"):
        controller.prepare_request(
            ChatCompletionRequest(
                messages=[UserMessage(content="Question")],
                response_format={"type": "object", "properties": {}},
            )
        )
    with pytest.raises(CompletionControllerError, match="exactly one response choice"):
        controller.prepare_request(ChatCompletionRequest(messages=[UserMessage(content="Question")], n=2))


def test_attachment_shaped_requests_are_supported():
    prompt = request(
        [
            {"type": "text", "text": "Describe this image"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
        ]
    )

    result, llm, _ = complete(
        response("The image shows", FinishReason.length),
        [response(" a small test fixture.")],
        prompt=prompt,
    )

    assert llm.requests[0].messages[0] == prompt.messages[0]
    assert result.choices[0].message.content == "The image shows a small test fixture."


def test_missing_usage_produces_no_misleading_aggregate():
    result, _, _ = complete(
        response("First. ", FinishReason.length, usage=False),
        [response("Second.")],
    )
    assert result.usage is None


def test_controller_serializes_by_fqcn_and_rejects_shared_retry():
    config = LLMAgentConfig(
        completion_controller={
            "kind": "rustic_ai.llm_agent.completion_controllers.TextContinuationController",
            "max_continuations": 2,
            "combined_max_characters": 8000,
        }
    )
    dumped = config.model_dump(exclude_none=True)
    assert dumped["completion_controller"]["kind"].endswith("TextContinuationController")
    assert dumped["completion_controller"]["max_continuations"] == 2

    with pytest.raises(ValidationError, match="cannot be combined with max_retries"):
        LLMAgentConfig(max_retries=1, completion_controller=TextContinuationController())


def test_helper_postprocesses_only_the_combined_response():
    CapturePostprocessor.contents = []
    llm = SequenceLLM(
        [
            response("First. ", FinishReason.length),
            response("Second."),
        ]
    )
    config = LLMAgentConfig(
        completion_controller=TextContinuationController(),
        response_postprocessors=[CapturePostprocessor()],
    )
    prompt = request()

    result = LLMAgentHelper.call_llm_with_plugins(
        agent=SimpleNamespace(name="Text Agent"),
        config=config,
        llm=llm,
        ctx=SimpleNamespace(payload=prompt),
        request=prompt,
    )

    assert not result.is_error
    assert CapturePostprocessor.contents == ["First. Second."]


def test_helper_returns_sanitized_error_without_partial_output_after_exhaustion():
    private = "PRIVATE partial output"
    llm = SequenceLLM(
        [
            response(private, FinishReason.length),
            response("PRIVATE continuation", FinishReason.length),
        ]
    )
    config = LLMAgentConfig(
        completion_controller=TextContinuationController(max_continuations=1),
    )
    prompt = request()

    result = LLMAgentHelper.call_llm_with_plugins(
        agent=SimpleNamespace(name="Text Agent"),
        config=config,
        llm=llm,
        ctx=SimpleNamespace(payload=prompt),
        request=prompt,
    )

    assert isinstance(result.response, ChatCompletionError)
    assert result.response.message == "The model response could not be completed reliably."
    assert "PRIVATE" not in result.response.model_dump_json()


def test_agent_emits_one_message_after_three_controlled_provider_calls(generator, build_message_from_payload):
    agent_spec: AgentSpec = (
        AgentBuilder(LLMAgent)
        .set_id("text-agent")
        .set_name("Text Agent")
        .set_description("Returns bounded plain-text responses")
        .set_properties(LLMAgentConfig(completion_controller=TextContinuationController()))
        .build_spec()
    )
    dependency_map = {
        "llm": DependencySpec(
            class_name=get_qualified_class_name(SequenceLLMResolver),
            properties={
                "chunks": [
                    {"content": "First. ", "finish_reason": "length"},
                    {"content": "Second. ", "finish_reason": "length"},
                    {"content": "Third.", "finish_reason": "stop"},
                ]
            },
        ),
        "filesystem": DependencySpec(
            class_name=get_qualified_class_name(FileSystemResolver),
            properties={
                "path_base": "/tmp/rustic-text-continuation-test",
                "protocol": "file",
                "storage_options": {"auto_mkdir": True},
            },
        ),
    }
    agent, results = wrap_agent_for_testing(agent_spec, dependency_map=dependency_map)

    agent._on_message(build_message_from_payload(generator, request()))

    assert len(results) == 1
    output = ChatCompletionResponse.model_validate(results[0].payload)
    assert output.choices[0].message.content == "First. Second. Third."
    assert SequenceLLMResolver.last_llm is not None
    assert len(SequenceLLMResolver.last_llm.requests) == 3
