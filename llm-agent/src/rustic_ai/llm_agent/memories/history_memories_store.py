import json
from typing import List, Literal

from rustic_ai.core import Message
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    ChatCompletionResponse,
    LLMMessage,
    TextContentPart,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.memories.memories_store import MemoriesStore


class HistoryBasedMemoriesStore(MemoriesStore):
    memory_type: Literal["history_based"] = "history_based"
    text_only: bool = True

    def remember(self, agent: Agent, ctx: ProcessContext, message: LLMMessage) -> None:
        # No-op: History-based memory does not store messages explicitly.
        pass

    def _filter_text_messages(self, messages):
        text_messages = []
        for msg in messages:
            if isinstance(msg.content, str):
                text_messages.append(msg)
            elif isinstance(msg.content, ArrayOfContentParts):
                is_text = False
                for part in msg.content.root:
                    if isinstance(part, TextContentPart):
                        is_text = True
                    else:
                        msg.content.root.remove(part)

                    if is_text:
                        text_messages.append(msg)
        messages = text_messages
        return messages

    def _deduplicate_messages(self, messages):
        seen_content = set()
        unique_messages = []

        for msg in messages:
            # Create a stable key for possibly unhashable content (e.g., dict, complex types)
            try:
                key = msg.content if hash(msg.content) is not None else msg.content
            except TypeError:
                try:
                    key = json.dumps(
                        msg.content,
                        default=lambda o: getattr(o, "model_dump", lambda: repr(o))(),
                        sort_keys=True,
                    )
                except TypeError:
                    key = repr(msg.content)

            if key not in seen_content:
                seen_content.add(key)
                unique_messages.append(msg)
        return unique_messages

    def _extract_messages_from_history(self, enriched_history):
        messages: List[LLMMessage] = []

        for entry in enriched_history:
            message = Message.from_json(entry)
            if message.format == get_qualified_class_name(ChatCompletionRequest):
                payload = ChatCompletionRequest.model_validate(message.payload)
                messages.extend(payload.messages)
            elif message.format == get_qualified_class_name(ChatCompletionResponse):
                # Implement retrieval logic for ChatCompletionResponse messages
                payload = ChatCompletionResponse.model_validate(message.payload)
                messages.append(payload.choices[0].message)
        return messages

    def recall(self, agent: Agent, ctx: ProcessContext, context: List[LLMMessage]) -> List[LLMMessage]:
        enriched_history = ctx.get_context().get("enriched_history", [])

        messages = self._extract_messages_from_history(enriched_history)

        # Deduplicate messages by their content

        unique_messages = self._deduplicate_messages(messages)

        messages = unique_messages

        if self.text_only:
            messages = self._filter_text_messages(messages)

        return messages
