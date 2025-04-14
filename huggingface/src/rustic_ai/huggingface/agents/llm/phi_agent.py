from transformers import AutoModelForCausalLM, AutoTokenizer

from rustic_ai.core.agents.commons.message_formats import (
    GenerationPromptRequest,
    GenerationPromptResponse,
)
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, AgentMode, AgentSpec, AgentType
from rustic_ai.huggingface.agents.models import PyTorchAgentProps


class PhiAgentProps(PyTorchAgentProps):
    model_id: str = "microsoft/phi-2"


class LLMPhiAgent(Agent[PhiAgentProps]):
    """An Agent that generates a response to the given generation prompt using Phi 2."""

    def __init__(
        self,
        agent_spec: AgentSpec[PhiAgentProps],
    ) -> None:
        super().__init__(
            agent_spec=agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )
        if agent_spec.properties is None:
            agent_spec.properties = PhiAgentProps()

        self._device = agent_spec.properties.torch_device
        model_id = agent_spec.properties.model_id
        self.model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True).to(self._device).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True, torch_dtype="auto")

    @agent.processor(GenerationPromptRequest)
    def generate_prompt(self, ctx: agent.ProcessContext[GenerationPromptRequest]) -> None:
        """
        Generates a response to the given generation prompt.
        """
        generation_prompt = ctx.payload.generation_prompt
        inputs = self.tokenizer(generation_prompt, return_tensors="pt", return_attention_mask=False).to(self._device)

        outputs = self.model.generate(**inputs, max_length=200)
        text = self.tokenizer.batch_decode(outputs)[0]

        ctx.send(GenerationPromptResponse(generation_prompt=generation_prompt, generated_response=text))
