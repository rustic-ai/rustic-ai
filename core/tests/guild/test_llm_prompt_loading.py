"""Test that !code tag works for loading LLM agent prompts from external files."""

from pathlib import Path

import pytest

from rustic_ai.core.guild.builders import GuildBuilder


class TestLLMAgentPromptLoading:
    """Test loading LLM agent prompts from external files using !code tag."""

    @pytest.fixture
    def resources_dir(self):
        """Path to test resources directory."""
        return Path(__file__).parent.parent / "resources" / "modular_guild"

    def test_load_llm_agent_with_code_tag_prompt(self, resources_dir):
        """Test that LLMAgent can load system prompt from .md file using !code tag."""
        guild_yaml = resources_dir / "research_guild.yaml"

        # Build guild from YAML with !code tag
        guild_builder = GuildBuilder.from_yaml_file(str(guild_yaml))

        # Verify the guild spec was loaded
        guild_spec = guild_builder.build_spec()

        # Check that we have the agent
        assert len(guild_spec.agents) == 1
        agent_spec = guild_spec.agents[0]

        # Verify agent configuration
        assert agent_spec.name == "Research Assistant"
        assert agent_spec.class_name == "rustic_ai.llm_agent.llm_agent.LLMAgent"

        # Check that properties contain the prompt
        assert hasattr(agent_spec.properties, "default_system_prompt")
        prompt = agent_spec.properties.default_system_prompt

        # Verify the prompt content was loaded from the .mmd file
        assert isinstance(prompt, str)
        assert "Research Assistant System Prompt" in prompt
        assert "Your Capabilities" in prompt
        assert "Guidelines" in prompt
        assert "Response Format" in prompt

    def test_code_tag_loads_file_content_as_string(self, resources_dir):
        """Test that !code tag loads the entire file content as a string."""
        guild_yaml = resources_dir / "research_guild.yaml"
        guild_builder = GuildBuilder.from_yaml_file(str(guild_yaml))
        guild_spec = guild_builder.build_spec()

        agent_spec = guild_spec.agents[0]
        prompt = agent_spec.properties.default_system_prompt

        # Verify it's a multi-line string with markdown formatting
        assert prompt.count("\n") > 10  # Has multiple lines
        assert "##" in prompt  # Has markdown headers
        assert "**" in prompt  # Has bold formatting
        assert "1." in prompt or "2." in prompt  # Has numbered lists

    def test_prompt_file_path_relative_to_yaml(self, resources_dir):
        """Test that !code tag resolves paths relative to the YAML file location."""
        # The path in llm_agent_example.yaml is "prompts/research_assistant.md"
        # This should be resolved relative to the directory containing llm_agent_example.yaml

        guild_yaml = resources_dir / "research_guild.yaml"
        guild_builder = GuildBuilder.from_yaml_file(str(guild_yaml))
        guild_spec = guild_builder.build_spec()

        # Should successfully load without file not found errors
        agent_spec = guild_spec.agents[0]
        assert hasattr(agent_spec.properties, "default_system_prompt")
        assert len(agent_spec.properties.default_system_prompt) > 100
