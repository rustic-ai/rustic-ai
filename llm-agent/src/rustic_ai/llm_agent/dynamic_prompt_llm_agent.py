from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
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


class DynamicPromptConfig(BaseModel):
    """Configuration for the dynamic prompt."""

    default_system_prompt: str
    system_prompt_generator: Optional[PromptGenerator] = Field(None, discriminator="type")

    _system_prompt: Optional[str] = None
    _updated: bool = False

    def update_system_prompt(self, data: JsonDict):
        self._system_prompt = (
            self.system_prompt_generator.generate_prompt(data)
            if self.system_prompt_generator
            else self.default_system_prompt
        )
        self._updated = True


class DynamicPromptLLMAgentConfig(LLMAgentConfig, DynamicPromptConfig):
    """Configuration for the dynamic prompt LLM agent."""

    def get_llm_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
            exclude={"system_prompt_generator"},
        )

    def get_prefix_messages(self) -> List[
        Union[
            SystemMessage,
            UserMessage,
            AssistantMessage,
            ToolMessage,
        ]
    ]:
        return [
            SystemMessage(
                content=self._system_prompt if self._updated else self.default_system_prompt,
            )
        ]


class SystemPromptUpdatingMixin:

    config: DynamicPromptConfig

    def _is_system_prompt_update(self, msg: Message) -> bool:
        assert self.config.system_prompt_generator
        return msg.format == self.config.system_prompt_generator.update_on_message_format

    @processor(JsonDict, predicate=lambda self, msg: self._is_system_prompt_update(msg))
    def update_system_prompt(self, ctx: ProcessContext[JsonDict]):
        """
        Update the system prompt using the system prompt generator.
        """

        self.config.update_system_prompt(ctx.payload)


class DynamicPromptLLMAgent(Agent[DynamicPromptLLMAgentConfig], LLMInvocationMixin, SystemPromptUpdatingMixin):
    """
    Dynamic prompt LLM agent that uses different prompt generators for system and user messages.
    """

    pass
