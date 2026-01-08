"""
Integration tests for ReActAgent using actual LLM calls.

These tests make real API calls and are skipped by default.
Set OPENAI_API_KEY environment variable and unset SKIP_EXPENSIVE_TESTS to run.
"""

import os
from typing import Any, List

from flaky import flaky
from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.react import (
    CompositeToolset,
    ReActAgent,
    ReActAgentConfig,
    ReActRequest,
    ReActResponse,
    ReActToolset,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing

# ---------------------------------------------------------------------------
# Tool Parameter Models
# ---------------------------------------------------------------------------


class CalculateParams(BaseModel):
    """Parameters for the calculate tool."""

    expression: str
    """A simple arithmetic expression to evaluate (e.g., '2 + 2', '10 * 5')."""


class GetWeatherParams(BaseModel):
    """Parameters for the get_weather tool."""

    city: str
    """The name of the city to get weather for."""


class SearchParams(BaseModel):
    """Parameters for the search tool."""

    query: str
    """The search query."""


# ---------------------------------------------------------------------------
# Test Toolsets
# ---------------------------------------------------------------------------


class CalculatorToolset(ReActToolset):
    """A simple calculator toolset that evaluates arithmetic expressions."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="calculate",
                description="Evaluate a simple arithmetic expression. "
                "Supports basic operations: +, -, *, /, **, (, ). "
                "Example: '2 + 2' returns '4', '10 * 5 + 3' returns '53'.",
                parameter_class=CalculateParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "calculate":
            assert isinstance(args, CalculateParams)
            try:
                # Safely evaluate arithmetic expressions
                # Only allow basic math operations
                allowed_chars = set("0123456789+-*/(). ")
                expression = args.expression
                if not all(c in allowed_chars for c in expression):
                    return f"Error: Expression contains invalid characters. Only arithmetic operations are allowed {args.expression}."
                result = eval(expression)  # noqa: S307
                return str(result)
            except Exception as e:
                return f"Error evaluating expression: {e}"
        raise ValueError(f"Unknown tool: {tool_name}")


class MockWeatherToolset(ReActToolset):
    """A mock weather toolset that returns predefined weather data."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="get_weather",
                description="Get the current weather for a city. Returns temperature and conditions.",
                parameter_class=GetWeatherParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "get_weather":
            assert isinstance(args, GetWeatherParams)
            # Return mock weather data based on city
            weather_data = {
                "paris": "72°F (22°C), Partly Cloudy",
                "london": "59°F (15°C), Rainy",
                "tokyo": "68°F (20°C), Clear",
                "new york": "65°F (18°C), Sunny",
                "sydney": "77°F (25°C), Sunny",
            }
            city_lower = args.city.lower()
            for city_name, weather in weather_data.items():
                if city_name in city_lower:
                    return f"Weather in {args.city}: {weather}"
            return f"Weather in {args.city}: 70°F (21°C), Clear (default)"
        raise ValueError(f"Unknown tool: {tool_name}")


class MockSearchToolset(ReActToolset):
    """A mock search toolset that returns predefined search results."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="search",
                description="Search for information on the web. Returns relevant search results.",
                parameter_class=SearchParams,
            )
        ]

    def execute(self, tool_name: str, args: Any) -> str:
        if tool_name == "search":
            assert isinstance(args, SearchParams)
            query_lower = args.query.lower()

            # Provide relevant mock search results
            if "eiffel tower" in query_lower:
                return "The Eiffel Tower is located in Paris, France. It was built in 1889."
            elif "capital" in query_lower and "france" in query_lower:
                return "Paris is the capital of France."
            elif "population" in query_lower and "tokyo" in query_lower:
                return "Tokyo has a population of approximately 14 million people."
            elif "python" in query_lower:
                return "Python is a high-level programming language created by Guido van Rossum."
            else:
                return f"Search results for '{args.query}': No specific information found."

        raise ValueError(f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# Integration Test Class
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests (set SKIP_EXPENSIVE_TESTS=false to run)",
)
@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ,
    reason="OPENAI_API_KEY not set",
)
class TestReActAgentIntegration:
    """Integration tests for ReActAgent using actual LLM calls."""

    @flaky(max_runs=3, min_passes=1)
    def test_simple_calculation(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with a simple calculation query."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="What is 15 multiplied by 7?"),
            )
        )

        assert len(results) > 0
        result = results[0]
        assert result.format == get_qualified_class_name(ReActResponse)

        response = ReActResponse.model_validate(result.payload)
        assert response.success is True
        assert "105" in response.answer
        # Should have at least one tool call in the trace
        assert len(response.trace) >= 1
        assert response.trace[0].action == "calculate"

    def test_multi_step_calculation(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with a multi-step calculation problem."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=10,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(
                    query="I have 3 apples and 4 oranges. If I get 2 more apples and 3 more oranges, "
                    "then give away half of all my fruits, how many fruits do I have left?"
                ),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        # 3 + 4 + 2 + 3 = 12, 12 / 2 = 6
        assert "6" in response.answer
        # Note: LLMs may solve simple arithmetic without tools, so we don't assert tool usage here.
        # The important thing is that the answer is correct.

    def test_weather_query(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with a weather query."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Weather Agent")
            .set_description("A ReAct agent that can check weather")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=5,
                    toolset=MockWeatherToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="What's the weather like in Paris today?"),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        # Should mention Paris and weather info
        assert "paris" in response.answer.lower() or "72" in response.answer or "cloudy" in response.answer.lower()
        assert len(response.trace) >= 1
        assert response.trace[0].action == "get_weather"

    def test_composite_toolset(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with multiple tools via CompositeToolset."""
        composite_toolset = CompositeToolset(
            toolsets=[
                CalculatorToolset(),
                MockSearchToolset(),
            ]
        )

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Multi-Tool Agent")
            .set_description("A ReAct agent with multiple tools")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=10,
                    toolset=composite_toolset,
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="When was the Eiffel Tower built? Calculate how many years old it is as of 2025."),
                ReActRequest(query="When was the Eiffel Tower built? Calculate how many years old it is as of 2025."),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        # Should find info about Eiffel Tower (built 1889) and calculate age (2025 - 1889 = 136)
        assert "136" in response.answer or "1889" in response.answer
        # Should have used at least the search tool
        assert len(response.trace) >= 1
        tool_names_used = [step.action for step in response.trace]
        assert "search" in tool_names_used or "calculate" in tool_names_used

    def test_no_tool_needed(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent when no tool is needed for the query."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="Say 'Hello, World!' exactly as written."),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        assert "Hello, World!" in response.answer
        # Should complete without tool calls
        assert len(response.trace) == 0

    def test_context_in_request(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with additional context in the request."""
        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(
                    query="Calculate the total cost.",
                    context={
                        "items": [
                            {"name": "Apple", "price": 1.50, "quantity": 3},
                            {"name": "Banana", "price": 0.75, "quantity": 4},
                        ]
                    },
                ),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        # Total: 1.50 * 3 + 0.75 * 4 = 4.50 + 3.00 = 7.50
        assert "7.5" in response.answer or "7.50" in response.answer

    def test_custom_system_prompt(self, generator, build_message_from_payload, dependency_map):
        """Test ReActAgent with a custom system prompt."""
        custom_prompt = (
            "You are a helpful math tutor. When solving problems, "
            "explain your reasoning step by step. Use the calculate tool "
            "to verify your computations."
        )

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Math Tutor")
            .set_description("A ReAct agent that tutors math")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    system_prompt=custom_prompt,
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="What is 25% of 200?"),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        assert response.success is True
        assert "50" in response.answer

    def test_error_recovery(self, generator, build_message_from_payload, dependency_map):
        """Test that agent handles tool errors gracefully."""

        class FlakyToolset(ReActToolset):
            """A toolset that sometimes returns errors."""

            def get_toolspecs(self) -> List[ToolSpec]:
                return [
                    ToolSpec(
                        name="divide",
                        description="Divide two numbers",
                        parameter_class=CalculateParams,
                    )
                ]

            def execute(self, tool_name: str, args: Any) -> str:
                if tool_name == "divide":
                    assert isinstance(args, CalculateParams)
                    try:
                        result = eval(args.expression)  # noqa: S307
                        return str(result)
                    except ZeroDivisionError:
                        return "Error: Cannot divide by zero"
                raise ValueError(f"Unknown tool: {tool_name}")

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-4o-mini",
                    max_iterations=5,
                    toolset=FlakyToolset(),
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        # Ask to divide by zero - agent should handle the error
        agent._on_message(
            build_message_from_payload(
                generator,
                ReActRequest(query="What is 10 divided by 0?"),
            )
        )

        assert len(results) > 0
        response = ReActResponse.model_validate(results[0].payload)
        # The agent should still respond, even if the tool returned an error
        assert response.success is True
        # Response should mention the error or impossibility
        assert (
            "zero" in response.answer.lower()
            or "undefined" in response.answer.lower()
            or "cannot" in response.answer.lower()
            or "error" in response.answer.lower()
            or "impossible" in response.answer.lower()
        )
