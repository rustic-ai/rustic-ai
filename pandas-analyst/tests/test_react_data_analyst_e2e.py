"""
End-to-end integration tests for ReActAgent.

These tests initialize a full guild with the ReActAgent,
use a ProbeAgent to send messages and verify tool calls happen as expected.
"""

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

from flaky import flaky
from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
    FunctionCall,
    ToolType,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority
from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver
from rustic_ai.llm_agent.react import ReActAgent, ReActAgentConfig

from rustic_ai.pandas_analyst.react_toolset import DataAnalystReActToolset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory with sample CSV data for testing."""
    tmpdir = tempfile.mkdtemp()

    # Create a sample CSV file
    data_path = os.path.join(tmpdir, "sales_data.csv")
    with open(data_path, "w") as f:
        f.write("id,product,quantity,price,category\n")
        f.write("1,Apple,50,1.50,Fruit\n")
        f.write("2,Banana,30,0.75,Fruit\n")
        f.write("3,Carrot,25,0.50,Vegetable\n")
        f.write("4,Orange,40,1.25,Fruit\n")
        f.write("5,Broccoli,15,1.00,Vegetable\n")

    # Create another sample CSV
    employees_path = os.path.join(tmpdir, "employees.csv")
    with open(employees_path, "w") as f:
        f.write("id,name,department,salary\n")
        f.write("1,Alice,Engineering,75000\n")
        f.write("2,Bob,Marketing,60000\n")
        f.write("3,Charlie,Engineering,80000\n")
        f.write("4,Diana,Sales,55000\n")
        f.write("5,Eve,Engineering,90000\n")

    yield tmpdir

    # Cleanup
    shutil.rmtree(tmpdir)


@pytest.fixture
def generator() -> GemstoneGenerator:
    return GemstoneGenerator(1)


@pytest.fixture
def org_id():
    return "test_data_analyst_org"


@pytest.fixture
def probe_spec():
    """Create a unique probe agent spec for each test."""
    probe_id = f"probe_{uuid.uuid4().hex[:8]}"
    return (
        AgentBuilder(ProbeAgent)
        .set_id(probe_id)
        .set_name(f"Probe Agent {probe_id}")
        .set_description("A probe agent for testing")
        .build_spec()
    )


@pytest.fixture
def build_message_from_payload():
    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
    ):
        from rustic_ai.core.messaging.core.message import AgentTag, Message
        from rustic_ai.core.guild.dsl import GuildTopics

        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )
        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else "raw_json",
        )
    return _build_message_from_payload


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def create_mock_response(
    content: str,
    tool_calls: List[ChatCompletionMessageToolCall] | None = None,
    finish_reason: FinishReason = FinishReason.stop,
) -> ChatCompletionResponse:
    """Helper to create mock LLM responses."""
    return ChatCompletionResponse(
        id="chatcmpl-test",
        created=1234567890,
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=AssistantMessage(
                    content=content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )


def create_tool_call(
    tool_id: str,
    name: str,
    arguments: dict,
) -> ChatCompletionMessageToolCall:
    """Helper to create tool call objects."""
    import json
    return ChatCompletionMessageToolCall(
        id=tool_id,
        type=ToolType.function,
        function=FunctionCall(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


# ---------------------------------------------------------------------------
# Unit Tests with Mocked LLM
# ---------------------------------------------------------------------------


class TestReactDataAnalystToolset:
    """Unit tests for the DataAnalystReActToolset."""

    def test_toolset_has_expected_tools(self):
        """Test that the toolset exposes the expected data analyst tools."""
        toolset = DataAnalystReActToolset()
        specs = toolset.get_toolspecs()

        tool_names = [spec.name for spec in specs]

        # Should have data analyst tools plus load_file
        assert "load_file" in tool_names
        assert "query_dataset" in tool_names
        assert "get_schema" in tool_names
        assert "preview_dataset" in tool_names
        assert "describe_dataset" in tool_names

    def test_toolset_is_self_contained(self, temp_data_dir):
        """Test that toolset creates its own dependencies lazily."""
        from rustic_ai.pandas_analyst.react_toolset import LoadFileRequest

        toolset = DataAnalystReActToolset(filesystem_base_path=temp_data_dir)

        # Verify toolset lazily creates analyzer and filesystem
        assert toolset.analyzer is not None
        assert toolset.filesystem is not None

        # Should be able to load a file without external dependency injection
        args = LoadFileRequest(filename="sales_data.csv", dataset_name="sales")
        result = toolset.execute("load_file", args)

        # Should succeed and return dataset info
        assert "sales" in result.lower() or "num_rows" in result.lower()


class TestReactDataAnalystWithMockedLLM:
    """Tests for ReActAgent with mocked LLM responses."""

    def test_agent_loads_file_and_queries(self, temp_data_dir, generator, build_message_from_payload):
        """Test agent can load a file and execute a query using tool calls."""
        from rustic_ai.testing.helpers import wrap_agent_for_testing

        # Create agent spec with self-contained toolset
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_analyst")
            .set_name("React Data Analyst")
            .set_description("A ReAct agent for data analysis")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    max_iterations=10,
                    toolset=DataAnalystReActToolset(
                        filesystem_base_path=temp_data_dir,
                    ),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        # Set up mock responses for a multi-step interaction:
        # 1. Load the file
        # 2. Query the data
        # 3. Return final answer
        import json

        responses = [
            # First: Load the file
            create_mock_response(
                content="I need to load the sales data file first.",
                tool_calls=[create_tool_call(
                    "call_1",
                    "load_file",
                    {"filename": "sales_data.csv", "dataset_name": "sales"}
                )],
                finish_reason=FinishReason.tool_calls,
            ),
            # Second: Query the data
            create_mock_response(
                content="Now I'll query the data to find total quantity.",
                tool_calls=[create_tool_call(
                    "call_2",
                    "query_dataset",
                    {
                        "query_language": "sql",
                        "query_string": "SELECT SUM(quantity) as total FROM sales",
                        "input_datasets": {"sales": "sales"}
                    }
                )],
                finish_reason=FinishReason.tool_calls,
            ),
            # Third: Final answer
            create_mock_response(
                content="The total quantity of all products is 160."
            ),
        ]

        call_count = [0]

        def mock_call_llm(llm, request):
            response = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(
                        messages=[UserMessage(content="What is the total quantity of all products in sales_data.csv?")]
                    ),
                )
            )

        # Verify results
        assert len(results) >= 1
        response = ChatCompletionResponse.model_validate(results[0].payload)
        assert response.choices[0].message.content == "The total quantity of all products is 160."

        # Check react_trace contains the expected tool calls
        provider_fields = response.choices[0].provider_specific_fields
        assert provider_fields is not None
        assert "react_trace" in provider_fields

        trace = provider_fields["react_trace"]
        assert len(trace) >= 2

        # Verify tool calls were made in order
        tool_names = [step["action"] for step in trace]
        assert "load_file" in tool_names
        assert "query_dataset" in tool_names

    def test_agent_handles_get_schema(self, temp_data_dir, generator, build_message_from_payload):
        """Test agent can get schema of a loaded dataset."""
        from rustic_ai.testing.helpers import wrap_agent_for_testing

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_analyst")
            .set_name("React Data Analyst")
            .set_description("A ReAct agent for data analysis")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    max_iterations=5,
                    toolset=DataAnalystReActToolset(
                        filesystem_base_path=temp_data_dir,
                    ),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        responses = [
            create_mock_response(
                content="Loading the file first.",
                tool_calls=[create_tool_call(
                    "call_1",
                    "load_file",
                    {"filename": "employees.csv", "dataset_name": "employees"}
                )],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="Now getting the schema.",
                tool_calls=[create_tool_call(
                    "call_2",
                    "get_schema",
                    {"name": "employees"}
                )],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(
                content="The employees dataset has columns: id (int), name (str), department (str), salary (int)."
            ),
        ]

        call_count = [0]

        def mock_call_llm(llm, request):
            response = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(
                        messages=[UserMessage(content="What columns are in the employees.csv file?")]
                    ),
                )
            )

        assert len(results) >= 1
        response = ChatCompletionResponse.model_validate(results[0].payload)

        provider_fields = response.choices[0].provider_specific_fields
        trace = provider_fields.get("react_trace", [])

        tool_names = [step["action"] for step in trace]
        assert "load_file" in tool_names
        assert "get_schema" in tool_names


# ---------------------------------------------------------------------------
# Integration Tests with Full Guild (Real LLM)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests (set SKIP_EXPENSIVE_TESTS=false to run)",
)
@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ,
    reason="OPENAI_API_KEY not set",
)
class TestReactDataAnalystGuildIntegration:
    """Full end-to-end integration tests with a running guild and real LLM."""

    @flaky(max_runs=3, min_passes=1)
    def test_full_guild_data_analysis_workflow(self, temp_data_dir, probe_spec, org_id):
        """
        Test the full workflow:
        1. Start a guild with ReActAgent
        2. Send a data analysis request
        3. Verify the agent uses tools correctly
        4. Check the final response
        """
        guild_id = f"data_analyst_test_guild_{uuid.uuid4().hex[:8]}"

        # Create GUILD_GLOBAL directory and copy test files there
        # FileSystemResolver expects files at {path_base}/{org_id}/{guild_id}/GUILD_GLOBAL/
        guild_global_dir = os.path.join(temp_data_dir, org_id, guild_id, "GUILD_GLOBAL")
        os.makedirs(guild_global_dir, exist_ok=True)
        shutil.copy(os.path.join(temp_data_dir, "sales_data.csv"), guild_global_dir)
        shutil.copy(os.path.join(temp_data_dir, "employees.csv"), guild_global_dir)

        # Dependency map with real LLM
        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-4o-mini"},
            ),
        }

        # Build the agent spec with self-contained toolset
        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_analyst")
            .set_name("React Data Analyst Agent")
            .set_description("A ReAct agent that analyzes data using pandas")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=10,
                    toolset=DataAnalystReActToolset(
                        filesystem_base_path=guild_global_dir,
                        use_guild_filesystem=False,
                    ),
                )
            )
            .build_spec()
        )

        # Build and launch guild
        guild_builder = (
            GuildBuilder(guild_id, "Data Analyst Test Guild", "Guild to test ReActAgent")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)

        # Add probe agent
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        try:
            # Send a data analysis request
            probe_agent.publish_dict(
                topic="default_topic",
                payload={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Load the sales_data.csv file and tell me the total quantity of all Fruit products."
                        }
                    ]
                },
                format=ChatCompletionRequest,
            )

            # Wait for processing
            time.sleep(10.0)

            # Get messages
            messages = probe_agent.get_messages()
            assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

            # Find ChatCompletionResponse
            react_responses = [
                m for m in messages
                if m.format == get_qualified_class_name(ChatCompletionResponse)
            ]
            assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

            response = ChatCompletionResponse.model_validate(react_responses[-1].payload)
            answer = response.choices[0].message.content or ""

            # Verify the answer mentions the correct total
            # Fruit products: Apple (50) + Banana (30) + Orange (40) = 120
            assert "120" in answer, f"Expected answer to contain '120', got: {answer}"

            # Verify tool usage
            provider_fields = response.choices[0].provider_specific_fields
            if provider_fields and "react_trace" in provider_fields:
                trace = provider_fields["react_trace"]
                tool_names = [step.get("action") for step in trace if step.get("action")]
                # Should have used load_file and query_dataset
                assert any("load" in name.lower() for name in tool_names), "Should have loaded a file"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()

    @flaky(max_runs=3, min_passes=1)
    def test_guild_describe_dataset(self, temp_data_dir, probe_spec, org_id):
        """Test that the agent can describe a dataset's statistics."""
        guild_id = f"data_analyst_describe_guild_{uuid.uuid4().hex[:8]}"

        # Create GUILD_GLOBAL directory and copy test files there
        # FileSystemResolver expects files at {path_base}/{org_id}/{guild_id}/GUILD_GLOBAL/
        guild_global_dir = os.path.join(temp_data_dir, org_id, guild_id, "GUILD_GLOBAL")
        os.makedirs(guild_global_dir, exist_ok=True)
        shutil.copy(os.path.join(temp_data_dir, "employees.csv"), guild_global_dir)

        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-4o-mini"},
            ),
        }

        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_analyst")
            .set_name("React Data Analyst Agent")
            .set_description("A ReAct agent that analyzes data using pandas")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=10,
                    toolset=DataAnalystReActToolset(
                        filesystem_base_path=guild_global_dir,
                        use_guild_filesystem=False,
                    ),
                )
            )
            .build_spec()
        )

        guild_builder = (
            GuildBuilder(guild_id, "Data Analyst Test Guild", "Guild to test ReActAgent")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)

        try:
            probe_agent.publish_dict(
                topic="default_topic",
                payload={
                    "messages": [
                        {
                            "role": "user",
                            "content": "Load employees.csv and tell me the average salary."
                        }
                    ]
                },
                format=ChatCompletionRequest,
            )

            time.sleep(10.0)

            messages = probe_agent.get_messages()
            assert len(messages) >= 1

            react_responses = [
                m for m in messages
                if m.format == get_qualified_class_name(ChatCompletionResponse)
            ]
            assert len(react_responses) >= 1

            response = ChatCompletionResponse.model_validate(react_responses[-1].payload)
            answer = response.choices[0].message.content or ""

            # Average salary: (75000 + 60000 + 80000 + 55000 + 90000) / 5 = 72000
            assert "72000" in answer or "72,000" in answer, f"Expected average salary 72000, got: {answer}"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()


