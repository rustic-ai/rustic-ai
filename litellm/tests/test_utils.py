from litellm.utils import ModelResponse as LitellmModelResponse
import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionResponse,
    FinishReason,
    ToolType,
)
from rustic_ai.litellm.utils import ResponseUtils


def make_basic_choice(content: str, finish_reason: str = "stop", index: int = 0):
    return {
        "index": index,
        "message": {
            "role": "assistant",
            "content": content,
        },
        "finish_reason": finish_reason,
        "logprobs": None,
    }


def test_from_litellm_simple_text_response():
    # Given a minimal OpenAI-like chat completion response
    resp_dict = {
        "id": "chatcmpl-abc123",
        "created": 1_700_000_000,
        "model": "gpt-4o-mini",
        "choices": [make_basic_choice("Hello world", finish_reason="stop")],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        },
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)

    # When we convert using our utility
    converted = ResponseUtils.from_litellm(litellm_resp)

    # Then we get our internal model populated correctly
    assert isinstance(converted, ChatCompletionResponse)
    assert converted.id == "chatcmpl-abc123"
    assert converted.model == "gpt-4o-mini"
    assert len(converted.choices) == 1
    assert converted.choices[0].message.content == "Hello world"
    assert converted.choices[0].finish_reason == FinishReason.stop
    assert converted.usage is not None
    assert converted.usage.prompt_tokens == 10
    assert converted.usage.completion_tokens == 2
    assert converted.usage.total_tokens == 12


def test_from_litellm_tool_calls_response():
    # Given a response with tool calls only (no content)
    resp_dict = {
        "id": "chatcmpl-tool-1",
        "created": 1_700_000_100,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"location":"San Francisco"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
                "logprobs": None,
            }
        ],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    assert isinstance(converted, ChatCompletionResponse)
    assert converted.choices[0].finish_reason == FinishReason.tool_calls
    msg = converted.choices[0].message
    assert msg.content is None
    assert msg.tool_calls is not None and len(msg.tool_calls) == 1
    tool_call = msg.tool_calls[0]
    assert tool_call.type == ToolType.function
    assert tool_call.function.name == "get_weather"
    assert "San Francisco" in tool_call.function.arguments


def test_from_litellm_with_reasoning_content_and_usage():
    # Given a response containing reasoning content
    resp_dict = {
        "id": "chatcmpl-reason-1",
        "created": 1_700_000_200,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Final answer.",
                    "reasoning_content": "Let's think step by step.",
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 4,
            "total_tokens": 12,
        },
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    assert converted.choices[0].message.content == "Final answer."
    assert converted.choices[0].message.reasoning_content == "Let's think step by step."
    assert converted.choices[0].finish_reason == FinishReason.stop
    assert converted.usage is not None and converted.usage.total_tokens == 12


def test_from_litellm_multiple_choices_and_length_finish_reason():
    # Given a response containing multiple choices and a length finish reason
    resp_dict = {
        "id": "chatcmpl-many-1",
        "created": 1_700_000_300,
        "model": "gpt-4o-mini",
        "choices": [
            make_basic_choice("First", finish_reason="stop", index=0),
            make_basic_choice("Second", finish_reason="length", index=1),
        ],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    assert len(converted.choices) == 2
    assert converted.choices[0].message.content == "First"
    assert converted.choices[0].finish_reason == FinishReason.stop
    assert converted.choices[1].message.content == "Second"
    assert converted.choices[1].finish_reason == FinishReason.length


def test_from_litellm_system_fingerprint_and_no_usage():
    # Given a response including system_fingerprint and no usage block
    resp_dict = {
        "id": "chatcmpl-fp-1",
        "created": 1_700_000_350,
        "model": "gpt-4o-mini",
        "system_fingerprint": "fp_abc123",
        "choices": [make_basic_choice("Hi", finish_reason="stop")],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    assert isinstance(converted, ChatCompletionResponse)
    assert converted.system_fingerprint == "fp_abc123"
    # LiteLLM's ModelResponse may include default zeroed usage even if not provided
    assert converted.usage is not None
    assert converted.usage.prompt_tokens == 0
    assert converted.usage.completion_tokens == 0
    assert converted.usage.total_tokens == 0


def test_from_litellm_multiple_tool_calls():
    # Given a response with multiple tool calls
    resp_dict = {
        "id": "chatcmpl-tool-2",
        "created": 1_700_000_360,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"location":"NYC"}',
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "get_time",
                                "arguments": '{"tz":"UTC"}',
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
                "logprobs": None,
            }
        ],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    msg = converted.choices[0].message
    assert msg.tool_calls is not None and len(msg.tool_calls) == 2
    assert msg.tool_calls[0].function.name == "get_weather"
    assert msg.tool_calls[1].function.name == "get_time"


