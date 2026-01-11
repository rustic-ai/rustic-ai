import os
from pathlib import Path
import tempfile

import pytest
import yaml

from rustic_ai.core.guild.builders import GuildBuilder
from rustic_ai.core.messaging.core.message import FunctionalTransformer, RoutingSlip
from rustic_ai.core.utils.yaml_utils import load_yaml


class TestModularGuildLoading:
    def test_load_modular_guild(self):
        """
        Verify that a guild with !include and !code tags is loaded correctly.
        """
        # Path to the modular guild resource
        base_path = os.path.dirname(__file__)
        guild_yaml_path = os.path.join(base_path, "resources/modular_guild/guild.yaml")

        # Load the guild using the builder
        builder = GuildBuilder.from_yaml_file(guild_yaml_path)
        spec = builder.build_spec()

        # Verify Guild Properties
        assert spec.id == "modular_guild_id"
        assert spec.name == "modular_guild_name"
        assert spec.description == "description for modular_guild"

        # Verify Agents loaded via !include
        assert len(spec.agents) == 1
        agent = spec.agents[0]
        assert agent.name == "Modular Agent"
        assert agent.description == "A simple agent defined in a separate file"
        assert agent.class_name == "rustic_ai.core.agents.eip.basic_wiring_agent.BasicWiringAgent"

        # Verify Routes loaded via !include and script loaded via !code
        assert spec.routes is not None
        assert isinstance(spec.routes, RoutingSlip)
        assert len(spec.routes.steps) == 1

        step = spec.routes.steps[0]
        assert step.agent.name == "Modular Agent"
        assert isinstance(step.transformer, FunctionalTransformer)

        # Verify the content of the script loaded via !code
        expected_script = '({"topics": payload.routing_key})'
        assert step.transformer.handler.strip() == expected_script.strip()


class TestModularGuildErrorHandling:
    """Test error scenarios for modular guild loading."""

    def test_missing_include_file(self):
        """Test that missing include files raise FileNotFoundError with context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            guild_file = Path(tmpdir) / "guild.yaml"
            guild_file.write_text("""
id: test_guild
name: Test Guild
agents:
  - !include missing_agent.yaml
""")

            with pytest.raises(FileNotFoundError) as exc_info:
                GuildBuilder.from_yaml_file(str(guild_file))

            # Verify error message includes context
            assert "missing_agent.yaml" in str(exc_info.value)
            assert "guild.yaml" in str(exc_info.value) or tmpdir in str(exc_info.value)

    def test_missing_code_file(self):
        """Test that missing code files raise FileNotFoundError with context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            guild_file = Path(tmpdir) / "guild.yaml"
            guild_file.write_text("""
id: test_guild
name: Test Guild
agents:
  - id: agent1
    name: Agent 1
    class_name: rustic_ai.core.agents.eip.basic_wiring_agent.BasicWiringAgent
    properties:
      prompt: !code missing_prompt.md
""")

            with pytest.raises(FileNotFoundError) as exc_info:
                GuildBuilder.from_yaml_file(str(guild_file))

            # Verify error message includes context
            assert "missing_prompt.md" in str(exc_info.value)

    def test_circular_include_detection(self):
        """Test that circular includes are detected and reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create circular reference: a.yaml -> b.yaml -> a.yaml
            a_file = Path(tmpdir) / "a.yaml"
            b_file = Path(tmpdir) / "b.yaml"

            a_file.write_text("""
id: agent_a
name: Agent A
nested: !include b.yaml
""")

            b_file.write_text("""
id: agent_b
name: Agent B
nested: !include a.yaml
""")

            with pytest.raises(ValueError) as exc_info:
                with open(a_file) as f:
                    load_yaml(f, base_dir=tmpdir)

            # Verify error message shows the circular chain
            assert "Circular" in str(exc_info.value)
            assert "a.yaml" in str(exc_info.value)
            assert "b.yaml" in str(exc_info.value)

    def test_invalid_yaml_syntax_in_included_file(self):
        """Test that invalid YAML syntax in included files is reported clearly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main_file = Path(tmpdir) / "main.yaml"
            bad_file = Path(tmpdir) / "bad.yaml"

            main_file.write_text("""
id: test_guild
agents: !include bad.yaml
""")

            bad_file.write_text("""
this is: not
  valid: yaml:
    syntax
      - here
""")

            with pytest.raises(yaml.YAMLError):
                with open(main_file) as f:
                    load_yaml(f, base_dir=tmpdir)

    def test_include_non_yaml_file_raises_error(self):
        """Test that !include on non-YAML files raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main_file = Path(tmpdir) / "main.yaml"
            txt_file = Path(tmpdir) / "data.txt"

            main_file.write_text("""
