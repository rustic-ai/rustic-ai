"""
Integration tests for ReActAgent with Skills using a guild-based approach.

These tests initialize a guild from YAML, add the ReActAgent with a SkillToolset,
and use a ProbeAgent to verify behavior.
"""

import os
from pathlib import Path
import tempfile
import time
from typing import List

from flaky import flaky
from pydantic import BaseModel
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import AgentSpec, DependencySpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver
from rustic_ai.llm_agent.react import (
    ReActAgent,
    ReActAgentConfig,
    ReActToolset,
)
from rustic_ai.skills.toolset import SkillToolset

# ---------------------------------------------------------------------------
# Test Toolsets (simple in-memory for testing)
# ---------------------------------------------------------------------------


class CalculateParams(BaseModel):
    """Parameters for the calculate tool."""

    expression: str
    """A simple arithmetic expression to evaluate (e.g., '2 + 2', '10 * 5')."""


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

    def execute(self, tool_name: str, args: BaseModel) -> str:
        if tool_name == "calculate":
            assert isinstance(args, CalculateParams)
            try:
                # Safely evaluate arithmetic expressions
                allowed_chars = set("0123456789+-*/(). ")
                expression = args.expression
                if not all(c in allowed_chars for c in expression):
                    return f"Error: Expression contains invalid characters: {args.expression}"
                result = eval(expression)  # noqa: S307
                return str(result)
            except Exception as e:
                return f"Error evaluating expression: {e}"
        raise ValueError(f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_skill_dir():
    """Create a temporary skill directory with a calculator skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_path = Path(tmpdir) / "calculator"
        skill_path.mkdir()

        # Create SKILL.md
        (skill_path / "SKILL.md").write_text(
            """---
name: calculator
description: A skill for performing mathematical calculations
---

# Calculator Skill

This skill provides mathematical calculation capabilities.
Use the calculate script to evaluate arithmetic expressions.

## Usage
- Provide arithmetic expressions like "2 + 2", "10 * 5", etc.
- Supports basic operations: +, -, *, /, **, (, )
"""
        )

        # Create scripts directory with calculator script
        scripts_dir = skill_path / "scripts"
        scripts_dir.mkdir()

        (scripts_dir / "calculate.py").write_text(
            '''"""Evaluate mathematical expressions safely."""
import json
import os
import sys

# Get arguments from environment
args_json = os.environ.get("SKILL_ARGS", "{}")
args = json.loads(args_json)

expression = args.get("expression", "")

# Validate expression contains only allowed characters
allowed_chars = set("0123456789+-*/(). ")
if not all(c in allowed_chars for c in expression):
    print(f"Error: Expression contains invalid characters")
    sys.exit(1)

try:
    result = eval(expression)
    print(result)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
'''
        )

        yield skill_path


@pytest.fixture
def skill_toolset(temp_skill_dir):
    """Create a SkillToolset from the temporary skill directory."""
    return SkillToolset.from_path(temp_skill_dir, tool_prefix="calc_")


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
class TestReActAgentGuildIntegration:
    """Integration tests for ReActAgent within a guild using ProbeAgent."""

    @flaky(max_runs=3, min_passes=1)
    def test_react_agent_with_calculator_toolset_in_guild(self, probe_spec, org_id, temp_skill_dir):
        """
        Test ReActAgent with a calculator toolset in a full guild setup.
        Uses ProbeAgent to send requests and verify responses.
        """
        guild_id = "test_react_skill_guild"

        # Set up dependency map with LLM resolver
        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-5-nano"},
            ),
        }

        # Create SkillToolset from the temp skill directory
        skill_toolset = SkillToolset.from_path(temp_skill_dir, tool_prefix="calc_")

        # Build the ReAct agent spec with the skill toolset
        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations using skills")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=skill_toolset,
                )
            )
            .build_spec()
        )

        # Build and launch the guild
        guild_builder = (
            GuildBuilder(guild_id, "ReAct Test Guild", "Guild to test ReActAgent with skills")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)

        # Add probe agent to the guild
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        try:
            # Send a calculation request via the probe agent
            probe_agent.publish_dict(
                topic="default_topic",
                payload={"messages": [{"role": "user", "content": "What is 15 multiplied by 7?"}]},
                format=ChatCompletionRequest,
            )

            # Wait for processing
            time.sleep(5.0)

            # Verify the response
            messages = probe_agent.get_messages()
            assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

            # Find the ChatCompletionResponse message
            react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
            assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

            response = ChatCompletionResponse.model_validate(react_responses[0].payload)
            answer = response.choices[0].message.content or ""
            assert "105" in answer, f"Answer should contain 105: {answer}"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()

    @flaky(max_runs=3, min_passes=1)
    def test_react_agent_with_simple_toolset_in_guild(self, probe_spec, org_id):
        """
        Test ReActAgent with a simple in-memory calculator toolset in a guild.
        """
        guild_id = "test_react_simple_guild"

        # Set up dependency map with LLM resolver
        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-5-nano"},
            ),
        }

        # Build the ReAct agent spec with the simple calculator toolset
        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        # Build and launch the guild
        guild_builder = (
            GuildBuilder(guild_id, "ReAct Test Guild", "Guild to test ReActAgent")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)

        # Add probe agent to the guild
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        try:
            # Send a calculation request via the probe agent
            probe_agent.publish_dict(
                topic="default_topic",
                payload={"messages": [{"role": "user", "content": "Calculate 25 times 4 plus 17"}]},
                format=ChatCompletionRequest,
            )

            # Wait for processing
            time.sleep(5.0)

            # Verify the response
            messages = probe_agent.get_messages()
            assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

            # Find the ChatCompletionResponse message
            react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
            assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

            response = ChatCompletionResponse.model_validate(react_responses[0].payload)
            answer = response.choices[0].message.content or ""
            # 25 * 4 + 17 = 100 + 17 = 117
            assert "117" in answer, f"Answer should contain 117: {answer}"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()

    @flaky(max_runs=3, min_passes=1)
    def test_react_agent_from_yaml_guild_spec(self, probe_spec, org_id, temp_skill_dir):
        """
        Test ReActAgent initialized from a YAML guild specification.
        """
        # Create a temporary YAML file with the guild spec
        yaml_content = f"""id: react_yaml_test_guild
name: ReAct YAML Test Guild
description: Guild to test ReActAgent from YAML configuration
properties: {{}}
agents:
  - class_name: rustic_ai.llm_agent.react.ReActAgent
    id: react_agent
    name: ReAct Agent
    description: A ReAct agent that uses skills to solve problems
    additional_topics: []
    properties:
      model: gpt-5-nano
      max_iterations: 5
      temperature: 0.7
      toolset:
        kind: rustic_ai.skills.toolset.SkillToolset
        skill_paths:
          - {temp_skill_dir}
        tool_prefix: calc_
        execution_config:
          timeout_seconds: 30
          capture_stderr: true
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as yaml_file:
            yaml_file.write(yaml_content)
            yaml_path = yaml_file.name

        try:
            # Set up dependency map with LLM resolver
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            # Build guild from YAML
            guild_builder = GuildBuilder.from_yaml_file(yaml_path)
            guild_builder.set_dependency_map(dep_map)

            guild = guild_builder.launch(org_id)

            # Add probe agent to the guild
            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # Send a calculation request via the probe agent
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "What is 8 plus 12?"}]},
                    format=ChatCompletionRequest,
                )

                # Wait for processing
                time.sleep(5.0)

                # Verify the response
                messages = probe_agent.get_messages()
                assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

                # Find the ChatCompletionResponse message
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                # 8 + 12 = 20
                assert "20" in answer, f"Answer should contain 20: {answer}"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            # Clean up the temporary YAML file
            os.unlink(yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_react_agent_multi_step_reasoning(self, probe_spec, org_id):
        """
        Test ReActAgent with a multi-step reasoning problem in a guild.
        """
        guild_id = "test_react_multistep_guild"

        # Set up dependency map with LLM resolver
        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-5-nano"},
            ),
        }

        # Build the ReAct agent spec with the calculator toolset
        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent that can perform calculations")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=10,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        # Build and launch the guild
        guild_builder = (
            GuildBuilder(guild_id, "ReAct Test Guild", "Guild to test ReActAgent")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)

        # Add probe agent to the guild
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        try:
            # Send a multi-step calculation request
            probe_agent.publish_dict(
                topic="default_topic",
                payload={
                    "messages": [{
                        "role": "user",
                        "content": (
                            "I have 3 boxes with 5 apples each. "
                            "If I add 7 more apples, then give away half of all apples, "
                            "how many apples do I have left?"
                        )
                    }]
                },
                format=ChatCompletionRequest,
            )

            # Wait for processing (may need multiple iterations)
            time.sleep(8.0)

            # Verify the response
            messages = probe_agent.get_messages()
            assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

            # Find the ChatCompletionResponse message
            react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
            assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

            response = ChatCompletionResponse.model_validate(react_responses[0].payload)
            answer = response.choices[0].message.content or ""
            # 3 * 5 = 15, 15 + 7 = 22, 22 / 2 = 11
            assert "11" in answer, f"Answer should contain 11: {answer}"
            # Should have taken multiple steps
            iterations = response.choices[0].provider_specific_fields.get("iterations", 0)
            assert iterations >= 1, "Should have taken at least 1 iteration"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()

    @flaky(max_runs=3, min_passes=1)
    def test_react_agent_no_tool_needed(self, probe_spec, org_id):
        """
        Test ReActAgent when no tool is needed - should respond directly.
        """
        guild_id = "test_react_direct_guild"

        # Set up dependency map with LLM resolver
        dep_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "gpt-5-nano"},
            ),
        }

        # Build the ReAct agent spec with the calculator toolset
        react_agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_agent")
            .set_name("ReAct Agent")
            .set_description("A ReAct agent")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=CalculatorToolset(),
                )
            )
            .build_spec()
        )

        # Build and launch the guild
        guild_builder = (
            GuildBuilder(guild_id, "ReAct Test Guild", "Guild to test ReActAgent")
            .add_agent_spec(react_agent_spec)
            .set_dependency_map(dep_map)
        )

        guild = guild_builder.launch(org_id)

        # Add probe agent to the guild
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        try:
            # Send a query that doesn't need calculation
            probe_agent.publish_dict(
                topic="default_topic",
                payload={"messages": [{"role": "user", "content": "Say 'Hello, World!' exactly as written."}]},
                format=ChatCompletionRequest,
            )

            # Wait for processing
            time.sleep(5.0)

            # Verify the response
            messages = probe_agent.get_messages()
            assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

            # Find the ChatCompletionResponse message
            react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
            assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

            response = ChatCompletionResponse.model_validate(react_responses[0].payload)
            answer = response.choices[0].message.content or ""
            assert "Hello, World!" in answer, f"Answer should contain greeting: {answer}"
            # Should have no tool calls
            assert len(response.choices[0].provider_specific_fields.get("react_trace", [])) == 0, "Should not have used any tools"

        finally:
            probe_agent.clear_messages()
            guild.shutdown()
