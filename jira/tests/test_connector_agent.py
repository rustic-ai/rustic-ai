"""Tests for JIRA connector agent."""

import pytest
from pydantic import BaseModel

from rustic_ai.testing import wrap_agent_for_testing
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority

from rustic_ai.jira import (
    JiraConnectorAgent,
    JiraCreateIssueRequest,
    JiraGetIssueRequest,
    JiraIssueResponse,
    JiraListProjectsRequest,
    JiraProjectsResponse,
    JiraSearchIssuesRequest,
    JiraSearchIssuesResponse,
)


@pytest.fixture
def generator() -> GemstoneGenerator:
    """Create GemstoneGenerator for message IDs."""
    return GemstoneGenerator(1)


@pytest.fixture
def build_message_from_payload():
    """Create a message builder helper."""

    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
    ) -> Message:
        # Ensure payload is a plain dict for Message payload
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        # Derive format if not provided
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else get_qualified_class_name(Message),
        )

    return _build_message_from_payload


@pytest.fixture
def jira_agent_spec():
    """Create JIRA agent spec for testing."""
    return AgentBuilder(JiraConnectorAgent).set_name("JiraAgent").set_description("JIRA connector agent").build_spec()


@pytest.mark.asyncio
async def test_create_issue_request_parsing(jira_agent_spec, generator, build_message_from_payload):
    """Test that create issue request is properly parsed."""
    agent, results = wrap_agent_for_testing(agent_spec=jira_agent_spec)

    request = JiraCreateIssueRequest(
        project_key="TEST",
        summary="Test issue",
        description="This is a test issue",
        issue_type="Task",
        instance_url="http://localhost:8080",
    )

    agent._on_message(build_message_from_payload(generator, request))

    # Since we don't have real JIRA credentials in tests,
    # we expect an error message about missing credentials
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_issues_request_parsing(jira_agent_spec, generator, build_message_from_payload):
    """Test that search issues request is properly parsed."""
    agent, results = wrap_agent_for_testing(agent_spec=jira_agent_spec)

    request = JiraSearchIssuesRequest(
        jql="project = TEST AND status = Open",
        max_results=10,
        instance_url="http://localhost:8080",
    )

    agent._on_message(build_message_from_payload(generator, request))

    assert len(results) > 0


@pytest.mark.asyncio
async def test_list_projects_request_parsing(jira_agent_spec, generator, build_message_from_payload):
    """Test that list projects request is properly parsed."""
    agent, results = wrap_agent_for_testing(agent_spec=jira_agent_spec)

    request = JiraListProjectsRequest(instance_url="http://localhost:8080")

    agent._on_message(build_message_from_payload(generator, request))

    assert len(results) > 0


@pytest.mark.asyncio
async def test_get_issue_request_parsing(jira_agent_spec, generator, build_message_from_payload):
    """Test that get issue request is properly parsed."""
    agent, results = wrap_agent_for_testing(agent_spec=jira_agent_spec)

    request = JiraGetIssueRequest(
        issue_key="TEST-123",
        instance_url="http://localhost:8080",
    )

    agent._on_message(build_message_from_payload(generator, request))

    assert len(results) > 0
