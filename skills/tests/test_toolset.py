"""Tests for skills toolset."""

from pathlib import Path

import pytest

from rustic_ai.skills.executor import ExecutionConfig
from rustic_ai.skills.models import (
    SkillAsset,
    SkillDefinition,
    SkillMetadata,
    SkillReference,
    SkillScript,
)
from rustic_ai.skills.toolset import (
    MultiSkillToolset,
    ScriptToolParams,
    SkillToolset,
    create_skill_toolset,
)


class TestScriptToolParams:
    """Tests for ScriptToolParams model."""

    def test_empty_params(self):
        """Test creating empty params."""
        params = ScriptToolParams()
        assert params.args is None
        assert params.input_text is None

    def test_with_args(self):
        """Test params with args."""
        params = ScriptToolParams(args={"key": "value"})
        assert params.args == {"key": "value"}

    def test_with_input_text(self):
        """Test params with input text."""
        params = ScriptToolParams(input_text="some text")
        assert params.input_text == "some text"


class TestSkillToolset:
    """Tests for SkillToolset class."""

    def test_get_toolspecs(self, sample_skill_dir):
        """Test getting tool specifications from skill."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        specs = toolset.get_toolspecs()

        # Should have specs for each script
        assert len(specs) == 2

        names = [s.name for s in specs]
        # Default prefix is skill name + underscore
        assert "test_skill_process" in names
        assert "test_skill_setup" in names

    def test_get_toolspecs_no_prefix(self, sample_skill_dir):
        """Test getting tool specs without prefix."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="")
        specs = toolset.get_toolspecs()

        names = [s.name for s in specs]
        assert "process" in names
        assert "setup" in names

    def test_get_toolspecs_custom_prefix(self, sample_skill_dir):
        """Test getting tool specs with custom prefix."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="custom_")
        specs = toolset.get_toolspecs()

        names = [s.name for s in specs]
        assert "custom_process" in names
        assert "custom_setup" in names

    def test_execute_tool(self, sample_skill_dir):
        """Test executing a tool."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="")
        args = ScriptToolParams(args={"test": "value"})

        result = toolset.execute("process", args)

        assert "Processing" in result

    def test_execute_tool_with_prefix(self, sample_skill_dir):
        """Test executing a tool with prefix."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        args = ScriptToolParams(args={"test": "value"})

        result = toolset.execute("test_skill_process", args)

        assert "Processing" in result

    def test_execute_unknown_tool(self, sample_skill_dir):
        """Test error for unknown tool."""
        toolset = SkillToolset.from_path(sample_skill_dir)

        with pytest.raises(ValueError, match="Unknown tool"):
            toolset.execute("nonexistent", ScriptToolParams())

    def test_get_system_prompt_addition(self, sample_skill_dir):
        """Test getting system prompt addition."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        prompt = toolset.get_system_prompt_addition()

        # Should include skill name
        assert "test-skill" in prompt

        # Should include instructions
        assert "Test Skill" in prompt

        # Should include available scripts
        assert "Available Scripts" in prompt
        assert "process" in prompt.lower()
        assert "setup" in prompt.lower()

        # Should include references
        assert "Reference Documents" in prompt
        assert "api-docs.md" in prompt

    def test_load_reference(self, sample_skill_dir):
        """Test loading a reference document."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        content = toolset.load_reference("api-docs.md")

        assert content is not None
        assert "API Documentation" in content

    def test_load_reference_not_found(self, sample_skill_dir):
        """Test loading nonexistent reference."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        content = toolset.load_reference("nonexistent.md")

        assert content is None

    def test_get_asset_path(self, sample_skill_dir):
        """Test getting asset path."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        path = toolset.get_asset_path("template.json")

        assert path is not None
        assert path.exists()

    def test_get_asset_path_not_found(self, sample_skill_dir):
        """Test getting nonexistent asset path."""
        toolset = SkillToolset.from_path(sample_skill_dir)
        path = toolset.get_asset_path("nonexistent.json")

        assert path is None

    def test_from_path_with_execution_config(self, sample_skill_dir):
        """Test creating toolset with custom execution config."""
        config = ExecutionConfig(timeout_seconds=60)
        toolset = SkillToolset.from_path(sample_skill_dir, execution_config=config)

        assert toolset.execution_config.timeout_seconds == 60

    def test_toolset_serialization(self, sample_skill_dir):
        """Test that toolset can be serialized."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="")
        data = toolset.model_dump()

        assert "kind" in data
        assert "skill" in data
        assert "tool_prefix" in data

    def test_chat_tools(self, sample_skill_dir):
        """Test conversion to ChatCompletionTool format."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="")
        chat_tools = toolset.chat_tools

        assert len(chat_tools) == 2
        assert all(hasattr(t, "function") for t in chat_tools)

    def test_tool_names(self, sample_skill_dir):
        """Test tool_names property."""
        toolset = SkillToolset.from_path(sample_skill_dir, tool_prefix="")
        names = toolset.tool_names

        assert "process" in names
        assert "setup" in names


class TestMultiSkillToolset:
    """Tests for MultiSkillToolset class."""

    def test_combines_skills(self, temp_dir):
        """Test combining multiple skills."""
        # Create two skill directories
        skill1 = temp_dir / "skill1"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("""---