def test_from_litellm_with_logprobs_content():
    # Given a response containing logprobs in the choice
    resp_dict = {
        "id": "chatcmpl-logprobs-1",
        "created": 1_700_000_370,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello",
                },
                "finish_reason": "stop",
                "logprobs": {
                    "content": [
                        {
                            "token": "Hello",
                            "logprob": -0.05,
                            "bytes": [72, 101, 108, 108, 111],
                            "top_logprobs": [
                                {"token": "Hello", "logprob": -0.05, "bytes": [72, 101, 108, 108, 111]},
                                {"token": "Hi", "logprob": -0.55, "bytes": [72, 105]},
                            ],
                        }
                    ]
                },
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    choice = converted.choices[0]
    assert choice.logprobs is not None
    # ensure expected keys exist in the parsed structure
    assert choice.logprobs.get("content") is not None
    first_token = choice.logprobs["content"][0]
    assert first_token.token == "Hello"
    assert isinstance(first_token.top_logprobs, list) and len(first_token.top_logprobs) >= 1


def test_from_litellm_assistant_name_provider_fields_and_thinking_blocks():
    # Given assistant name, provider_specific_fields, and thinking blocks
    resp_dict = {
        "id": "chatcmpl-think-1",
        "created": 1_700_000_380,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "name": "planner",
                    "content": "Result",
                    "provider_specific_fields": {"vendor": "openai", "latency_ms": 123},
                    "reasoning_content": "Short chain of thought.",
                    "thinking_blocks": [
                        {"type": "thinking", "thinking": "Step 1...", "signature": "sig1"},
                        {"type": "redacted_thinking", "data": "[redacted]"},
                    ],
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    msg = converted.choices[0].message
    assert msg.name == "planner"
    # provider_specific_fields is excluded by our models on dumps and is not preserved by LiteLLM round-trip
    assert msg.provider_specific_fields is None
    assert msg.reasoning_content == "Short chain of thought."
    assert msg.thinking_blocks is not None and len(msg.thinking_blocks) == 2


def test_from_litellm_empty_string_content():
    resp_dict = {
        "id": "chatcmpl-empty-1",
        "created": 1_700_000_390,
        "model": "gpt-4o-mini",
        "choices": [make_basic_choice("", finish_reason="stop")],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)
    assert converted.choices[0].message.content == ""


@pytest.mark.parametrize(
    "finish_reason",
    [
        "stop",
        "length",
        "content_filter",
        "function_call",
    ],
)
def test_from_litellm_various_finish_reasons(finish_reason: str):
    resp_dict = {
        "id": f"chatcmpl-fr-{finish_reason}",
        "created": 1_700_000_400,
        "model": "gpt-4o-mini",
        "choices": [make_basic_choice("Some text", finish_reason=finish_reason)],
    }

    litellm_resp = LitellmModelResponse.model_validate(resp_dict)
    converted = ResponseUtils.from_litellm(litellm_resp)

    assert converted.choices[0].finish_reason == finish_reason
