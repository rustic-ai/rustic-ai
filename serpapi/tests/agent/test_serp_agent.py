import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from serpapi.exceptions import (
    HTTPConnectionError,
    HTTPError,
    SerpApiError,
    TimeoutError,
)
from serpapi.models import SerpResults as ProviderSerpResults

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.serpapi.agent import (
    SearchError,
    SERPAgent,
    SERPQuery,
    SERPResults,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestSERPAgent:
    def test_search_errors_use_error_transport(self):
        ctx = MagicMock()
        ctx.payload = SERPQuery(engine="google", query="multi-agent AI", id="query-1")

        SERPAgent._send_search_error(ctx, "search_timeout")

        ctx.send.assert_not_called()
        ctx.send_error.assert_called_once_with(
            SearchError(
                id="query-1",
                response={
                    "status": "Error",
                    "code": "search_timeout",
                    "error": "The search provider could not complete the request.",
                },
            )
        )

    @pytest.mark.skipif(os.getenv("SERP_API_KEY") is None, reason="SERP_API_KEY environment variable not set")
    def test_serp_agent_with_google(self, generator):
        serpAgent, results = wrap_agent_for_testing(
            AgentBuilder(SERPAgent)
            .set_name("TestSerpAgent")
            .set_id("test_agent")
            .set_description("Test Serp Agent")
            .build_spec(),
        )

        query = Message(
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            format=get_qualified_class_name(SERPQuery),
            payload={"engine": "google", "query": "multi-agent AI"},
            id_obj=generator.get_id(Priority.NORMAL),
        )
        serpAgent._on_message(query)

        logging.info(results)
        assert len(results) > 0
        assert results[0].priority == Priority.NORMAL
        assert results[0].in_response_to == query.id
        assert results[0].current_thread_id == query.id
        assert results[0].recipient_list == []

        assert len(results) == 1

        search_result = SERPResults.model_validate(results[0].payload)

        assert search_result.count > 0
        assert search_result.results is not None
        assert len(search_result.results) == search_result.count

        assert search_result.engine == "google"
        assert search_result.query == "multi-agent AI"

        result01 = search_result.results[0]

        assert result01.metadata is not None
        assert result01.metadata["title"] is not None
        assert result01.url is not None

    def test_serp_agent_error_scenario(self, generator, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "test-key")
        with patch("serpapi.Client.search") as mock_search:
            # Configure the mock to return an error response
            mock_search.return_value = {
                "search_metadata": {
                    "status": "Error",
                    "error": "Test Error containing test-key",
                    "json_endpoint": "https://serpapi.example/search?api_key=test-key",
                }
            }

            serpAgent, results = wrap_agent_for_testing(
                AgentBuilder(SERPAgent)
                .set_name("TestSerpAgent")
                .set_id("test_agent")
                .set_description("Test Serp Agent")
                .build_spec(),
            )

            query = Message(
                topics="default_topic",
                sender=AgentTag(id="testerId", name="tester"),
                format=get_qualified_class_name(SERPQuery),
                payload={"engine": "google", "query": "multi-agent AI"},
                id_obj=generator.get_id(Priority.NORMAL),
            )
            serpAgent._on_message(query)

            # Assert that an error message is published
            assert len(results) > 0
            error = SearchError.model_validate(results[0].payload)
            assert error.response == {
                "status": "Error",
                "code": "search_rejected",
                "error": "The search provider could not complete the request.",
            }
            assert "test-key" not in str(results[0].payload)

    def test_serp_agent_accepts_provider_serp_results(self, generator, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "test-key")
        provider_results = ProviderSerpResults(
            {
                "search_metadata": {"status": "Success"},
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Rustic AI",
                        "link": "https://rustic.ai/",
                        "snippet": "Build multi-agent systems.",
                    }
                ],
                "search_information": {"total_results": 1},
            },
            client=MagicMock(),
        )

        with patch("serpapi.Client.search", return_value=provider_results):
            serp_agent, results = wrap_agent_for_testing(
                AgentBuilder(SERPAgent)
                .set_name("TestSerpAgent")
                .set_id("test_agent")
                .set_description("Test Serp Agent")
                .build_spec(),
            )
            query = Message(
                topics="default_topic",
                sender=AgentTag(id="testerId", name="tester"),
                format=get_qualified_class_name(SERPQuery),
                payload={"engine": "google", "query": "multi-agent AI", "id": "query-3"},
                id_obj=generator.get_id(Priority.NORMAL),
            )
            serp_agent._on_message(query)

        assert len(results) == 1
        search_result = SERPResults.model_validate(results[0].payload)
        assert search_result.id == "query-3"
        assert search_result.count == 1
        assert search_result.total_results == 1
        assert search_result.results[0].url == "https://rustic.ai/"

    @pytest.mark.parametrize(
        ("exception", "expected_code"),
        [
            (TimeoutError("secret-in-url"), "search_timeout"),
            (HTTPConnectionError(Exception("secret-in-url")), "search_unavailable"),
            (HTTPError(Exception("secret-in-url")), "search_provider_error"),
            (SerpApiError("secret-in-url"), "search_provider_error"),
        ],
    )
    def test_serp_agent_sanitizes_provider_exceptions(
        self,
        generator,
        monkeypatch,
        caplog,
        exception,
        expected_code,
    ):
        monkeypatch.setenv("SERP_API_KEY", "test-key")
        with patch("serpapi.Client.search", side_effect=exception):
            serp_agent, results = wrap_agent_for_testing(
                AgentBuilder(SERPAgent)
                .set_name("TestSerpAgent")
                .set_id("test_agent")
                .set_description("Test Serp Agent")
                .build_spec(),
            )

            query = Message(
                topics="default_topic",
                sender=AgentTag(id="testerId", name="tester"),
                format=get_qualified_class_name(SERPQuery),
                payload={"engine": "google", "query": "multi-agent AI", "id": "query-1"},
                id_obj=generator.get_id(Priority.NORMAL),
            )
            serp_agent._on_message(query)

        assert len(results) == 1
        error = SearchError.model_validate(results[0].payload)
        assert error.id == "query-1"
        assert error.response["code"] == expected_code
        assert "secret-in-url" not in str(results[0].payload)
        assert "secret-in-url" not in caplog.text

    def test_serp_agent_rejects_malformed_provider_response(self, generator, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "test-key")
        with patch("serpapi.Client.search", return_value={"unexpected": "test-key"}):
            serp_agent, results = wrap_agent_for_testing(
                AgentBuilder(SERPAgent)
                .set_name("TestSerpAgent")
                .set_id("test_agent")
                .set_description("Test Serp Agent")
                .build_spec(),
            )
            query = Message(
                topics="default_topic",
                sender=AgentTag(id="testerId", name="tester"),
                format=get_qualified_class_name(SERPQuery),
                payload={"engine": "google", "query": "multi-agent AI", "id": "query-2"},
                id_obj=generator.get_id(Priority.NORMAL),
            )
            serp_agent._on_message(query)

        error = SearchError.model_validate(results[0].payload)
        assert error.response["code"] == "invalid_provider_response"
        assert "test-key" not in str(results[0].payload)
