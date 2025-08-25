from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    LLMMessage,
    SystemMessage,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.json_utils import JsonDict
from rustic_ai.llm_agent.basic_llm_agent import LLMInvocationMixin
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig


class PromptGenerator(BaseModel):
    """Base class for prompt generators."""

    type: Literal["template"]
    update_on_message_format: str

    def generate_prompt(self, data: JsonDict) -> str:
        raise NotImplementedError("Subclasses must implement this method.")


class TemplatedPromptGenerator(PromptGenerator):
    """Prompt generator that uses a template for prompts."""

    type: Literal["template"] = "template"
    update_on_message_format: str

    template: str

    def generate_prompt(self, dict: JsonDict) -> str:
        return self.template.format(**dict)


class DynamicPromptLLMAgentConfig(LLMAgentConfig):
    """Configuration for the dynamic prompt LLM agent."""

    default_system_prompt: str
    system_prompt_generator: PromptGenerator = Field(discriminator="type")

    def get_llm_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
            exclude={"system_prompt_generator", "default_system_prompt"},
        )


class DynamicSystemPromptMixin:
    """Mixin for dynamic system prompt updates."""

    name: str
    config: DynamicPromptLLMAgentConfig

    _system_prompt: Optional[str] = None
    _updated: bool = False

    def _is_system_prompt_update(self, msg: Message) -> bool:
        if self.config and isinstance(self.config, DynamicPromptLLMAgentConfig):
            return msg.format == self.config.system_prompt_generator.update_on_message_format
        return False

    @processor(JsonDict, predicate=lambda self, msg: self._is_system_prompt_update(msg))
    def update_system_prompt(self, ctx: ProcessContext[JsonDict]):
        """
        Update the system prompt using the system prompt generator.
        """
        if not self.config or not isinstance(self.config, DynamicPromptLLMAgentConfig):
            return
        self._system_prompt = (
            self.config.system_prompt_generator.generate_prompt(ctx.payload)
            if self.config.system_prompt_generator
            else self.config.default_system_prompt
        )
        self._updated = True


class DynamicPromptLLMAgent(Agent[DynamicPromptLLMAgentConfig], LLMInvocationMixin, DynamicSystemPromptMixin):
    """
    Dynamic prompt LLM agent that uses different prompt generators for system and user messages.
    """

    def get_prefix_messages(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM) -> List[LLMMessage]:
        return [
            SystemMessage(
                content=self._system_prompt if self._updated else self.config.default_system_prompt,
            )
        ]
