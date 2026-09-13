"""Controllers that can turn one logical LLM request into bounded provider calls."""

from abc import ABC, abstractmethod
from copy import deepcopy
import json
import re
from typing import Any, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import Field, model_validator

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionUsage,
    FinishReason,
    UserMessage,
)
from rustic_ai.llm_agent.plugins.base_plugin import BasePlugin


class CompletionControllerError(ValueError):
    """A sanitized failure while constructing one logical completion."""


class RepairableCompletionControllerError(CompletionControllerError):
    """A malformed chunk that may be replaced by one bounded repair call."""


class CompletionController(BasePlugin, ABC):
    """Controls bounded follow-up calls before normal response postprocessing."""

    @abstractmethod
    def prepare_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Prepare the preprocessed request for the first provider call."""

    @abstractmethod
    def complete(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
        llm: LLM,
        model: Optional[str] = None,
    ) -> ChatCompletionResponse:
        """Return the single response exposed to wrappers and postprocessors."""


class StructuredContinuationController(CompletionController):
    """Reconstruct a bounded structured answer from sentence-aligned chunks."""

    content_field: str = "answer"
    continuation_field: str = "continuation"
    status_field: Optional[str] = "status"
    insufficient_status_values: list[str] = Field(default_factory=lambda: ["insufficient_evidence"])
    empty_fields_by_status: dict[str, list[str]] = Field(default_factory=dict)
    non_empty_fields_by_status: dict[str, list[str]] = Field(default_factory=dict)
    chunk_max_characters: int = Field(default=4000, ge=256)
    combined_max_characters: int = Field(default=16000, ge=256)
    max_continuations: int = Field(default=3, ge=0)
    max_total_calls: int = Field(default=5, ge=1)
    max_repairs: int = Field(default=1, ge=0)
    require_sentence_boundary: bool = True

    @model_validator(mode="after")
    def _validate_limits(self):
        if self.content_field == self.continuation_field:
            raise ValueError("content_field and continuation_field must differ")
        if self.chunk_max_characters > self.combined_max_characters:
            raise ValueError("chunk_max_characters cannot exceed combined_max_characters")
        if self.max_total_calls < 1 + self.max_continuations:
            raise ValueError("max_total_calls must allow the configured continuation calls")
        if (self.empty_fields_by_status or self.non_empty_fields_by_status) and not self.status_field:
            raise ValueError("status_field is required when status-dependent field rules are configured")
        for status in set(self.empty_fields_by_status) | set(self.non_empty_fields_by_status):
            empty = self.empty_fields_by_status.get(status, [])
            non_empty = self.non_empty_fields_by_status.get(status, [])
            if not status or any(not field for field in [*empty, *non_empty]):
                raise ValueError("status-dependent field rules require non-empty status and field names")
            if set(empty) & set(non_empty):
                raise ValueError("a field cannot be both empty and non-empty for the same status")
        return self

    def prepare_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        if getattr(request, "stream", False):
            raise CompletionControllerError("Structured continuation does not support streaming responses.")
        if request.tools or request.tool_choice:
            raise CompletionControllerError("Structured continuation does not support tool calls.")
        if request.n not in (None, 1):
            raise CompletionControllerError("Structured continuation requires exactly one response choice.")
        if not isinstance(request.response_format, dict):
            raise CompletionControllerError("Structured continuation requires an inline JSON response schema.")

        schema = deepcopy(request.response_format)
        properties = schema.get("properties")
        required = schema.get("required")
        if schema.get("type") != "object" or not isinstance(properties, dict) or not isinstance(required, list):
            raise CompletionControllerError("Structured continuation requires an object response schema.")
        content_schema = properties.get(self.content_field)
        if not isinstance(content_schema, dict) or content_schema.get("type") != "string":
            raise CompletionControllerError("Structured continuation requires a string content field.")
        if self.continuation_field in properties:
            raise CompletionControllerError("The continuation field is reserved by the completion controller.")

        configured_limit = content_schema.get("maxLength", self.chunk_max_characters)
        if not isinstance(configured_limit, int) or configured_limit < 1:
            raise CompletionControllerError("Structured continuation requires a positive content limit.")
        content_schema["maxLength"] = min(configured_limit, self.chunk_max_characters)
        properties[self.continuation_field] = {
            "type": "string",
            "enum": ["continue", "complete"],
        }
        schema["required"] = [*required, self.continuation_field]
        self._validate_controller_schema(schema)
        return request.model_copy(update={"response_format": schema})

    def complete(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
        llm: LLM,
        model: Optional[str] = None,
    ) -> ChatCompletionResponse:
        del agent, ctx  # The controller is intentionally stateless and emits no messages.

        original_schema = self._original_schema(request)
        responses = [response]
        accumulated = ""
        expected_metadata: Optional[dict[str, Any]] = None
        continuations = 0
        repairs = 0
        current_request = request
        current_response = response

        while True:
            try:
                data, choice = self._parse_chunk(current_response, current_request)
                self._validate_status_rules(data)
                chunk = data[self.content_field]
                metadata = {
                    key: value
                    for key, value in data.items()
                    if key not in (self.content_field, self.continuation_field)
                }
                if expected_metadata is not None and metadata != expected_metadata:
                    raise RepairableCompletionControllerError("Continuation metadata changed between response chunks.")

                if self.status_field and metadata.get(self.status_field) in self.insufficient_status_values:
                    if accumulated or chunk or data[self.continuation_field] != "complete":
                        raise RepairableCompletionControllerError(
                            "An insufficient response cannot contain continuation content."
                        )
                elif not chunk.strip():
                    raise RepairableCompletionControllerError("A structured response chunk was empty.")

                candidate = accumulated + chunk
                if len(candidate) > self.combined_max_characters:
                    raise RepairableCompletionControllerError(
                        "The combined structured response exceeded its configured limit."
                    )
            except RepairableCompletionControllerError:
                if repairs >= self.max_repairs or len(responses) >= self.max_total_calls:
                    raise
                repairs += 1
                current_request = self._repair_request(
                    request,
                    current_response,
                    accumulated,
                    expected_metadata,
                )
                current_response = llm.completion(current_request.model_copy(deep=True), model)
                responses.append(current_response)
                continue

            if expected_metadata is None:
                expected_metadata = metadata
            accumulated = candidate

            needs_continuation = (
                data[self.continuation_field] == "continue"
                or choice.finish_reason == FinishReason.length
                or (self.require_sentence_boundary and accumulated and not self._ends_at_sentence_boundary(accumulated))
            )
            if not needs_continuation:
                return self._combined_response(
                    first_response=response,
                    final_response=current_response,
                    original_schema=original_schema,
                    metadata=expected_metadata or {},
                    content=accumulated,
                    responses=responses,
                    request=request,
                )

            if continuations >= self.max_continuations or len(responses) >= self.max_total_calls:
                raise CompletionControllerError(
                    "The structured response remained incomplete after bounded continuation."
                )
            continuations += 1
            current_request = self._continuation_request(request, data, accumulated, continuations)
            current_response = llm.completion(current_request.model_copy(deep=True), model)
            responses.append(current_response)

    def _parse_chunk(self, response: ChatCompletionResponse, request: ChatCompletionRequest):
        if len(response.choices) != 1:
            raise CompletionControllerError("Structured continuation requires exactly one response choice.")
        choice = response.choices[0]
        if choice.finish_reason not in (FinishReason.stop, FinishReason.length):
            raise CompletionControllerError("The provider did not return usable structured content.")
        if choice.message.tool_calls:
            raise CompletionControllerError("Structured continuation does not accept tool calls.")
        raw = choice.message.content
        if not isinstance(raw, str):
            raise RepairableCompletionControllerError("The provider returned no structured content.")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RepairableCompletionControllerError("The provider returned malformed structured content.") from exc
        if not isinstance(data, dict):
            raise RepairableCompletionControllerError("The provider returned a non-object structured response.")

        schema = request.response_format
        if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
            raise CompletionControllerError("The continuation response schema was unavailable.")
        expected_keys = set(schema["properties"])
        if set(data) != expected_keys:
            raise RepairableCompletionControllerError("The provider returned an unexpected structured response shape.")
        chunk = data.get(self.content_field)
        continuation = data.get(self.continuation_field)
        if not isinstance(chunk, str) or len(chunk) > self._content_limit(schema):
            raise RepairableCompletionControllerError("The provider returned an invalid structured response chunk.")
        if continuation not in ("continue", "complete"):
            raise RepairableCompletionControllerError("The provider returned an invalid continuation decision.")
        try:
            Draft202012Validator(schema).validate(data)
        except ValidationError as exc:
            raise RepairableCompletionControllerError(
                "The provider returned structured content that violated the response schema."
            ) from exc
        return data, choice

    def _original_schema(self, request: ChatCompletionRequest) -> dict:
        schema = deepcopy(request.response_format)
        if not isinstance(schema, dict):
            raise CompletionControllerError("The continuation response schema was unavailable.")
        schema["properties"].pop(self.continuation_field, None)
        schema["required"] = [key for key in schema["required"] if key != self.continuation_field]
        content_schema = schema["properties"][self.content_field]
        content_schema["maxLength"] = self.combined_max_characters
        return schema

    def _repair_request(
        self,
        base_request: ChatCompletionRequest,
        response: ChatCompletionResponse,
        accumulated: str,
        expected_metadata: Optional[dict[str, Any]],
    ) -> ChatCompletionRequest:
        raw = ""
        if len(response.choices) == 1 and isinstance(response.choices[0].message.content, str):
            raw = response.choices[0].message.content[:4000]
        schema = deepcopy(base_request.response_format)
        assert isinstance(schema, dict)
        repair_limit = self.chunk_max_characters
        schema["properties"][self.content_field]["maxLength"] = repair_limit
        repair_status = self._repair_status(raw, expected_metadata)
        if repair_status is not None:
            self._specialize_status_schema(schema, repair_status)
        instruction = (
            "Replace the rejected structured chunk. Return only one JSON object matching the supplied schema. "
            f"Keep {self.content_field} at or below {repair_limit} characters and end it at a complete sentence. "
            "Set continuation to continue when more content is required, otherwise complete. "
            "Do not repeat text already accepted."
        )
        if accumulated:
            instruction += f" Continue after this accepted tail: {accumulated[-2000:]}"
        if expected_metadata is not None:
            instruction += (
                " Preserve these already accepted non-content fields exactly: "
                f"{json.dumps(expected_metadata, ensure_ascii=False)}"
            )
        status_rules = self._status_rules_instruction()
        if status_rules:
            instruction += f" Preserve these status-dependent rules: {status_rules}"
        messages = [*base_request.messages]
        if raw:
            messages.append(AssistantMessage(content=raw))
        messages.append(UserMessage(content=instruction))
        return base_request.model_copy(update={"messages": messages, "response_format": schema})

    def _continuation_request(
        self,
        base_request: ChatCompletionRequest,
        data: dict[str, Any],
        accumulated: str,
        continuation_number: int,
    ) -> ChatCompletionRequest:
        is_final_continuation = continuation_number == self.max_continuations
        instruction = (
            f"Continue the {self.content_field} exactly after the accepted text below. Return only the next JSON chunk "
            "matching the supplied schema. Do not repeat accepted text or change any other field. End the chunk at a "
            "complete sentence. "
            + (
                "This is the final permitted chunk, so finish the answer and set continuation to complete.\n\n"
                if is_final_continuation
                else "Set continuation to continue only if another chunk is still required.\n\n"
            )
            + f"Accepted text tail:\n{accumulated[-2000:]}\n\nContinuation {continuation_number} of "
            f"{self.max_continuations}."
        )
        schema = deepcopy(base_request.response_format)
        assert isinstance(schema, dict)
        if is_final_continuation:
            schema["properties"][self.continuation_field]["enum"] = ["complete"]
        return base_request.model_copy(
            update={
                "messages": [
                    *base_request.messages,
                    AssistantMessage(content=json.dumps(data, ensure_ascii=False)),
                    UserMessage(content=instruction),
                ],
                "response_format": schema,
            }
        )

    def _combined_response(
        self,
        first_response: ChatCompletionResponse,
        final_response: ChatCompletionResponse,
        original_schema: dict,
        metadata: dict[str, Any],
        content: str,
        responses: list[ChatCompletionResponse],
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        properties = original_schema["properties"]
        combined = {key: content if key == self.content_field else metadata[key] for key in properties}
        try:
            Draft202012Validator(original_schema).validate(combined)
        except ValidationError as exc:
            raise CompletionControllerError(
                "The reconstructed response violated the original response schema."
            ) from exc
        self._validate_status_rules(combined)
        final_choice = final_response.choices[0].model_copy(
            update={
                "finish_reason": FinishReason.stop,
                "message": final_response.choices[0].message.model_copy(
                    update={"content": json.dumps(combined, ensure_ascii=False), "reasoning_content": None}
                ),
            }
        )
        return first_response.model_copy(
            update={
                "choices": [final_choice],
                "usage": self._aggregate_usage(responses),
                "input_messages": request.messages,
            }
        )

    @staticmethod
    def _aggregate_usage(responses: list[ChatCompletionResponse]) -> Optional[CompletionUsage]:
        if not all(response.usage is not None for response in responses):
            return None
        return CompletionUsage(
            completion_tokens=sum(response.usage.completion_tokens for response in responses if response.usage),
            prompt_tokens=sum(response.usage.prompt_tokens for response in responses if response.usage),
            total_tokens=sum(response.usage.total_tokens for response in responses if response.usage),
        )

    def _content_limit(self, schema: dict) -> int:
        value = schema["properties"].get(self.content_field, {}).get("maxLength")
        return int(value) if isinstance(value, int) else 2**31 - 1

    def _validate_controller_schema(self, schema: dict) -> None:
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise CompletionControllerError("Structured continuation requires a valid JSON response schema.") from exc

        properties = schema["properties"]
        if self.status_field:
            status_schema = properties.get(self.status_field)
            if not isinstance(status_schema, dict):
                raise CompletionControllerError("The configured status field is missing from the response schema.")
            allowed_statuses = status_schema.get("enum")
            configured_statuses = set(self.insufficient_status_values)
            configured_statuses.update(self.empty_fields_by_status)
            configured_statuses.update(self.non_empty_fields_by_status)
            if not isinstance(allowed_statuses, list) or not configured_statuses.issubset(set(allowed_statuses)):
                raise CompletionControllerError(
                    "Status-dependent rules must reference status values allowed by the response schema."
                )

        configured_fields = {
            field
            for fields in [*self.empty_fields_by_status.values(), *self.non_empty_fields_by_status.values()]
            for field in fields
        }
        if not configured_fields.issubset(properties):
            raise CompletionControllerError(
                "Status-dependent rules must reference fields declared by the response schema."
            )
        if any(
            not isinstance(properties[field], dict) or properties[field].get("type") not in ("array", "string")
            for field in configured_fields
        ):
            raise CompletionControllerError(
                "Status-dependent rules require array or string fields in the response schema."
            )
        if self.continuation_field in configured_fields:
            raise CompletionControllerError("Status-dependent rules cannot target the continuation field.")

    def _validate_status_rules(self, data: dict[str, Any]) -> None:
        if not self.status_field:
            return
        status = data.get(self.status_field)
        for field in self.empty_fields_by_status.get(status, []):
            if not self._is_empty(data.get(field)):
                raise RepairableCompletionControllerError(
                    "The provider violated an empty-field rule for the response status."
                )
        for field in self.non_empty_fields_by_status.get(status, []):
            if self._is_empty(data.get(field)):
                raise RepairableCompletionControllerError(
                    "The provider violated a required-content rule for the response status."
                )

    def _status_rules_instruction(self) -> str:
        rules = []
        for status, fields in self.empty_fields_by_status.items():
            if fields:
                rules.append(f"when {self.status_field} is {status}, {', '.join(fields)} must be empty")
        for status, fields in self.non_empty_fields_by_status.items():
            if fields:
                rules.append(f"when {self.status_field} is {status}, {', '.join(fields)} must be non-empty")
        return "; ".join(rules)

    def _repair_status(self, raw: str, expected_metadata: Optional[dict[str, Any]]) -> Optional[str]:
        if not self.status_field:
            return None
        if expected_metadata is not None:
            status = expected_metadata.get(self.status_field)
            return status if isinstance(status, str) else None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        status = data.get(self.status_field) if isinstance(data, dict) else None
        allowed_statuses = self.empty_fields_by_status.keys() | self.non_empty_fields_by_status.keys()
        return status if isinstance(status, str) and status in allowed_statuses else None

    def _specialize_status_schema(self, schema: dict, status: str) -> None:
        assert self.status_field
        properties = schema["properties"]
        properties[self.status_field]["enum"] = [status]
        for field in self.empty_fields_by_status.get(status, []):
            field_schema = properties[field]
            if field_schema.get("type") == "array":
                field_schema["maxItems"] = 0
                field_schema.pop("minItems", None)
            elif field_schema.get("type") == "string":
                field_schema["maxLength"] = 0
                field_schema.pop("minLength", None)
        for field in self.non_empty_fields_by_status.get(status, []):
            field_schema = properties[field]
            if field_schema.get("type") == "array":
                field_schema["minItems"] = max(1, field_schema.get("minItems", 0))
            elif field_schema.get("type") == "string":
                field_schema["minLength"] = max(1, field_schema.get("minLength", 0))
        if status in self.insufficient_status_values:
            properties[self.continuation_field]["enum"] = ["complete"]

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return value is None

    @staticmethod
    def _ends_at_sentence_boundary(content: str) -> bool:
        return bool(re.search(r"[.!?](?:[\"'\)\]\}])*\s*$", content))
