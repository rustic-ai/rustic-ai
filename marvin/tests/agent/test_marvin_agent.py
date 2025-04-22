import asyncio
import os

import pytest
from flaky import flaky
from pydantic import BaseModel

from rustic_ai.core.agents.commons import (
    ClassifyAndExtractRequest,
    ClassifyAndExtractResponse,
    ClassifyRequest,
    ClassifyResponse,
    ExtractionSpec,
    ExtractRequest,
    ExtractResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.marvin import MarvinAgent

from rustic_ai.testing.helpers import wrap_agent_for_testing


class CityPopulation(BaseModel):
    city: str
    population: int
    year: int


class StatePopulation(BaseModel):
    state: str
    population: int
    year: int


@pytest.mark.skipif(os.getenv("OPENAI_API_KEY") is None, reason="OPENAI_API_KEY environment variable not set")
class TestMarvinAgent:
    @pytest.fixture
    def agent(self):
        agent = (
            AgentBuilder(MarvinAgent)
            .set_id("marvin_agent")
            .set_name("Marvin")
            .set_description("A classifier agent using Marvin")
            .build()
        )
        return agent

    @flaky(max_runs=3, min_passes=1)
    async def test_classifier(self, agent: MarvinAgent, generator):
        marvin_agent, messages = wrap_agent_for_testing(agent, generator)

        classify_request = ClassifyRequest(
            source_text="I am very happy with this product",
            categories=["positive", "negative"],
        )

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=classify_request.model_dump(),
            format=get_qualified_class_name(ClassifyRequest),
        )

        marvin_agent._on_message(message)

        tries = 0
        while True:
            tries += 1
            await asyncio.sleep(1)
            if len(messages) > 0 or tries > 10:
                break

        assert len(messages) > 0

        response = ClassifyResponse.model_validate(messages[0].payload)

        assert response.source_text == classify_request.source_text
        assert response.category == "positive"

    @flaky(max_runs=3, min_passes=1)
    async def test_extractor(self, agent: MarvinAgent, generator):
        marvin_agent, messages = wrap_agent_for_testing(agent, generator)

        extract_request = ExtractRequest(
            source_text="The current metro area population of London in 2024 is 9,748,000, a 1.04% increase from 2023.",
            extraction_spec=ExtractionSpec(pydantic_model_to_extract=get_qualified_class_name(CityPopulation)),
        )

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=extract_request.model_dump(),
            format=get_qualified_class_name(ExtractRequest),
        )

        marvin_agent._on_message(message)

        tries = 0
        while True:
            tries += 1
            await asyncio.sleep(1)
            if len(messages) > 0 or tries > 10:
                break

        assert len(messages) > 0

        response = ExtractResponse[CityPopulation].model_validate(messages[0].payload)

        assert response.source_text == extract_request.source_text

        assert len(response.extracted_data) == 1

        assert isinstance(response.extracted_data[0], CityPopulation)

        assert response.extracted_data[0].city == "London"
        assert response.extracted_data[0].population == 9748000
        assert response.extracted_data[0].year == 2024

    @flaky(max_runs=3, min_passes=1)
    async def test_classify_and_extract(self, agent: MarvinAgent, generator):
        marvin_agent, messages = wrap_agent_for_testing(agent, generator)

        category_map = {
            "city": ExtractionSpec(pydantic_model_to_extract=get_qualified_class_name(CityPopulation)),
            "state": ExtractionSpec(pydantic_model_to_extract=get_qualified_class_name(StatePopulation)),
        }

        classify_and_extract_request = ClassifyAndExtractRequest(
            source_text="The current metro area population of London in 2024 is 9,748,000, a 1.04% increase from 2023.",
            classification_instructions="Categorize if the text is about a city or a state.",
            categories_extractions_map=category_map,
        )

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=classify_and_extract_request.model_dump(),
            format=get_qualified_class_name(ClassifyAndExtractRequest),
        )

        marvin_agent._on_message(message)

        tries = 0
        while True:
            tries += 1
            await asyncio.sleep(1)
            if len(messages) > 0 or tries > 10:
                break

        assert len(messages) > 0

        response = ClassifyAndExtractResponse[CityPopulation].model_validate(messages[0].payload)

        assert response.source_text == classify_and_extract_request.source_text
        assert response.category == "city"

        assert len(response.extracted_data) == 1

        assert isinstance(response.extracted_data[0], CityPopulation)

        assert response.extracted_data[0].city == "London"
        assert response.extracted_data[0].population == 9748000
        assert response.extracted_data[0].year == 2024

        classify_and_extract_request2 = ClassifyAndExtractRequest(
            source_text="With an estimated population of 5.6 million as of 2024, it is Canada's third-most populous province.",
            classification_instructions="Categorize if the text is about a city or a state.",
            categories_extractions_map=category_map,
        )

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=classify_and_extract_request2.model_dump(),
            format=get_qualified_class_name(ClassifyAndExtractRequest),
        )

        marvin_agent._on_message(message)

        assert len(messages) > 1

        response2 = ClassifyAndExtractResponse[StatePopulation].model_validate(messages[1].payload)

        assert response2.source_text == classify_and_extract_request2.source_text
        assert response2.category == "state"

        assert len(response2.extracted_data) == 1

        assert isinstance(response2.extracted_data[0], StatePopulation)

        assert response2.extracted_data[0].state == "British Columbia"
        assert response2.extracted_data[0].population == 5600000
        assert response2.extracted_data[0].year == 2024
