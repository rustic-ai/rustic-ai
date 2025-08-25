from abc import abstractmethod
from typing import List, Union

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    LLMMessage,
    SystemMessage,
)
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_agent_utils import LLMAgentUtils


class BasicLLMAgentConfig(LLMAgentConfig):
    system_prompt: str
    """System prompt for the LLM agent."""

    _default_excludes = {"system_prompt"}

    def get_llm_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
            exclude=self._default_excludes,
        )


class LLMInvocationMixin:
    """
    Mixin class to add LLM invocation capabilities to an agent.
    """

    @abstractmethod
    def get_prefix_messages(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM) -> List[LLMMessage]:
        pass

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_no_attachments(msg),
        depends_on=["llm"],
    )
    def invoke_llm(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Invoke the LLM with the given context. All the LLM configuration parameters are passed along.
        The System prompt is set in prefix messages.
        """
        prefix_messages = self.get_prefix_messages(ctx, llm)
        LLMAgentHelper.invoke_llm_and_handle_response(
            self.name,  # type: ignore
            prefix_messages,
            self.config,  # type: ignore
            ctx.payload,
            llm,
            ctx,
        )


class BasicLLMAgent(Agent[BasicLLMAgentConfig], LLMInvocationMixin):
    """
    A simple LLM Agent that simply invokes an LLM.
    """

    def get_prefix_messages(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM) -> List[Union[LLMMessage]]:
        return [
            SystemMessage(
                content=self.config.system_prompt,
            )
        ]
