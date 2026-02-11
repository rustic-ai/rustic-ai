"""
Test suite for loading and validating the test_react_guild.yaml configuration.

This module contains comprehensive tests that load the checked-in YAML file
and verify that the guild configuration is correct and functional.
"""

import os
from pathlib import Path
import tempfile
import time

from flaky import flaky
import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver
from rustic_ai.llm_agent.react.toolset import CompositeToolset
from rustic_ai.skills.toolset import MarketplaceSkillToolset, SkillToolset


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests (set SKIP_EXPENSIVE_TESTS=false to run)",
)
@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ,
    reason="OPENAI_API_KEY not set",
)
class TestReActGuildYAML:
    """Test suite for the test_react_guild.yaml configuration file."""

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_file_exists(self):
        """Verify that the test_react_guild.yaml file exists."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        assert yaml_path.exists(), f"YAML file not found at {yaml_path}"
        assert yaml_path.is_file(), f"Path exists but is not a file: {yaml_path}"

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_loads_successfully(self, temp_skill_dir):
        """Test that the YAML file can be loaded without errors."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"

        # Create a temporary copy with the correct skill path
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            # Should not raise any exceptions
            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)

            # Verify basic structure
            assert guild_builder is not None
            assert hasattr(guild_builder, "guild_spec_dict")
            assert "id" in guild_builder.guild_spec_dict

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_structure(self, org_id, temp_skill_dir):
        """Test that the guild structure from YAML is correct."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            try:
                # Verify guild properties from YAML
                assert guild.id == "react_skill_guild", f"Guild ID mismatch: {guild.id}"
                assert guild.name == "ReAct Skill Test Guild", f"Guild name mismatch: {guild.name}"
                assert (
                    guild.description == "Guild for testing ReActAgent with CompositeToolset combining local and marketplace skills"
                ), f"Guild description mismatch: {guild.description}"

                # Verify agents are registered
                assert guild.get_agent_count() >= 1, "Guild should have at least one agent"

                # Verify the agent spec is registered
                agent_specs = guild._agents_by_id
                assert "react_agent" in agent_specs, "react_agent should be registered"

                agent_spec = agent_specs["react_agent"]
                assert agent_spec.id == "react_agent", f"Agent ID mismatch: {agent_spec.id}"
                assert agent_spec.name == "ReAct Agent", f"Agent name mismatch: {agent_spec.name}"

            finally:
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_agent_configuration(self, org_id, temp_skill_dir):
        """Test that the ReActAgent configuration from YAML is correct."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            try:
                # Get the agent spec
                agent_specs = guild._agents_by_id
                assert "react_agent" in agent_specs, "react_agent should be registered"

                agent_spec = agent_specs["react_agent"]

                # Verify configuration from YAML - properties are stored in the agent spec
                properties = agent_spec.properties
                assert properties is not None, "Agent should have properties"

                # Properties is a Pydantic model (ReActAgentConfig), access attributes directly
                assert properties.model == "gpt-5-nano", f"Model should be gpt-5-nano: {properties.model}"
                assert properties.max_iterations == 10, f"Max iterations should be 10: {properties.max_iterations}"
                assert properties.temperature == 0.7, f"Temperature should be 0.7: {properties.temperature}"

            finally:
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_toolset_configuration(self, org_id, temp_skill_dir):
        """Test that the SkillToolset configuration from YAML is properly loaded."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            try:
                # Get the agent spec
                agent_specs = guild._agents_by_id
                assert "react_agent" in agent_specs, "react_agent should be registered"

                agent_spec = agent_specs["react_agent"]

                # Verify toolset configuration - properties are stored in the agent spec
                properties = agent_spec.properties
                assert properties is not None, "Agent should have properties"

                # Verify toolset configuration - access as Pydantic model attributes
                toolset = properties.toolset
                assert toolset is not None, "Toolset should be configured"
                assert isinstance(toolset, CompositeToolset), f"Toolset should be CompositeToolset: {type(toolset)}"

                # Verify CompositeToolset has 2 child toolsets
                assert len(toolset.toolsets) == 2, f"CompositeToolset should have 2 toolsets: {len(toolset.toolsets)}"

                # Verify first toolset is SkillToolset (local calculator)
                skill_toolset = toolset.toolsets[0]
                assert isinstance(skill_toolset, SkillToolset), f"First toolset should be SkillToolset: {type(skill_toolset)}"
                assert skill_toolset.tool_prefix == "calc_", f"Tool prefix should be 'calc_': {skill_toolset.tool_prefix}"

                # Verify execution config on SkillToolset
                exec_config = skill_toolset.execution_config
                assert exec_config is not None, "Execution config should be present"
                assert exec_config.timeout_seconds == 30, f"Timeout should be 30: {exec_config.timeout_seconds}"
                assert exec_config.capture_stderr is True, f"Capture stderr should be True: {exec_config.capture_stderr}"

                # Verify skill_paths are configured
                skill_paths = skill_toolset.skill_paths
                assert skill_paths is not None and len(skill_paths) > 0, "Skill paths should be configured"

                # Verify second toolset is MarketplaceSkillToolset (pdf skill)
                marketplace_toolset = toolset.toolsets[1]
                assert isinstance(
                    marketplace_toolset, MarketplaceSkillToolset
                ), f"Second toolset should be MarketplaceSkillToolset: {type(marketplace_toolset)}"
                assert marketplace_toolset.source == "anthropic", f"Source should be 'anthropic': {marketplace_toolset.source}"
                assert "pdf" in marketplace_toolset.skill_names, f"Should include 'pdf' skill: {marketplace_toolset.skill_names}"

            finally:
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_basic_calculation(self, probe_spec, org_id, temp_skill_dir):
        """Test that the guild loaded from YAML can perform basic calculations."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # Send a basic calculation request
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "What is 42 multiplied by 3?"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"

                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                assert "126" in answer, f"Answer should contain 126: {answer}"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_complex_calculation(self, probe_spec, org_id, temp_skill_dir):
        """Test that the guild can handle complex multi-step calculations."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # Send a complex calculation request
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "Calculate (10 + 5) * 2 - 3"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                # (10 + 5) * 2 - 3 = 15 * 2 - 3 = 30 - 3 = 27
                assert "27" in answer, f"Answer should contain 27: {answer}"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_max_iterations_respected(self, probe_spec, org_id, temp_skill_dir):
        """Test that max_iterations configuration from YAML is respected."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # This should work within 10 iterations (as per YAML config)
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "Calculate 100 + 200 + 300"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                iterations = response.choices[0].provider_specific_fields.get("iterations", 0)
                assert iterations <= 10, f"Should complete within 10 iterations: {iterations}"
                assert "600" in answer, f"Answer should contain 600: {answer}"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_tool_prefix_usage(self, probe_spec, org_id, temp_skill_dir):
        """Test that the tool_prefix from YAML is correctly applied to tool calls."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "What is 7 times 8?"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                assert "56" in answer, f"Answer should contain 56: {answer}"

                # Verify the tool was called with the correct prefix
                react_trace = response.choices[0].provider_specific_fields.get("react_trace", [])
                if len(react_trace) > 0:
                    # Check that the tool name uses the correct prefix
                    for step in react_trace:
                        if step.get("action"):
                            assert step["action"].startswith("calc_"), (
                                f"Tool name should start with 'calc_': {step['action']}"
                            )

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_error_handling(self, probe_spec, org_id, temp_skill_dir):
        """Test that the guild handles invalid expressions gracefully."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # Test with invalid expression (should be handled gracefully)
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "Calculate abc + xyz"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                # The agent should still respond even if the calculation fails
                assert answer, "Should have an answer even on error"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)

    @flaky(max_runs=3, min_passes=1)
    def test_yaml_guild_multiple_operations(self, probe_spec, org_id, temp_skill_dir):
        """Test that the guild can handle multiple sequential operations."""
        yaml_path = Path(__file__).parent / "test_react_guild.yaml"
        yaml_content = yaml_path.read_text()
        yaml_content = yaml_content.replace("/tmp/test_skills/calculator", str(temp_skill_dir))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_yaml:
            temp_yaml.write(yaml_content)
            temp_yaml_path = temp_yaml.name

        try:
            dep_map = {
                "llm": DependencySpec(
                    class_name=LiteLLMResolver.get_qualified_class_name(),
                    properties={"model": "gpt-5-nano"},
                ),
            }

            guild_builder = GuildBuilder.from_yaml_file(temp_yaml_path)
            guild_builder.set_dependency_map(dep_map)
            guild = guild_builder.launch(org_id)

            probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

            try:
                # Test 1
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "What is 10 + 20?"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                assert "30" in answer, f"Answer should contain 30: {answer}"

                # Test 2
                probe_agent.clear_messages()
                probe_agent.publish_dict(
                    topic="default_topic",
                    payload={"messages": [{"role": "user", "content": "What is 50 - 15?"}]},
                    format=ChatCompletionRequest,
                )

                time.sleep(5.0)

                messages = probe_agent.get_messages()
                react_responses = [m for m in messages if m.format == get_qualified_class_name(ChatCompletionResponse)]
                assert len(react_responses) >= 1, "Expected at least one ChatCompletionResponse"

                response = ChatCompletionResponse.model_validate(react_responses[0].payload)
                answer = response.choices[0].message.content or ""
                assert "35" in answer, f"Answer should contain 35: {answer}"

            finally:
                probe_agent.clear_messages()
                guild.shutdown()

        finally:
            os.unlink(temp_yaml_path)
