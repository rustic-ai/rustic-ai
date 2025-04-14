from pydantic import BaseModel

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, AgentMode, AgentSpec, AgentType
from rustic_ai.huggingface.inference_mixin import (
    HuggingfaceInferenceMixin,
)


class QuestionWithContext(BaseModel):
    context: str
    question: str


class SquadAnswer(BaseModel):
    text: str


class SquadAgent(Agent, HuggingfaceInferenceMixin):
    def __init__(
        self,
        agent_spec: AgentSpec,
    ) -> None:
        super().__init__(
            agent_spec,
            AgentType.BOT,
            AgentMode.REMOTE,
        )

    @agent.processor(QuestionWithContext)
    async def find_answer(self, ctx: agent.ProcessContext[QuestionWithContext]):
        """
        Uses the Huggingface model (deepset/roberta-base-squad2) to find the answer to the question in the context.
        """
        question_with_context = ctx.payload
        payload = self.generate_input_prompt(question_with_context.model_dump())
        response = await self.run_inference("deepset/roberta-base-squad2", payload)

        if response:
            result = SquadAnswer(text=response["answer"])

            ctx.send(result)

        else:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="InferenceError",
                    error_message="No answer received from the model.",
                )
            )  # pragma: no cover
