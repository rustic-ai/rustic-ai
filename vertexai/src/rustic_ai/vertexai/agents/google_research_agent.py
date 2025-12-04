from typing import Any, Dict

from google.genai import types
from pydantic import BaseModel

from rustic_ai.core import Agent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.vertexai.client import VertexAIBase, VertexAIConf
from rustic_ai.serpapi.agent import SERPQuery



class GoogleResearchAgentProps(BaseAgentProps, VertexAIConf):
    model_id: str = "gemini-2.5-pro"
    system_prompt: str | None = None


class ResearchResponse(BaseModel):
    query: str
    response: str


class GoogleResearchAgent(Agent[GoogleResearchAgentProps], VertexAIBase):
    """
    A Rustic AI-compatible research agent that uses Google Gemini directly
    with the Google Search tool enabled. It performs a full research query
    and returns structured findings.
    """

    def __init__(self):
        self.model = self.config.model_id
        self.system_prompt = self.config.system_prompt
        VertexAIBase.__init__(self, self.config.project_id, self.config.location)

    async def research(self, query: str) -> Dict[str, Any]:
        if not self.genai_client:
            raise RuntimeError("Client not initialized. Call startup() first.")

        google_search_tool = types.Tool(google_search=types.GoogleSearch())

        config = types.GenerateContentConfig(
            tools=[google_search_tool],
            temperature=0.3,
            max_output_tokens=2048,
        )

        if self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\nResearch topic: {query}"
        else:
            full_prompt = (
                "You are a Research Agent that uses web search to find current and reliable information. "
                "When needed, call the Google Search tool to retrieve facts, statistics, or latest data. "
                "At the end, summarize your findings clearly with citations where possible.\n\n"
                f"Research topic: {query}"
            )

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=full_prompt)]),
        ]

        response = self.genai_client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        summary = getattr(response, "text", None) or "No summary available."

        return {"query": query, "response": summary}

    @agent.processor(SERPQuery)
    async def on_message(self, ctx: agent.ProcessContext[TextFormat]):
        query = ctx.payload.query
        result = await self.research(query)
        ctx.send(ResearchResponse(query=result["query"], response=result["response"]))
