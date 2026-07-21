"""Tests for skills parser."""

import pytest

from rustic_ai.skills.parser import (
    SkillParseError,
    SkillParser,
    parse_skill,
    parse_skill_metadata,
)


class TestSkillParser:
    """Tests for SkillParser class."""

    def test_parse_full_skill(self, sample_skill_dir):
        """Test parsing a complete skill directory."""
        skill = SkillParser.parse(sample_skill_dir)

        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
        assert skill.metadata.allowed_tools == ["Read", "Write", "Bash"]
        assert skill.metadata.model == "gpt-4"

        # Check instructions
        assert "# Test Skill" in skill.instructions
        assert "unit testing purposes" in skill.instructions

        # Check scripts
        assert len(skill.scripts) == 2
        script_names = [s.name for s in skill.scripts]
        assert "process" in script_names
        assert "setup" in script_names

        # Check references
        assert len(skill.references) == 1
        assert skill.references[0].name == "api-docs.md"

        # Check assets
        assert len(skill.assets) == 1
        assert skill.assets[0].name == "template.json"

    def test_parse_minimal_skill(self, minimal_skill_dir):
        """Test parsing a minimal skill (SKILL.md only)."""
        skill = SkillParser.parse(minimal_skill_dir)

        assert skill.name == "minimal-skill"
        assert skill.description == "Minimal skill for testing"
        assert skill.metadata.allowed_tools is None
        assert skill.metadata.model is None

        assert len(skill.scripts) == 0
        assert len(skill.references) == 0
        assert len(skill.assets) == 0

    def test_parse_missing_skill_md(self, empty_dir):
        """Test error when SKILL.md is missing."""
        with pytest.raises(SkillParseError, match="SKILL.md not found"):
            SkillParser.parse(empty_dir)

    def test_parse_not_directory(self, temp_dir):
        """Test error when path is not a directory."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("not a directory")

        with pytest.raises(SkillParseError, match="not a directory"):
            SkillParser.parse(file_path)

    def test_parse_missing_description(self, invalid_skill_dir):
        """Test error when description is missing."""
        with pytest.raises(SkillParseError, match="description"):
            SkillParser.parse(invalid_skill_dir)

    def test_parse_metadata_only(self, sample_skill_dir):
        """Test parsing only metadata (lazy loading)."""
        metadata = SkillParser.parse_metadata_only(sample_skill_dir)

        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill for unit testing"
        assert metadata.allowed_tools == ["Read", "Write", "Bash"]

    def test_parse_metadata_only_minimal(self, minimal_skill_dir):
        """Test parsing metadata from minimal skill."""
        metadata = SkillParser.parse_metadata_only(minimal_skill_dir)

        assert metadata.name == "minimal-skill"
        assert metadata.description == "Minimal skill for testing"

    def test_split_frontmatter(self):
        """Test frontmatter splitting."""
        content = """---
name: test
description: testing
---

# Body content

More content here.
"""
        frontmatter, body = SkillParser._split_frontmatter(content)

        assert frontmatter == "name: test\ndescription: testing"
        assert "# Body content" in body
        assert "More content here." in body

    def test_split_frontmatter_no_delimiter(self):
        """Test content without frontmatter."""
        content = "# Just markdown\n\nNo frontmatter."
        frontmatter, body = SkillParser._split_frontmatter(content)

        assert frontmatter is None
        assert body == content

    def test_parse_allowed_tools_string(self, temp_dir):
        """Test parsing allowed-tools as comma-separated string."""
        skill_path = temp_dir / "string-tools"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("""---
name: string-tools
description: Test string tools
allowed-tools: Read, Write, Bash
---

Instructions
""")

        metadata = SkillParser.parse_metadata_only(skill_path)
        assert metadata.allowed_tools == ["Read", "Write", "Bash"]

    def test_parse_allowed_tools_list(self, temp_dir):
        """Test parsing allowed-tools as YAML list."""
        skill_path = temp_dir / "list-tools"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("""---
name: list-tools
description: Test list tools
allowed-tools:
  - Read
  - Write
  - Bash
---

Instructions
""")

        metadata = SkillParser.parse_metadata_only(skill_path)
        assert metadata.allowed_tools == ["Read", "Write", "Bash"]

    def test_discover_scripts_descriptions(self, temp_dir):
        """Test script description extraction."""
        skill_path = temp_dir / "desc-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("""---
name: desc-skill
description: Skill with script descriptions
---

Instructions
""")

        scripts_dir = skill_path / "scripts"
        scripts_dir.mkdir()

        # Python script with docstring
        (scripts_dir / "python_script.py").write_text('''"""Process data and return results.

This is a longer description."""
import sys
print("hello")
''')

        # Shell script with comment
        (scripts_dir / "shell_script.sh").write_text("""#!/bin/bash
# Run the setup process
echo "setup"
""")

        skill = SkillParser.parse(skill_path)

        python_script = skill.get_script("python_script")
        assert python_script is not None
        assert python_script.description == "Process data and return results."

        shell_script = skill.get_script("shell_script")
        assert shell_script is not None
        assert shell_script.description == "Run the setup process"


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_parse_skill(self, sample_skill_dir):
        """Test parse_skill function."""
        skill = parse_skill(sample_skill_dir)
        assert skill.name == "test-skill"

    def test_parse_skill_metadata(self, sample_skill_dir):
        """Test parse_skill_metadata function."""
        metadata = parse_skill_metadata(sample_skill_dir)
        assert metadata.name == "test-skill"
