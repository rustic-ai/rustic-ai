"""Pytest fixtures for skills module tests."""

from pathlib import Path
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Common Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_skill_md():
    """Sample SKILL.md content."""
    return """---
name: test-skill
description: A test skill for unit testing
allowed-tools: Read, Write, Bash
model: gpt-4
---

# Test Skill

This is a test skill for unit testing purposes.

## Instructions

1. First, read the input file
2. Process the data
3. Write the output

## Notes

- This skill is for testing only
- Do not use in production
"""


@pytest.fixture
def sample_skill_md_minimal():
    """Minimal SKILL.md with only required fields."""
    return """---
name: minimal-skill
description: Minimal skill for testing
---

# Minimal Skill

Simple instructions.
"""


@pytest.fixture
def sample_skill_dir(temp_dir, sample_skill_md):
    """Create a sample skill directory structure."""
    skill_path = temp_dir / "test-skill"
    skill_path.mkdir()

    # Create SKILL.md
    (skill_path / "SKILL.md").write_text(sample_skill_md)

    # Create scripts directory with sample scripts
    scripts_dir = skill_path / "scripts"
    scripts_dir.mkdir()

    # Python script
    (scripts_dir / "process.py").write_text(
        '''"""Process input data and return result."""
import json
import os

args = json.loads(os.environ.get("SKILL_ARGS", "{}"))
print(f"Processing: {args}")
'''
    )

    # Shell script
    (scripts_dir / "setup.sh").write_text(
        """#!/bin/bash
# Setup the environment
echo "Setting up..."
echo "Done"
"""
    )

    # Create references directory
    refs_dir = skill_path / "references"
    refs_dir.mkdir()
    (refs_dir / "api-docs.md").write_text(
        """# API Documentation

This is the API documentation for the test skill.
"""
    )

    # Create assets directory
    assets_dir = skill_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "template.json").write_text('{"key": "value"}')

    return skill_path


@pytest.fixture
def minimal_skill_dir(temp_dir, sample_skill_md_minimal):
    """Create a minimal skill directory (SKILL.md only)."""
    skill_path = temp_dir / "minimal-skill"
    skill_path.mkdir()

    (skill_path / "SKILL.md").write_text(sample_skill_md_minimal)

    return skill_path


@pytest.fixture
def empty_dir(temp_dir):
    """Create an empty directory (no SKILL.md)."""
    empty_path = temp_dir / "empty"
    empty_path.mkdir()
    return empty_path


@pytest.fixture
def invalid_skill_md():
    """Invalid SKILL.md content (missing required fields)."""
    return """---
name: invalid-skill
---

Missing description field.
"""


@pytest.fixture
def invalid_skill_dir(temp_dir, invalid_skill_md):
    """Create a skill directory with invalid SKILL.md."""
    skill_path = temp_dir / "invalid-skill"
    skill_path.mkdir()

    (skill_path / "SKILL.md").write_text(invalid_skill_md)

    return skill_path


@pytest.fixture
def skills_collection_dir(temp_dir, sample_skill_md, sample_skill_md_minimal):
    """Create a directory containing multiple skills."""
    # Skill 1
    skill1 = temp_dir / "skill-one"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text(sample_skill_md)

    # Skill 2
    skill2 = temp_dir / "skill-two"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text(sample_skill_md_minimal)

    # Non-skill directory (no SKILL.md)
    other = temp_dir / "not-a-skill"
    other.mkdir()
    (other / "README.md").write_text("Not a skill")

    return temp_dir
