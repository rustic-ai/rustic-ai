import logging
import os
from unittest.mock import patch

import pytest

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.serpapi.agent import (
    SERPAgent,
    SERPQuery,
    SERPResults,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestSERPAgent:
    @pytest.mark.skipif(os.getenv("SERP_API_KEY") is None, reason="SERP_API_KEY environment variable not set")
    def test_serp_agent_with_google(self, generator):
        serpAgent, results = wrap_agent_for_testing(
            AgentBuilder(SERPAgent)
            .set_name("TestSerpAgent")
            .set_id("test_agent")
            .set_description("Test Serp Agent")
            .build(),
            generator,
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

    @pytest.mark.skipif(os.getenv("SERP_API_KEY") is None, reason="SERP_API_KEY environment variable not set")
    def test_serp_agent_error_scenario(self, generator):
        with patch("serpapi.Client.search") as mock_search:
            # Configure the mock to return an error response
            mock_search.return_value = {"search_metadata": {"status": "Error", "error": "Test Error"}}

            serpAgent, results = wrap_agent_for_testing(
                AgentBuilder(SERPAgent)
                .set_name("TestSerpAgent")
                .set_id("test_agent")
                .set_description("Test Serp Agent")
                .build(),
                generator,
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
            assert results[0].payload["response"] == {"error": "Test Error", "status": "Error"}