name: skill-one
description: First skill
---

Instructions for skill one.
""")
        scripts1 = skill1 / "scripts"
        scripts1.mkdir()
        (scripts1 / "action1.py").write_text('print("action1")')

        skill2 = temp_dir / "skill2"
        skill2.mkdir()
        (skill2 / "SKILL.md").write_text("""---
name: skill-two
description: Second skill
---

Instructions for skill two.
""")
        scripts2 = skill2 / "scripts"
        scripts2.mkdir()
        (scripts2 / "action2.py").write_text('print("action2")')

        # Create multi-skill toolset
        multi = MultiSkillToolset.from_paths([skill1, skill2])

        specs = multi.get_toolspecs()
        assert len(specs) == 2

        # Both skills' tools should be available
        names = multi.tool_names
        assert "skill_one_action1" in names
        assert "skill_two_action2" in names

    def test_execute_routes_correctly(self, temp_dir):
        """Test that execute routes to correct skill."""
        # Create two skills
        skill1 = temp_dir / "skill1"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("""---
name: skill-one
description: First skill
---

Instructions.
""")
        scripts1 = skill1 / "scripts"
        scripts1.mkdir()
        (scripts1 / "greet.py").write_text('print("Hello from skill 1")')

        skill2 = temp_dir / "skill2"
        skill2.mkdir()
        (skill2 / "SKILL.md").write_text("""---
name: skill-two
description: Second skill
---

Instructions.
""")
        scripts2 = skill2 / "scripts"
        scripts2.mkdir()
        (scripts2 / "greet.py").write_text('print("Hello from skill 2")')

        multi = MultiSkillToolset.from_paths([skill1, skill2])

        result1 = multi.execute("skill_one_greet", ScriptToolParams())
        assert "Hello from skill 1" in result1

        result2 = multi.execute("skill_two_greet", ScriptToolParams())
        assert "Hello from skill 2" in result2

    def test_execute_unknown_tool(self, temp_dir):
        """Test error for unknown tool in multi-skill toolset."""
        skill = temp_dir / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("""---
name: test-skill
description: Test skill
---

Instructions.
""")

        multi = MultiSkillToolset.from_paths([skill])

        with pytest.raises(ValueError, match="Unknown tool"):
            multi.execute("nonexistent", ScriptToolParams())

    def test_get_combined_system_prompt(self, temp_dir):
        """Test getting combined system prompt."""
        skill1 = temp_dir / "skill1"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("""---
name: skill-one
description: First skill
---

Instructions for skill one.
""")

        skill2 = temp_dir / "skill2"
        skill2.mkdir()
        (skill2 / "SKILL.md").write_text("""---
name: skill-two
description: Second skill
---

Instructions for skill two.
""")

        multi = MultiSkillToolset.from_paths([skill1, skill2])
        prompt = multi.get_combined_system_prompt()

        assert "skill-one" in prompt
        assert "skill-two" in prompt
        assert "Instructions for skill one" in prompt
        assert "Instructions for skill two" in prompt


class TestConvenienceFunction:
    """Tests for create_skill_toolset function."""

    def test_create_skill_toolset(self, sample_skill_dir):
        """Test creating toolset with convenience function."""
        toolset = create_skill_toolset(
            sample_skill_dir,
            tool_prefix="my_",
            timeout_seconds=60,
        )

        assert toolset.tool_prefix == "my_"
        assert toolset.execution_config.timeout_seconds == 60

    def test_create_skill_toolset_defaults(self, sample_skill_dir):
        """Test creating toolset with default values."""
        toolset = create_skill_toolset(sample_skill_dir)

        assert toolset.execution_config.timeout_seconds == 30  # default
