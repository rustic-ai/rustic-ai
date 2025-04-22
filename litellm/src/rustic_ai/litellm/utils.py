from typing import List, Optional

from rustic_ai.core.guild.agent_ext.depends.llm.models import FinishReason, ChatCompletionMessageToolCall, \
    ChatCompletionResponse, CompletionUsage, AssistantMessage, ToolType, FunctionCall, Choice
from litellm import Usage as LitellmUsage
from litellm.types.utils import Message as LitellmMessage
from litellm.utils import Choices as LitellmChoice, ModelResponse as LitellmModelResponse


class MessageUtils:
    @staticmethod
    def from_litellm(litellm_message: LitellmMessage) -> AssistantMessage:
        tool_calls: Optional[List[ChatCompletionMessageToolCall]] = None
        if hasattr(litellm_message, "tool_calls") and litellm_message.tool_calls:
            for tool_call in litellm_message.tool_calls:
                tool_calls = []
                if isinstance(tool_call, ChatCompletionMessageToolCall):
                    tool_calls.append(
                        ChatCompletionMessageToolCall(
                            id=tool_call.id,
                            type=ToolType.function,
                            function=FunctionCall(name=tool_call.function.name, arguments=tool_call.function.arguments),
                        )
                    )
        return AssistantMessage(
            content=litellm_message.content,
            tool_calls=tool_calls,
        )


class ChoiceUtils:
    @staticmethod
    def from_litellm(litellm_choice: LitellmChoice) -> Choice:
        return Choice(
            finish_reason=FinishReason(litellm_choice.finish_reason),
            index=litellm_choice.index,
            message=MessageUtils.from_litellm(litellm_choice.message),
        )


class ResponseUtils:
    @staticmethod
    def from_litellm(litellm_response: LitellmModelResponse) -> ChatCompletionResponse:
        cusage = None
        usage: LitellmUsage = litellm_response.get("usage")
        if usage:
            cusage = CompletionUsage(
                completion_tokens=usage.completion_tokens,
                prompt_tokens=usage.prompt_tokens,
                total_tokens=usage.total_tokens,
            )

        return ChatCompletionResponse(
            id=litellm_response.id,
            choices=[
                ChoiceUtils.from_litellm(choice) for choice in litellm_response.choices if isinstance(choice, LitellmChoice)
            ],
            created=litellm_response.created,
            model=litellm_response.model,
            system_fingerprint=litellm_response.system_fingerprint,
            usage=cusage,
        )