"""Pytest fixtures for ReAct agent integration tests."""

from pathlib import Path
import tempfile

import pytest


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