# ---------------------------------------------------------------------------
# Tool Call Verification Tests
# ---------------------------------------------------------------------------


class TestToolCallVerification:
    """Tests that verify specific tool calls are made correctly."""

    def test_load_file_tool_call_arguments(self, temp_data_dir, generator, build_message_from_payload):
        """Verify that load_file is called with correct arguments."""
        from rustic_ai.testing.helpers import wrap_agent_for_testing

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_analyst")
            .set_name("React Data Analyst")
            .set_description("A ReAct agent for data analysis")
            .set_properties(
                ReActAgentConfig(
                    model="test-model",
                    max_iterations=5,
                    toolset=DataAnalystReActToolset(
                        filesystem_base_path=temp_data_dir,
                    ),
                )
            )
            .build_spec()
        )

        mock_dependency_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "test-model"},
            ),
        }

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=mock_dependency_map,
        )

        responses = [
            create_mock_response(
                content="Loading sales data.",
                tool_calls=[create_tool_call(
                    "call_1",
                    "load_file",
                    {"filename": "sales_data.csv", "dataset_name": "sales"}
                )],
                finish_reason=FinishReason.tool_calls,
            ),
            create_mock_response(content="File loaded successfully with 5 rows.")
        ]

        call_count = [0]

        def mock_call_llm(llm, request):
            response = responses[min(call_count[0], len(responses) - 1)]
            call_count[0] += 1
            return response

        with patch.object(agent, "_call_llm_direct", side_effect=mock_call_llm):
            agent._on_message(
                build_message_from_payload(
                    generator,
                    ChatCompletionRequest(
                        messages=[UserMessage(content="Load sales_data.csv")]
                    ),
                )
            )

        assert len(results) >= 1
        response = ChatCompletionResponse.model_validate(results[0].payload)

        trace = response.choices[0].provider_specific_fields.get("react_trace", [])
        assert len(trace) >= 1

        load_step = trace[0]
        assert load_step["action"] == "load_file"
        assert load_step["action_input"]["filename"] == "sales_data.csv"
        assert load_step["action_input"]["dataset_name"] == "sales"
        # Verify observation contains success info
        assert "num_rows" in load_step["observation"] or "sales" in load_step["observation"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
