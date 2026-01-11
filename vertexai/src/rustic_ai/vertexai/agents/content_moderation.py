from typing import List, Optional

from google.cloud import language
import pandas as pd
from pydantic import BaseModel, Field

from rustic_ai.core import Agent
from rustic_ai.core.guild import BaseAgentProps, agent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    TextContentPart,
    UserMessage,
)
from rustic_ai.vertexai.client import VertexAIBase, VertexAIConf


class ContentModeratorProps(BaseAgentProps, VertexAIConf):
    threshold: Optional[float] = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence threshold for flagging content"
    )
    categories: List[str] = Field(
        default=[],
        description="Categories that should be considered for content moderation. If none are provided, "
        "all categories will be considered.",
    )


class ModerationResponse(BaseModel):
    source_text: str
    is_flagged: bool = Field(description="Whether content was flagged")
    max_confidence: Optional[float] = Field(None, description="Highest confidence score")
    flagged_categories: Optional[dict[str, float]] = Field(
        None, description="Categories that exceeded threshold with their confidence scores"
    )


class ModerationResponseWithReason(BaseModel):
    response: ModerationResponse
    reason: str


class ContentModerationAgent(Agent[ContentModeratorProps], VertexAIBase):
    def __init__(self):
        VertexAIBase.__init__(self, self.config.project_id, self.config.location)
        self.client = language.LanguageServiceClient()  # Reuse client instance

    def moderate_text(self, text_content: str) -> ModerationResponseWithReason:
        # Validate input
        if not text_content or not text_content.strip():
            return ModerationResponseWithReason(
                response=ModerationResponse(source_text="", is_flagged=False), reason="Empty input provided"
            )

        document = language.Document(
            content=text_content,
            type_=language.Document.Type.PLAIN_TEXT,
        )

        response: language.ModerateTextResponse = self.client.moderate_text(document=document)

        # Get categories to check from config (if provided and not empty)
        requested_categories = self.config.categories if self.config.categories else None

        # Sort categories by confidence (descending)
        categories = sorted(response.moderation_categories, key=lambda cat: cat.confidence, reverse=True)

        # Filter categories if specific ones were requested
        if requested_categories:
            categories_to_check = [cat for cat in categories if cat.name in requested_categories]
        else:
            categories_to_check = categories

        # Find flagged categories with their confidence scores
        flagged_categories = {
            cat.name: cat.confidence for cat in categories_to_check if cat.confidence >= self.config.threshold
        }
        is_flagged = len(flagged_categories) > 0

        # Max confidence from categories that were actually checked
        max_confidence = categories_to_check[0].confidence if categories_to_check else None

        # Generate reason using Markdown table (show all categories, but only flag specified ones)
        data = [(cat.name, cat.confidence) for cat in categories]
        df = pd.DataFrame(data, columns=["category", "confidence"])
        reason = df.to_markdown(index=False, tablefmt="github", floatfmt=".2%")

        if requested_categories:
            reason = f"**Checked categories:** {', '.join(requested_categories)}\n\n{reason}"

        return ModerationResponseWithReason(
            response=ModerationResponse(
                source_text=text_content,
                is_flagged=is_flagged,
                max_confidence=max_confidence,
                flagged_categories=flagged_categories if is_flagged else None,
            ),
            reason=reason,
        )

    @agent.processor(ChatCompletionRequest)
    def moderate_llm_request(self, ctx: agent.ProcessContext[ChatCompletionRequest]):
        content_list = []
        for msg in ctx.payload.messages:
            if isinstance(msg, UserMessage):
                if isinstance(msg.content, str):
                    content_list.append(msg.content)
                else:
                    # Extract text from content parts
                    for part in msg.content.root:
                        if isinstance(part, TextContentPart):
                            content_list.extend([part.text])
        combined_text: str = " ".join(content_list)
        result: ModerationResponseWithReason = self.moderate_text(combined_text)
        ctx.send(result.response, reason=result.reason)

    @agent.processor(ChatCompletionResponse)
    def moderate_llm_response(self, ctx: agent.ProcessContext[ChatCompletionResponse]):
        first_choice = ctx.payload.choices[0] if ctx.payload.choices else None
        if first_choice and first_choice.message.content:
            result: ModerationResponseWithReason = self.moderate_text(first_choice.message.content)
            ctx.send(result.response, reason=result.reason)
        else:
            ctx.send(ModerationResponse(source_text="", is_flagged=False), reason="Empty input provided")
