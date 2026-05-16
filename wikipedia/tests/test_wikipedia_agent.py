import pytest
from rustic_ai.testing.helpers import wrap_agent_for_testing

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.wikipedia import (
    WikipediaAgent,
    WikipediaError,
    WikipediaPageRequest,
    WikipediaPageResponse,
    WikipediaSearchRequest,
    WikipediaSearchResponse,
    WikipediaSummaryRequest,
    WikipediaSummaryResponse,
)


@pytest.fixture
def wikipedia_agent_spec():
    """Create a WikipediaAgent spec for testing."""
    return (
        AgentBuilder(WikipediaAgent)
        .set_name("WikipediaAgent")
        .set_id("test_wikipedia_agent")
        .set_description("Wikipedia data connector")
        .set_dependency_map(
            {
                "wikipedia_config": DependencySpec(
                    class_name="rustic_ai.wikipedia.resolver.WikipediaConfigResolver", properties={}
                )
            }
        )
        .build_spec()
    )


@pytest.mark.asyncio
async def test_search_wikipedia(wikipedia_agent_spec, generator):
    """Test searching Wikipedia for articles."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaSearchRequest),
        payload={"query": "Python programming language", "results": 5},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    response = WikipediaSearchResponse.model_validate(results[0].payload)
    assert response.query == "Python programming language"
    assert len(response.results) > 0
    assert any("Python" in result for result in response.results)


@pytest.mark.asyncio
async def test_fetch_page(wikipedia_agent_spec, generator):
    """Test fetching a full Wikipedia page."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaPageRequest),
        payload={"title": "Python (programming language)"},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    response = WikipediaPageResponse.model_validate(results[0].payload)
    assert "Python" in response.title
    assert len(response.summary) > 0
    assert len(response.content) > 0
    assert response.url.startswith("https://")
    assert len(response.categories) > 0


@pytest.mark.asyncio
async def test_fetch_summary(wikipedia_agent_spec, generator):
    """Test fetching a Wikipedia page summary."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaSummaryRequest),
        payload={"title": "Artificial intelligence", "sentences": 3},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    response = WikipediaSummaryResponse.model_validate(results[0].payload)
    assert "Artificial" in response.title or "Intelligence" in response.title
    assert len(response.summary) > 0
    assert response.url.startswith("https://")


@pytest.mark.asyncio
async def test_page_not_found(wikipedia_agent_spec, generator):
    """Test handling of non-existent page."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaPageRequest),
        payload={"title": "ThisPageDefinitelyDoesNotExist12345XYZ", "auto_suggest": False},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    error = WikipediaError.model_validate(results[0].payload)
    assert error.error_type == "PageError"


@pytest.mark.asyncio
async def test_disambiguation_page(wikipedia_agent_spec, generator):
    """Test handling of disambiguation pages."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaPageRequest),
        payload={"title": "Mercury", "auto_suggest": False},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    error = WikipediaError.model_validate(results[0].payload)
    assert error.error_type == "DisambiguationError"
    assert "Multiple pages found" in error.message


@pytest.mark.asyncio
async def test_search_with_custom_results_count(wikipedia_agent_spec, generator):
    """Test searching with custom number of results."""
    agent, results = wrap_agent_for_testing(agent_spec=wikipedia_agent_spec)

    message = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(WikipediaSearchRequest),
        payload={"query": "Machine learning", "results": 3},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(message)

    assert len(results) == 1
    response = WikipediaSearchResponse.model_validate(results[0].payload)
    assert len(response.results) <= 3
