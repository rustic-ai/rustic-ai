"""LLM capability with explicit commits to its private conversational store."""

import time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from rustic_ai.core.guild.agent import ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper

from .memories import UnikoMemoriesStore


class CommitConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=256)
    user_text: str = Field(min_length=1, max_length=16000)
    assistant_text: str = Field(min_length=1, max_length=16000)


class ConversationMemoryCommitted(BaseModel):
    request_id: str


class ConversationMemoryError(BaseModel):
    request_id: str
    error: str
    message: str


class ConversationDeadlineGuard(LLMCallWrapper):
    """Place last in the wrapper chain to guard calls after blocked recall."""

    context_key: str = "sma_deadline_ms"
    max_prompt_characters: int = Field(default=64000, ge=1)

    def preprocess(self, agent, ctx, request: ChatCompletionRequest, llm) -> ChatCompletionRequest:
        deadline = ctx.get_context().get(self.context_key)
        if not isinstance(deadline, (int, float)) or time.time() * 1000 >= deadline:
            raise RuntimeError("workflow_timed_out")
        if len(request.model_dump_json()) > self.max_prompt_characters:
            raise RuntimeError("conversation_input_limit_exceeded")
        return request

    def postprocess(self, agent, ctx, final_prompt, llm_response, llm) -> Optional[List[BaseModel]]:
        return None


class ConversationMemoryAgent(LLMAgent):
    """Use the normal LLM pipeline; persist only explicit accepted turns."""

    @processor(CommitConversationRequest)
    def commit_conversation(self, ctx: ProcessContext[CommitConversationRequest]):
        stores = [wrapper for wrapper in self.config.llm_request_wrappers if isinstance(wrapper, UnikoMemoriesStore)]
        try:
            if len(stores) != 1 or not stores[0].defer_recording:
                raise RuntimeError("conversation_store_configuration_invalid")
            _, _, original_id = stores[0]._request_identity(self, ctx)
            if original_id != ctx.payload.request_id:
                raise RuntimeError("conversation_request_identity_mismatch")
            stores[0].commit(self, ctx, ctx.payload.user_text, ctx.payload.assistant_text)
        except Exception:
            ctx.send_error(
                ConversationMemoryError(
                    request_id=ctx.payload.request_id,
                    error="conversation_memory_commit_unconfirmed",
                    message="Conversational memory save could not be confirmed.",
                )
            )
            return
        ctx.send(ConversationMemoryCommitted(request_id=ctx.payload.request_id))