id: test_guild
data: !include data.txt
""")

            txt_file.write_text("This is plain text")

            with pytest.raises(ValueError) as exc_info:
                with open(main_file) as f:
                    load_yaml(f, base_dir=tmpdir)

            # Verify error message guides user to use !code
            assert "!include only supports" in str(exc_info.value)
            assert "!code" in str(exc_info.value)
            assert ".txt" in str(exc_info.value)

    def test_code_tag_works_with_any_extension(self):
        """Test that !code works with any text file extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main_file = Path(tmpdir) / "main.yaml"
            txt_file = Path(tmpdir) / "data.txt"
            md_file = Path(tmpdir) / "prompt.md"
            json_file = Path(tmpdir) / "config.json"

            main_file.write_text("""
id: test_guild
txt_content: !code data.txt
md_content: !code prompt.md
json_content: !code config.json
""")

            txt_file.write_text("Plain text content")
            md_file.write_text("# Markdown content")
            json_file.write_text('{"key": "value"}')

            with open(main_file) as f:
                data = load_yaml(f, base_dir=tmpdir)

            assert data["txt_content"] == "Plain text content"
            assert data["md_content"] == "# Markdown content"
            assert data["json_content"] == '{"key": "value"}'

    def test_string_content_loading(self):
        """Test that load_yaml handles string content properly."""
        yaml_content = """
id: test_guild
name: Test Guild
agents:
  - id: agent1
    name: Agent 1
"""

        # Should work with string content
        data = load_yaml(yaml_content)
        assert data["id"] == "test_guild"
        assert data["name"] == "Test Guild"

    def test_string_content_with_base_dir(self):
        """Test that string content respects base_dir for includes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_file = Path(tmpdir) / "agent.yaml"
            agent_file.write_text("""
id: agent1
name: Agent 1
class_name: rustic_ai.core.agents.eip.basic_wiring_agent.BasicWiringAgent
""")

            yaml_content = """
id: test_guild
agents:
  - !include agent.yaml
"""

            # String content with explicit base_dir should resolve includes
            data = load_yaml(yaml_content, base_dir=tmpdir)
            assert data["id"] == "test_guild"
            assert data["agents"][0]["id"] == "agent1"

    def test_nested_includes(self):
        """Test that nested includes work correctly (A includes B includes C)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            a_file = Path(tmpdir) / "a.yaml"
            b_file = Path(tmpdir) / "b.yaml"
            c_file = Path(tmpdir) / "c.yaml"

            a_file.write_text("""
id: a
nested: !include b.yaml
""")

            b_file.write_text("""
id: b
nested: !include c.yaml
""")

            c_file.write_text("""
id: c
value: deepest
""")

            with open(a_file) as f:
                data = load_yaml(f, base_dir=tmpdir)

            assert data["id"] == "a"
            assert data["nested"]["id"] == "b"
            assert data["nested"]["nested"]["id"] == "c"
            assert data["nested"]["nested"]["value"] == "deepest"

    def test_relative_paths_in_includes(self):
        """Test that relative paths work correctly in nested directory structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            agents_dir = base / "agents"
            prompts_dir = base / "prompts"

            agents_dir.mkdir()
            prompts_dir.mkdir()

            main_file = base / "guild.yaml"
            agent_file = agents_dir / "agent.yaml"
            prompt_file = prompts_dir / "system.md"

            main_file.write_text("""
id: test_guild
agents:
  - !include agents/agent.yaml
""")

            agent_file.write_text("""
id: agent1
name: Agent 1
class_name: rustic_ai.core.agents.eip.basic_wiring_agent.BasicWiringAgent
properties:
  prompt: !code ../prompts/system.md
""")

            prompt_file.write_text("System prompt content")

            with open(main_file) as f:
                data = load_yaml(f, base_dir=base)

            assert data["agents"][0]["properties"]["prompt"] == "System prompt content"


if __name__ == "__main__":
    pytest.main([__file__])
