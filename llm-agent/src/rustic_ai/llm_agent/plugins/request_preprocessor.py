from abc import abstractmethod

from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionRequest
from rustic_ai.llm_agent.plugins.base_plugin import BasePlugin


class RequestPreprocessor(BasePlugin):
    """
    Base class for request preprocessors (plugins inherit from this).

    Preprocessors are called before the LLM request is sent, allowing
    modification of the request. They can declare dependencies via the
    `depends_on` field and access them using `self.get_dep(agent, "name")`.

    Example:
        class LoggingPreprocessor(RequestPreprocessor):
            depends_on: List[str] = ["logger"]

            def preprocess(self, agent, ctx, request, llm):
                self.get_dep(agent, "logger").info("Processing request")
                return request
    """

    @abstractmethod
    def preprocess(
        self,
        agent: Agent,
        ctx: ProcessContext[ChatCompletionRequest],
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        """
        Preprocess the prompt before sending it to the LLM.
        This method can modify the prompt as needed.

        Use `self.get_dep(agent, "name")` to access dependencies declared in `depends_on`.

        Args:
            agent: The agent instance.
            ctx: The process context.
            request: The chat completion request.
            llm: The LLM instance.

        Returns:
            The (possibly modified) chat completion request.
        """
        pass
