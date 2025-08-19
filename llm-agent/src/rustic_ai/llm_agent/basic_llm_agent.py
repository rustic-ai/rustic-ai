from typing import List, Union

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from rustic_ai.llm_agent.llm_agent_conf import LLMConfigBase
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_agent_utils import LLMAgentUtils


class BasicLLMAgentConfig(LLMConfigBase):
    system_prompt: str
    """System prompt for the LLM agent."""

    def get_llm_params(self) -> dict:
        return self.model_dump(
            exclude_none=True,
            exclude={"system_prompt"},
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
                content=self.system_prompt,
            )
        ]


class BasicLLMAgent(Agent[BasicLLMAgentConfig]):
    """
    A simple LLM Agent that simply invokes an LLM.
    """

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_no_attachments(msg),
        depends_on=["llm"],
    )
    def invoke_llm(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        LLMAgentHelper.invoke_llm_and_handle_response(
            self.name,
            self.config,
            ctx.payload,
            llm,
            ctx,
        )
