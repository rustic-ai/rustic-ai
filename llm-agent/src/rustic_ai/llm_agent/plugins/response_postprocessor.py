from abc import abstractmethod
from typing import List, Optional

from pydantic import BaseModel

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.llm_agent.plugins.base_plugin import BasePlugin


class ResponsePostprocessor(BasePlugin):
    """
    Base class for response postprocessors (plugins inherit from this).

    Postprocessors are called after the LLM response is received, allowing
    additional processing or message generation. They can declare dependencies
    via `depends_on` and access them using `self.get_dep(agent, "name")`.

    Example:
        class MetricsPostprocessor(ResponsePostprocessor):
            depends_on: List[str] = ["metrics"]

            def postprocess(self, agent, ctx, final_prompt, llm_response, llm):
                self.get_dep(agent, "metrics").record_latency(llm_response)
                return None
    """

    @abstractmethod
    def postprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        """
        Postprocess the response received from the LLM.
        This method can perform an action using the response.
        Any values returned from this method will be sent as messages.

        Use `self.get_dep(agent, "name")` to access dependencies declared in `depends_on`.

        Args:
            agent: The agent instance.
            ctx: The process context.
            final_prompt: The final chat completion request sent to the LLM.
            llm_response: The response from the LLM.
            llm: The LLM instance.

        Returns:
            Optional list of messages to send, or None.
        """
        pass
