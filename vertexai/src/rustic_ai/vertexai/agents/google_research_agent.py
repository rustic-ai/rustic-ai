from datetime import datetime

from google.genai import types
import shortuuid

from rustic_ai.core import Agent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionResponse,
    Choice,
    FinishReason,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.serpapi.agent import SERPQuery
from rustic_ai.vertexai.client import VertexAIBase, VertexAIConf


class GoogleResearchAgentProps(BaseAgentProps, VertexAIConf):
    model_id: str = "gemini-2.5-pro"
    system_prompt: str = (
        "You are a Research Agent that uses web search to find current and reliable information. When needed, call the Google Search tool to retrieve facts, "
        "statistics, or latest data. At the end, summarize your findings clearly with citations where possible."
    )
    temperature: float = 0.3
    max_output_tokens: int = 2048


class GoogleResearchAgent(Agent[GoogleResearchAgentProps], VertexAIBase):
    """
    A Rustic AI-compatible research agent that uses Google Gemini directly
    with the Google Search tool enabled. It performs a full research query
    and returns structured findings.
    """

    async def research(self, query: str) -> str:
        VertexAIBase.__init__(self, self.config.project_id, self.config.location)
        if not self.genai_client:
            raise RuntimeError("GenAI Client not initialized.")

        google_search_tool = types.Tool(google_search=types.GoogleSearch())

        config = types.GenerateContentConfig(
            tools=[google_search_tool],
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )

        full_prompt = f"{self.config.system_prompt}. Research topic: {query}"
        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=full_prompt)]),
        ]

        response = self.genai_client.models.generate_content(
            model=self.config.model_id,
            contents=contents,
            config=config,
        )

        summary: str = getattr(response, "text", None) or "No summary available."

        return summary

    @agent.processor(SERPQuery)
    async def on_message(self, ctx: agent.ProcessContext[TextFormat]):
        query = ctx.payload.query
        result = await self.research(query)
        query_id = shortuuid.uuid()
        ccr = ChatCompletionResponse(
            id=f"chatcmpl-{query_id}",
            choices=[Choice(index=0, message=AssistantMessage(content=result), finish_reason=FinishReason.stop)],
            model=self.config.model_id,
            created=int(datetime.now().timestamp()),
        )
        ctx.send(ccr)
