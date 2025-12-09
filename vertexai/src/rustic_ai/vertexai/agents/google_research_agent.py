from datetime import datetime

from google.genai import types
import shortuuid

from rustic_ai.core import Agent
from rustic_ai.core.agents.commons import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionResponse,
    Choice,
    FinishReason,
)
from rustic_ai.core.guild.dsl import BaseAgentProps
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

    def __init__(self):
        VertexAIBase.__init__(self, self.config.project_id, self.config.location)

    @agent.processor(SERPQuery)
    async def on_message(self, ctx: agent.ProcessContext[SERPQuery]):
        query = ctx.payload.query

        try:
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

            result: str = getattr(response, "text", None) or "No summary available."

            # Extract grounding metadata properly
            grounding_metadata = getattr(
                response.candidates[0] if response.candidates else None, "grounding_metadata", None
            )
            if grounding_metadata:
                grounding_parts = []

                # Extract web sources from grounding chunks
                if hasattr(grounding_metadata, "grounding_chunks") and grounding_metadata.grounding_chunks:
                    sources = []
                    for chunk in grounding_metadata.grounding_chunks:
                        if hasattr(chunk, "web") and chunk.web:
                            web_info = chunk.web
                            source = f"{web_info.title or web_info.domain}: {web_info.uri}"
                            sources.append(source)
                    if sources:
                        grounding_parts.append("**Sources:**\n" + "\n".join(sources))

                # Extract search queries used
                if hasattr(grounding_metadata, "web_search_queries") and grounding_metadata.web_search_queries:
                    queries = [f"- {q}" for q in grounding_metadata.web_search_queries]
                    grounding_parts.append("**Search Queries:**\n" + "\n".join(queries))

                grounding = "\n\n".join(grounding_parts) if grounding_parts else "No grounding information available"
            else:
                grounding = "No grounding metadata found"

            query_id = shortuuid.uuid()
            ccr = ChatCompletionResponse(
                id=f"chatcmpl-{query_id}",
                choices=[Choice(index=0, message=AssistantMessage(content=result), finish_reason=FinishReason.stop)],
                model=self.config.model_id,
                created=int(datetime.now().timestamp()),
            )
            ctx.send(payload=ccr, reason=grounding)
        except Exception as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ResearchErrors",
                    error_message=str(e),
                )
            )
