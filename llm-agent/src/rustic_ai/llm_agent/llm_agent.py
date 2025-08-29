from typing import Optional

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    SystemMessage,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.json_utils import JsonDict
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_agent_utils import LLMAgentUtils


class LLMAgent(Agent[LLMAgentConfig]):
    """
    A simple LLM Agent that simply invokes an LLM.
    """

    _system_prompt: Optional[str] = None
    _updated: bool = False

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_no_attachments(msg),
        depends_on=["llm"],
    )
    def invoke_llm(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Invoke the LLM with the given context. All the LLM configuration parameters are passed along.
        """
        prompt = ctx.payload

        if self._system_prompt:
            # If the system prompt was updated, add it to the messages.
            messages = [SystemMessage(content=self._system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})
        elif self.config.default_system_prompt:
            # If there is a default system prompt, use it.
            messages = [SystemMessage(content=self.config.default_system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})

        LLMAgentHelper.invoke_llm_and_handle_response(
            self,
            self.config,
            llm,
            ctx,
            prompt,
        )

    def _is_system_prompt_update(self, msg: Message) -> bool:
        config = self.config
        if config.system_prompt_generator and msg.format == config.system_prompt_generator.update_on_message_format:
            return True
        return False

    @processor(JsonDict, predicate=lambda self, msg: self._is_system_prompt_update(msg))
    def update_system_prompt(self, ctx: ProcessContext[JsonDict]):
        """
        Update the system prompt using the system prompt generator.
        """
        if not self.config.system_prompt_generator:
            return

        self._system_prompt = (
            self.config.system_prompt_generator.generate_prompt(ctx.payload)
            if self.config.system_prompt_generator
            else self.config.default_system_prompt
        )
        self._updated = True
