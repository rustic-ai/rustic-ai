import marvin

from rustic_ai.core.agents.commons import (
    ClassifyAndExtractRequest,
    ClassifyAndExtractResponse,
    ClassifyRequest,
    ClassifyResponse,
    ExtractRequest,
    ExtractResponse,
)
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext


class MarvinAgent(Agent):
    """
    An agent that uses prefect's marvin to classify the message into requested categories and extracts the requested data from
    the message into the response.
    """

    @agent.processor(ClassifyRequest)
    async def classifier(self, ctx: ProcessContext[ClassifyRequest]):
        """
        Handles messages of type ClassificationRequest, classifying the text and extracting data
        """
        request = ctx.payload

        category = await marvin.classify_async(
            request.source_text, labels=request.categories, instructions=request.instructions
        )

        response = ClassifyResponse(
            source_text=request.source_text,
            category=category,
        )

        ctx.send(response, reason=f"Text classified into category: {category}")

    @agent.processor(ExtractRequest)
    async def extractor(self, ctx: ProcessContext[ExtractRequest]):
        """
        Handles messages of type ExtractRequest, extracting data from the text
        """
        request = ctx.payload

        try:
            extracted_entities = await marvin.extract_async(  # type: ignore
                request.source_text,
                target=request.extraction_spec.extraction_class,
                instructions=request.extraction_spec.extraction_instructions,
            )

            response = ExtractResponse[request.extraction_spec.extraction_class](
                source_text=request.source_text,
                extracted_data=[
                    (
                        request.extraction_spec.extraction_class.model_validate(e)
                        if not isinstance(e, request.extraction_spec.extraction_class)
                        else e
                    )
                    for e in extracted_entities
                ],
            )

            ctx.send(response, reason=f"Successfully extracted {len(extracted_entities)} entities from text")
        except Exception as e:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(), error_type="ExtractorError", error_message=str(e)
                ),
                reason=f"Extraction failed: {str(e)}",
            )

    @agent.processor(ClassifyAndExtractRequest)
    def classify_and_extract(self, ctx: ProcessContext[ClassifyAndExtractRequest]):
        """
        Handles messages of type ClassifyAndExtractRequest, classifying the text and extracting data
        """
        request = ctx.payload

        category = marvin.classify(
            request.source_text, labels=request.categories, instructions=request.classification_instructions
        )

        extracted_data = marvin.extract(  # type: ignore
            request.source_text,
            target=request.get_extraction_class_for_category(category),
            instructions=request.get_extraction_instructions_for_category(category),
        )

        response = ClassifyAndExtractResponse(
            source_text=request.source_text,
            category=category,
            extracted_data=extracted_data,
        )  # type: ignore

        ctx.send(
            response,
            reason=f"Text classified as '{category}' and extracted {len(extracted_data) if hasattr(extracted_data, '__len__') else '0'} entities",
        )
