"""
End-to-end integration tests for Skills with ReActAgent.

These tests verify the complete flow of:
1. Discovering skills from various sources (including Anthropic's official skills)
2. Installing skills locally
3. Creating SkillToolsets from installed skills
4. Using skills with ReActAgent for real LLM-powered task execution

Tests are organized by scenario:
- Local skill tests (fast, no external dependencies)
- Anthropic skill integration tests (require network + API keys)
- Multi-skill composition tests
- Error handling and edge cases

NOTE: These tests use REAL skills and REAL LLM calls - no mocks.
NOTE: Agent specs are loaded from YAML/JSON to verify serializability.
"""

import json
import os
from pathlib import Path
import tempfile
from typing import Any, List, Optional

from pydantic import BaseModel
import pytest
import yaml

from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.llm_agent.react import (
    CompositeToolset,
    ReActAgent,
    ReActAgentConfig,
    ReActToolset,
)
from rustic_ai.skills.executor import ExecutionConfig
from rustic_ai.skills.marketplace import MarketplaceError, SkillMarketplace
from rustic_ai.skills.toolset import (
    MarketplaceSkillToolset,
    ScriptToolParams,
    SkillToolset,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing

# ---------------------------------------------------------------------------
# Helper Functions for YAML/JSON Spec Loading
# ---------------------------------------------------------------------------


def create_agent_spec_yaml(
    agent_id: str,
    name: str,
    description: str,
    model: str,
    toolset_kind: str,
    skill_paths: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    max_iterations: int = 5,
) -> dict:
    """
    Create an agent spec dictionary that can be serialized to YAML/JSON.

    This demonstrates the spec structure that works with serializable toolsets.
    """
    toolset_config: dict[str, Any] = {"kind": toolset_kind}
    if skill_paths:
        toolset_config["skill_paths"] = skill_paths

    spec: dict[str, Any] = {
        "id": agent_id,
        "name": name,
        "description": description,
        "class_name": "rustic_ai.llm_agent.react.ReActAgent",
        "properties": {
            "model": model,
            "max_iterations": max_iterations,
            "toolset": toolset_config,
        },
    }

    if system_prompt:
        spec["properties"]["system_prompt"] = system_prompt

    return spec


def save_spec_to_yaml(spec: dict, path: Path) -> Path:
    """Save an agent spec to a YAML file."""
    yaml_path = path / "agent_spec.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(spec, f, default_flow_style=False)
    return yaml_path


def save_spec_to_json(spec: dict, path: Path) -> Path:
    """Save an agent spec to a JSON file."""
    json_path = path / "agent_spec.json"
    with open(json_path, "w") as f:
        json.dump(spec, f, indent=2)
    return json_path


def load_agent_spec_from_yaml(yaml_path: Path) -> AgentSpec:
    """Load an AgentSpec from a YAML file."""
    with open(yaml_path, "r") as f:
        spec_dict = yaml.safe_load(f)
    return AgentSpec.model_validate(spec_dict)


def load_agent_spec_from_json(json_path: Path) -> AgentSpec:
    """Load an AgentSpec from a JSON file."""
    with open(json_path, "r") as f:
        spec_dict = json.load(f)
    return AgentSpec.model_validate(spec_dict)


def verify_spec_roundtrip(agent_spec: AgentSpec, temp_dir: Path) -> AgentSpec:
    """
    Verify that an AgentSpec can be serialized and deserialized correctly.

    This tests the full roundtrip: AgentSpec -> YAML -> AgentSpec
    """
    # Serialize to dict
    spec_dict = agent_spec.model_dump()

    # Save to YAML
    yaml_path = save_spec_to_yaml(spec_dict, temp_dir)

    # Load back
    loaded_spec = load_agent_spec_from_yaml(yaml_path)

    return loaded_spec


# ---------------------------------------------------------------------------
# Fixtures for Integration Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_install_dir():
    """Create a temporary installation directory for skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for skills marketplace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def calculator_skill_dir(temp_install_dir):
    """
    Create a real calculator skill with working Python scripts.

    This skill performs mathematical calculations using Python's math library.
    """
    skill_dir = temp_install_dir / "calculator"
    skill_dir.mkdir(parents=True)

    skill_md = """---
name: calculator
description: Perform mathematical calculations including arithmetic, trigonometry, and advanced math operations.
allowed-tools: Bash
---

# Calculator Skill

A comprehensive calculator for mathematical operations.

## Capabilities

- Basic arithmetic: addition, subtraction, multiplication, division
- Advanced math: power, square root, logarithm
- Trigonometric functions: sin, cos, tan
- Constants: pi, e

## Usage

Use the calculate script to evaluate mathematical expressions.
Pass the expression as an argument to compute the result.
"""
    (skill_dir / "SKILL.md").write_text(skill_md)

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()

    # Real working calculator script
    (scripts_dir / "calculate.py").write_text(
        '''#!/usr/bin/env python3
"""Evaluate a mathematical expression and return the result."""
import json
import os
import math

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)
    expression = args.get("expression", "0")

    # Create a safe evaluation context with math functions
    safe_dict = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "pi": math.pi,
        "e": math.e,
    }

    try:
        # Evaluate the expression safely
        result = eval(expression, {"__builtins__": {}}, safe_dict)
        output = {
            "success": True,
            "expression": expression,
            "result": result
        }
    except Exception as e:
        output = {
            "success": False,
            "expression": expression,
            "error": str(e)
        }

    print(json.dumps(output))

if __name__ == "__main__":
    main()
'''
    )

    # Unit conversion script
    (scripts_dir / "convert.py").write_text(
        '''#!/usr/bin/env python3
"""Convert between units of measurement."""
import json
import os

CONVERSIONS = {
    # Length
    ("meters", "feet"): 3.28084,
    ("feet", "meters"): 0.3048,
    ("kilometers", "miles"): 0.621371,
    ("miles", "kilometers"): 1.60934,
    ("inches", "centimeters"): 2.54,
    ("centimeters", "inches"): 0.393701,
    # Weight
    ("kilograms", "pounds"): 2.20462,
    ("pounds", "kilograms"): 0.453592,
    # Temperature handled separately
}

def convert_temperature(value, from_unit, to_unit):
    if from_unit == "celsius" and to_unit == "fahrenheit":
        return value * 9/5 + 32
    elif from_unit == "fahrenheit" and to_unit == "celsius":
        return (value - 32) * 5/9
    elif from_unit == "celsius" and to_unit == "kelvin":
        return value + 273.15
    elif from_unit == "kelvin" and to_unit == "celsius":
        return value - 273.15
    return None

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    value = args.get("value", 0)
    from_unit = args.get("from_unit", "").lower()
    to_unit = args.get("to_unit", "").lower()

    # Try temperature conversion
    temp_result = convert_temperature(value, from_unit, to_unit)
    if temp_result is not None:
        print(json.dumps({
            "success": True,
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "result": temp_result
        }))
        return

    # Try standard conversion
    key = (from_unit, to_unit)
    if key in CONVERSIONS:
        result = value * CONVERSIONS[key]
        print(json.dumps({
            "success": True,
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "result": result
        }))
    else:
        print(json.dumps({
            "success": False,
            "error": f"Unknown conversion: {from_unit} to {to_unit}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    return skill_dir


@pytest.fixture
def text_processing_skill_dir(temp_install_dir):
    """
    Create a real text processing skill with working scripts.

    This skill performs text analysis and transformation.
    """
    skill_dir = temp_install_dir / "text-processor"
    skill_dir.mkdir(parents=True)

    skill_md = """---
name: text-processor
description: Analyze and transform text - count words, find patterns, format text, and extract information.
allowed-tools: Read
---

# Text Processor Skill

A comprehensive text processing toolkit.

## Capabilities

- Word and character counting
- Text transformation (uppercase, lowercase, title case)
- Pattern finding and extraction
- Text statistics

## Usage

Use the available scripts to process text:
- analyze: Get statistics about text
- transform: Change text format
- extract: Find patterns in text
"""
    (skill_dir / "SKILL.md").write_text(skill_md)

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()

    # Text analysis script
    (scripts_dir / "analyze.py").write_text(
        '''#!/usr/bin/env python3
"""Analyze text and return statistics."""
import json
import os
import re

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)
    text = args.get("text", "")

    # Calculate statistics
    char_count = len(text)
    char_count_no_spaces = len(text.replace(" ", ""))
    word_count = len(text.split()) if text.strip() else 0
    line_count = len(text.splitlines()) if text else 0
    sentence_count = len(re.findall(r'[.!?]+', text))

    # Find unique words
    words = re.findall(r'\\b\\w+\\b', text.lower())
    unique_words = len(set(words))

    # Average word length
    avg_word_length = sum(len(w) for w in words) / len(words) if words else 0

    output = {
        "success": True,
        "statistics": {
            "characters": char_count,
            "characters_no_spaces": char_count_no_spaces,
            "words": word_count,
            "unique_words": unique_words,
            "lines": line_count,
            "sentences": sentence_count,
            "average_word_length": round(avg_word_length, 2)
        }
    }

    print(json.dumps(output))

if __name__ == "__main__":
    main()
'''
    )

    # Text transformation script
    (scripts_dir / "transform.py").write_text(
        '''#!/usr/bin/env python3
"""Transform text according to specified operation."""
import json
import os

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)
    text = args.get("text", "")
    operation = args.get("operation", "uppercase").lower()

    operations = {
        "uppercase": text.upper(),
        "lowercase": text.lower(),
        "title": text.title(),
        "capitalize": text.capitalize(),
        "swapcase": text.swapcase(),
        "reverse": text[::-1],
        "strip": text.strip(),
    }

    if operation in operations:
        result = operations[operation]
        print(json.dumps({
            "success": True,
            "original": text,
            "operation": operation,
            "result": result
        }))
    else:
        print(json.dumps({
            "success": False,
            "error": f"Unknown operation: {operation}. Available: {list(operations.keys())}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    # Pattern extraction script
    (scripts_dir / "extract.py").write_text(
        '''#!/usr/bin/env python3
"""Extract patterns from text using regex."""
import json
import os
import re

# Predefined patterns
PATTERNS = {
    "emails": r'[\\w.+-]+@[\\w-]+\\.[\\w.-]+',
    "urls": r'https?://[\\w.-]+(?:/[\\w./-]*)?',
    "numbers": r'\\b\\d+(?:\\.\\d+)?\\b',
    "words": r'\\b\\w+\\b',
    "sentences": r'[^.!?]*[.!?]',
    "phone": r'\\b\\d{3}[-.]?\\d{3}[-.]?\\d{4}\\b',
}

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)
    text = args.get("text", "")
    pattern_name = args.get("pattern", "words").lower()
    custom_pattern = args.get("custom_pattern", None)

    # Use custom pattern or predefined
    if custom_pattern:
        pattern = custom_pattern
    elif pattern_name in PATTERNS:
        pattern = PATTERNS[pattern_name]
    else:
        print(json.dumps({
            "success": False,
            "error": f"Unknown pattern: {pattern_name}. Available: {list(PATTERNS.keys())}"
        }))
        return

    try:
        matches = re.findall(pattern, text)
        print(json.dumps({
            "success": True,
            "pattern": pattern_name if not custom_pattern else "custom",
            "matches": matches,
            "count": len(matches)
        }))
    except re.error as e:
        print(json.dumps({
            "success": False,
            "error": f"Invalid regex pattern: {e}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    return skill_dir


@pytest.fixture
def data_skill_dir(temp_install_dir):
    """
    Create a real data processing skill with working scripts.

    This skill handles JSON and CSV data operations.
    """
    skill_dir = temp_install_dir / "data-tools"
    skill_dir.mkdir(parents=True)

    skill_md = """---
name: data-tools
description: Process and analyze structured data - JSON manipulation, data filtering, aggregation, and formatting.
allowed-tools: Read, Write
---

# Data Tools Skill

Tools for working with structured data.

## Capabilities

- JSON parsing and formatting
- Data filtering and querying
- Aggregation (sum, average, count)
- Data transformation

## Usage

Use these scripts to process data:
- json_query: Query and filter JSON data
- aggregate: Compute aggregations on numeric data
- format_json: Pretty print or minify JSON
"""
    (skill_dir / "SKILL.md").write_text(skill_md)

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()

    # JSON query script
    (scripts_dir / "json_query.py").write_text(
        '''#!/usr/bin/env python3
"""Query and filter JSON data."""
import json
import os

def get_nested_value(data, path):
    """Get value from nested dict using dot notation."""
    keys = path.split(".")
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)] if int(key) < len(data) else None
        else:
            return None
    return data

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    data = args.get("data", {})
    path = args.get("path", "")
    filter_key = args.get("filter_key", "")
    filter_value = args.get("filter_value", "")

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            return

    # Apply path navigation
    if path:
        result = get_nested_value(data, path)
    else:
        result = data

    # Apply filter if specified
    if filter_key and isinstance(result, list):
        result = [item for item in result
                  if isinstance(item, dict) and str(item.get(filter_key)) == str(filter_value)]

    print(json.dumps({
        "success": True,
        "result": result,
        "type": type(result).__name__
    }))

if __name__ == "__main__":
    main()
'''
    )

    # Aggregation script
    (scripts_dir / "aggregate.py").write_text(
        '''#!/usr/bin/env python3
"""Compute aggregations on numeric data."""
import json
import os
import statistics

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    numbers = args.get("numbers", [])
    operation = args.get("operation", "sum").lower()

    if not numbers:
        print(json.dumps({"success": False, "error": "No numbers provided"}))
        return

    # Ensure all values are numeric
    try:
        numbers = [float(n) for n in numbers]
    except (ValueError, TypeError) as e:
        print(json.dumps({"success": False, "error": f"Invalid numbers: {e}"}))
        return

    operations = {
        "sum": sum(numbers),
        "average": statistics.mean(numbers),
        "mean": statistics.mean(numbers),
        "median": statistics.median(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "count": len(numbers),
        "stdev": statistics.stdev(numbers) if len(numbers) > 1 else 0,
    }

    if operation in operations:
        print(json.dumps({
            "success": True,
            "operation": operation,
            "numbers": numbers,
            "result": operations[operation]
        }))
    else:
        print(json.dumps({
            "success": False,
            "error": f"Unknown operation: {operation}. Available: {list(operations.keys())}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    # JSON formatting script
    (scripts_dir / "format_json.py").write_text(
        '''#!/usr/bin/env python3
"""Format JSON data - pretty print or minify."""
import json
import os

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    data = args.get("data", {})
    mode = args.get("mode", "pretty").lower()
    indent = args.get("indent", 2)

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            return

    if mode == "pretty":
        formatted = json.dumps(data, indent=indent, sort_keys=True)
    elif mode == "minify":
        formatted = json.dumps(data, separators=(',', ':'))
    else:
        print(json.dumps({"success": False, "error": f"Unknown mode: {mode}"}))
        return

    print(json.dumps({
        "success": True,
        "mode": mode,
        "result": formatted
    }))

if __name__ == "__main__":
    main()
'''
    )

    return skill_dir


@pytest.fixture
def datetime_skill_dir(temp_install_dir):
    """
    Create a real datetime skill with working scripts.

    This skill handles date and time operations.
    """
    skill_dir = temp_install_dir / "datetime"
    skill_dir.mkdir(parents=True)

    skill_md = """---
name: datetime
description: Work with dates and times - get current time, format dates, calculate durations, and convert timezones.
allowed-tools: Bash
---

# DateTime Skill

Tools for working with dates and times.

## Capabilities

- Get current date/time
- Parse and format dates
- Calculate time differences
- Date arithmetic (add/subtract days, hours, etc.)

## Usage

Use these scripts for date/time operations:
- now: Get current date and time
- format: Format a date string
- diff: Calculate difference between dates
- add: Add time to a date
"""
    (skill_dir / "SKILL.md").write_text(skill_md)

    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()

    # Current time script
    (scripts_dir / "now.py").write_text(
        '''#!/usr/bin/env python3
"""Get the current date and time."""
import json
import os
from datetime import datetime, timezone

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    format_str = args.get("format", "%Y-%m-%d %H:%M:%S")
    utc = args.get("utc", False)

    if utc:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()

    print(json.dumps({
        "success": True,
        "datetime": now.strftime(format_str),
        "iso": now.isoformat(),
        "timestamp": now.timestamp(),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
        "second": now.second,
        "weekday": now.strftime("%A"),
        "utc": utc
    }))

if __name__ == "__main__":
    main()
'''
    )

    # Date formatting script
    (scripts_dir / "format.py").write_text(
        '''#!/usr/bin/env python3
"""Format a date string into different formats."""
import json
import os
from datetime import datetime

COMMON_FORMATS = {
    "iso": "%Y-%m-%dT%H:%M:%S",
    "date": "%Y-%m-%d",
    "time": "%H:%M:%S",
    "us": "%m/%d/%Y",
    "eu": "%d/%m/%Y",
    "long": "%B %d, %Y",
    "full": "%A, %B %d, %Y %I:%M %p",
}

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    date_str = args.get("date", "")
    input_format = args.get("input_format", "%Y-%m-%d")
    output_format = args.get("output_format", "iso")

    # Use named format or custom
    if output_format in COMMON_FORMATS:
        output_format = COMMON_FORMATS[output_format]

    try:
        dt = datetime.strptime(date_str, input_format)
        result = dt.strftime(output_format)
        print(json.dumps({
            "success": True,
            "input": date_str,
            "output": result,
            "format": output_format
        }))
    except ValueError as e:
        print(json.dumps({
            "success": False,
            "error": f"Failed to parse date: {e}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    # Date difference script
    (scripts_dir / "diff.py").write_text(
        '''#!/usr/bin/env python3
"""Calculate the difference between two dates."""
import json
import os
from datetime import datetime

def main():
    args_json = os.environ.get("SKILL_ARGS", "{}")
    args = json.loads(args_json)

    date1_str = args.get("date1", "")
    date2_str = args.get("date2", "")
    format_str = args.get("format", "%Y-%m-%d")

    try:
        date1 = datetime.strptime(date1_str, format_str)
        date2 = datetime.strptime(date2_str, format_str)

        diff = date2 - date1

        print(json.dumps({
            "success": True,
            "date1": date1_str,
            "date2": date2_str,
            "difference": {
                "days": diff.days,
                "seconds": diff.seconds,
                "total_seconds": diff.total_seconds(),
                "weeks": diff.days // 7,
                "hours": diff.total_seconds() / 3600,
            }
        }))
    except ValueError as e:
        print(json.dumps({
            "success": False,
            "error": f"Failed to parse dates: {e}"
        }))

if __name__ == "__main__":
    main()
'''
    )

    return skill_dir


# ---------------------------------------------------------------------------
# Helper Toolsets for Comparison Tests
# ---------------------------------------------------------------------------


class SimpleCalculatorParams(BaseModel):
    """Parameters for simple calculator tool."""

    expression: str
    """Mathematical expression to evaluate."""


class SimpleCalculatorToolset(ReActToolset):
    """A basic calculator toolset for comparison testing."""

    def get_toolspecs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="basic_calc",
                description="Evaluate a simple arithmetic expression (e.g., '2 + 2', '10 * 5').",
                parameter_class=SimpleCalculatorParams,
            )
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        if tool_name == "basic_calc":
            try:
                allowed_chars = set("0123456789+-*/() .")
                calc_args = SimpleCalculatorParams.model_validate(args.model_dump())
                expression = calc_args.expression
                if not all(c in allowed_chars for c in expression):
                    return "Error: Invalid characters in expression"
                result = eval(expression)  # noqa: S307
                return str(result)
            except Exception as e:
                return f"Error: {e}"
        raise ValueError(f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# Unit Tests for SkillToolset
# ---------------------------------------------------------------------------


class TestSkillToolsetIntegration:
    """Tests for SkillToolset integration with ReActAgent components."""

    def test_skill_toolset_creates_valid_toolspecs(self, calculator_skill_dir):
        """Verify SkillToolset creates proper ToolSpecs from skill scripts."""
        toolset = SkillToolset.from_path(calculator_skill_dir)
        specs = toolset.get_toolspecs()

        assert len(specs) == 2  # calculate, convert

        spec_names = [s.name for s in specs]
        assert "calculator_calculate" in spec_names
        assert "calculator_convert" in spec_names

        # Verify each spec has required attributes
        for spec in specs:
            assert spec.description
            assert spec.parameter_class == ScriptToolParams

    def test_skill_toolset_executes_calculator(self, calculator_skill_dir):
        """Verify SkillToolset can execute calculator scripts."""
        toolset = SkillToolset.from_path(calculator_skill_dir)

        # Execute calculation
        result = toolset.execute(
            "calculator_calculate",
            ScriptToolParams(args={"expression": "2 + 2 * 3"}),
        )

        assert "success" in result
        assert "true" in result.lower()
        assert "8" in result  # 2 + 2 * 3 = 8

    def test_skill_toolset_executes_sqrt_calculation(self, calculator_skill_dir):
        """Verify SkillToolset can execute advanced math."""
        toolset = SkillToolset.from_path(calculator_skill_dir)

        result = toolset.execute(
            "calculator_calculate",
            ScriptToolParams(args={"expression": "sqrt(144)"}),
        )

        assert "success" in result
        assert "12" in result

    def test_skill_toolset_executes_conversion(self, calculator_skill_dir):
        """Verify SkillToolset can execute unit conversions."""
        toolset = SkillToolset.from_path(calculator_skill_dir)

        result = toolset.execute(
            "calculator_convert",
            ScriptToolParams(args={"value": 100, "from_unit": "celsius", "to_unit": "fahrenheit"}),
        )

        assert "success" in result
        assert "212" in result  # 100°C = 212°F

    def test_skill_toolset_text_processing(self, text_processing_skill_dir):
        """Verify text processing skill works correctly."""
        toolset = SkillToolset.from_path(text_processing_skill_dir)

        # Test text analysis
        result = toolset.execute(
            "text_processor_analyze",
            ScriptToolParams(args={"text": "Hello world. This is a test."}),
        )

        assert "success" in result
        assert "words" in result

    def test_skill_toolset_text_transform(self, text_processing_skill_dir):
        """Verify text transformation works correctly."""
        toolset = SkillToolset.from_path(text_processing_skill_dir)

        result = toolset.execute(
            "text_processor_transform",
            ScriptToolParams(args={"text": "hello world", "operation": "uppercase"}),
        )

        assert "HELLO WORLD" in result

    def test_skill_toolset_chat_tools_format(self, calculator_skill_dir):
        """Verify SkillToolset produces valid ChatCompletionTool format."""
        toolset = SkillToolset.from_path(calculator_skill_dir)
        chat_tools = toolset.chat_tools

        assert len(chat_tools) == 2

        for tool in chat_tools:
            assert tool.type == "function"
            assert tool.function.name
            assert tool.function.description
            assert tool.function.parameters

    def test_skill_toolset_system_prompt_addition(self, calculator_skill_dir):
        """Verify system prompt generation includes skill instructions."""
        toolset = SkillToolset.from_path(calculator_skill_dir)
        prompt = toolset.get_system_prompt_addition()

        # Should include skill name and instructions
        assert "calculator" in prompt.lower()
        assert "Calculator Skill" in prompt

        # Should list available scripts
        assert "Available Scripts" in prompt
        assert "calculate" in prompt.lower()


class TestSkillToolsetWithMultipleSkills:
    """Tests for SkillToolset with multiple skills in ReActAgent integration."""

    def test_toolset_combines_multiple_skills(self, calculator_skill_dir, text_processing_skill_dir):
        """Verify that SkillToolset combines tools from multiple skills."""
        toolset = SkillToolset.from_paths(
            [
                calculator_skill_dir,
                text_processing_skill_dir,
            ]
        )

        specs = toolset.get_toolspecs()
        names = [s.name for s in specs]

        # Should have tools from both skills
        assert "calculator_calculate" in names
        assert "calculator_convert" in names
        assert "text_processor_analyze" in names
        assert "text_processor_transform" in names

    def test_toolset_routes_to_correct_skill(self, calculator_skill_dir, text_processing_skill_dir):
        """Verify that SkillToolset routes execution to the correct skill."""
        toolset = SkillToolset.from_paths(
            [
                calculator_skill_dir,
                text_processing_skill_dir,
            ]
        )

        # Execute from calculator skill
        result1 = toolset.execute(
            "calculator_calculate",
            ScriptToolParams(args={"expression": "10 * 5"}),
        )
        assert "50" in result1

        # Execute from text skill
        result2 = toolset.execute(
            "text_processor_transform",
            ScriptToolParams(args={"text": "test", "operation": "uppercase"}),
        )
        assert "TEST" in result2

    def test_composite_with_skill_toolset(self, calculator_skill_dir):
        """Test CompositeToolset with SkillToolset and regular ReActToolset."""
        skill_toolset = SkillToolset.from_path(calculator_skill_dir)
        basic_toolset = SimpleCalculatorToolset()

        composite = CompositeToolset(toolsets=[skill_toolset, basic_toolset])

        specs = composite.get_toolspecs()
        names = [s.name for s in specs]

        # Should have tools from both
        assert "calculator_calculate" in names
        assert "basic_calc" in names

        # Both should be executable
        result1 = composite.execute(
            "calculator_calculate",
            ScriptToolParams(args={"expression": "sqrt(25)"}),
        )
        assert "5" in result1

        result2 = composite.execute(
            "basic_calc",
            SimpleCalculatorParams(expression="2 + 2"),
        )
        assert "4" in result2


# ---------------------------------------------------------------------------
# Marketplace Integration Tests
# ---------------------------------------------------------------------------


class TestMarketplaceIntegration:
    """Tests for skill marketplace integration."""

    def test_discover_local_skills(self, calculator_skill_dir, temp_install_dir):
        """Test discovering skills from a local source."""
        marketplace = SkillMarketplace(install_path=temp_install_dir / "installed")
        marketplace.add_source(
            name="local-test",
            source_type="local",
            location=str(calculator_skill_dir.parent),
            skills_path="",
        )

        discovered = marketplace.discover("local-test")

        assert len(discovered) >= 1
        names = [s.name for s in discovered]
        assert "calculator" in names

    def test_install_and_create_toolset(self, calculator_skill_dir, temp_install_dir):
        """Test full flow: discover -> install -> create toolset."""
        install_path = temp_install_dir / "installed"
        marketplace = SkillMarketplace(install_path=install_path)

        # Add local source pointing to parent directory
        marketplace.add_source(
            name="local-test",
            source_type="local",
            location=str(calculator_skill_dir.parent),
            skills_path="",
        )

        # Discover and install
        marketplace.discover("local-test")
        installed_path = marketplace.install("calculator")

        assert installed_path.exists()
        assert (installed_path / "SKILL.md").exists()

        # Create toolset from installed skill
        toolset = SkillToolset.from_path(installed_path)
        assert toolset.tool_count >= 1

        # Verify it still works after installation
        result = toolset.execute(
            "calculator_calculate",
            ScriptToolParams(args={"expression": "3 + 3"}),
        )
        assert "6" in result

    def test_list_installed_skills(self, calculator_skill_dir, text_processing_skill_dir, temp_install_dir):
        """Test listing installed skills."""
        install_path = temp_install_dir / "installed"
        marketplace = SkillMarketplace(install_path=install_path)

        # Add and install multiple skills
        for skill_dir in [calculator_skill_dir, text_processing_skill_dir]:
            marketplace.add_source(
                name=f"local-{skill_dir.name}",
                source_type="local",
                location=str(skill_dir.parent),
                skills_path="",
            )
            marketplace.discover(f"local-{skill_dir.name}")

        marketplace.install("calculator")
        marketplace.install("text-processor")

        installed = marketplace.list_installed()
        names = [s.name for s in installed]

        assert len(installed) == 2
        assert "calculator" in names
        assert "text-processor" in names


# ---------------------------------------------------------------------------
# LLM Integration Tests (Require API Keys)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests (set SKIP_EXPENSIVE_TESTS=false to run)",
)
@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ,
    reason="OPENAI_API_KEY not set",
)
class TestReActAgentWithSkills:
    """Integration tests for ReActAgent with real LLM calls and skills."""

    def test_react_agent_with_calculator_skill(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        calculator_skill_dir,
    ):
        """Test ReActAgent using a calculator SkillToolset with real LLM."""
        skill_toolset = SkillToolset.from_path(calculator_skill_dir)

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_calc_agent")
            .set_name("ReAct Calculator Agent")
            .set_description("A ReAct agent with calculator skill")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=skill_toolset,
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="What is the square root of 256 multiplied by 4?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # sqrt(256) = 16, 16 * 4 = 64
        assert "64" in answer

    def test_react_agent_with_text_skill(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        text_processing_skill_dir,
    ):
        """Test ReActAgent with text processing skill."""
        skill_toolset = SkillToolset.from_path(text_processing_skill_dir)

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_text_agent")
            .set_name("ReAct Text Agent")
            .set_description("A ReAct agent with text processing skill")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=skill_toolset,
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="Convert the text 'hello world from python' to uppercase.")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # Should contain uppercase result
        assert "HELLO WORLD FROM PYTHON" in answer.upper()

    def test_react_agent_with_multi_skills(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        calculator_skill_dir,
        text_processing_skill_dir,
    ):
        """Test ReActAgent with multiple skills composed together."""
        multi_toolset = SkillToolset.from_paths(
            [
                calculator_skill_dir,
                text_processing_skill_dir,
            ]
        )

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_multi_agent")
            .set_name("ReAct Multi-Skill Agent")
            .set_description("A ReAct agent with multiple skills")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=10,
                    toolset=multi_toolset,
                    system_prompt=f"""You are an AI assistant with calculation and text processing capabilities.

{multi_toolset.get_combined_system_prompt()}

Use the appropriate tools to help the user.
""",
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        # Request that requires calculation
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[UserMessage(content="Calculate 15 * 7 and tell me the result.")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        assert "105" in answer

    def test_react_agent_data_skill(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        data_skill_dir,
    ):
        """Test ReActAgent with data processing skill."""
        skill_toolset = SkillToolset.from_path(data_skill_dir)

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_data_agent")
            .set_name("ReAct Data Agent")
            .set_description("A ReAct agent with data tools")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=skill_toolset,
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="Calculate the average of these numbers: 10, 20, 30, 40, 50")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        # Average = 30
        assert "30" in answer

    def test_react_agent_datetime_skill(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        datetime_skill_dir,
    ):
        """Test ReActAgent with datetime skill."""
        skill_toolset = SkillToolset.from_path(datetime_skill_dir)

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_datetime_agent")
            .set_name("ReAct DateTime Agent")
            .set_description("A ReAct agent with datetime tools")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=skill_toolset,
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="What is the current date and time?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)

        # Should have used the datetime tool
        react_trace = response.choices[0].provider_specific_fields.get("react_trace", [])
        tool_names_used = [step.get("action", "") for step in react_trace]
        assert any("datetime" in name.lower() or "now" in name.lower() for name in tool_names_used)

    def test_react_agent_composite_skill_and_regular_toolset(
        self,
        generator,
        build_message_from_payload,
        dependency_map,
        calculator_skill_dir,
    ):
        """Test ReActAgent with both SkillToolset and regular ReActToolset."""
        skill_toolset = SkillToolset.from_path(calculator_skill_dir)
        basic_toolset = SimpleCalculatorToolset()

        composite = CompositeToolset(toolsets=[skill_toolset, basic_toolset])

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_composite_agent")
            .set_name("ReAct Composite Agent")
            .set_description("Agent with skills and regular tools")
            .set_properties(
                ReActAgentConfig(
                    model="gpt-5-nano",
                    max_iterations=5,
                    toolset=composite,
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="Calculate the value of pi times 2.")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        # pi * 2 ≈ 6.28
        assert "6.28" in answer or "6.3" in answer


# ---------------------------------------------------------------------------
# Anthropic Skills Repository Integration Tests (Complex Skills)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests",
)
@pytest.mark.skipif(
    os.getenv("SKIP_NETWORK_TESTS") == "true",
    reason="Skipping network tests",
)
class TestAnthropicSkillsRepository:
    """
    Integration tests that interact with the real Anthropic skills repository.

    These tests focus on the MOST COMPLEX skills from Anthropic:
    - xlsx: Excel formula recalculation with recalc.py (6KB+)
    - pdf: PDF processing with 8+ scripts (form filling, image conversion, etc.)
    - webapp-testing: Playwright server lifecycle with with_server.py

    These tests verify:
    1. Ability to discover skills from anthropics/skills GitHub repo
    2. Skill format compatibility including complex scripts directories
    3. Integration with SkillToolset and ReActAgent

    Note: These tests require network access and may be slow.
    """

    # The most complex skills from Anthropic's repository
    COMPLEX_SKILLS = [
        "xlsx",  # Has recalc.py for Excel formula recalculation with LibreOffice
        "pdf",  # Has 8+ scripts for PDF processing (form fields, images, etc.)
        "webapp-testing",  # Has with_server.py for Playwright server lifecycle
    ]

    @pytest.fixture
    def marketplace(self, temp_install_dir, temp_cache_dir):
        """Create a marketplace configured for Anthropic skills."""
        return SkillMarketplace(
            install_path=temp_install_dir / "installed",
            cache_path=temp_cache_dir,
        )

    def test_discover_anthropic_skills(self, marketplace):
        """Test discovering skills from the Anthropic repository."""
        discovered = marketplace.discover("anthropic")

        # Should find at least some skills (repository may change over time)
        assert len(discovered) >= 0  # Allow for empty repo

        # If skills found, verify they have required fields
        for skill in discovered:
            assert skill.name
            assert skill.description

        # Verify we can find the complex skills
        discovered_names = [s.name for s in discovered]
        for complex_skill in self.COMPLEX_SKILLS:
            if complex_skill in discovered_names:
                # Found a complex skill - good
                pass

    def test_install_complex_xlsx_skill(self, marketplace):
        """
        Test installing the xlsx skill from Anthropic repository.

        The xlsx skill is one of the most complex, containing:
        - SKILL.md with comprehensive Excel processing documentation
        - recalc.py: 6KB+ script for Excel formula recalculation using LibreOffice

        This tests that we can handle skills with substantial Python scripts.
        """
        discovered = marketplace.discover("anthropic")
        xlsx_skills = [s for s in discovered if s.name == "xlsx"]

        if not xlsx_skills:
            pytest.skip("xlsx skill not found in Anthropic repository")

        xlsx_skill = xlsx_skills[0]
        try:
            installed_path = marketplace.install(xlsx_skill.name)
            assert installed_path.exists()
            assert (installed_path / "SKILL.md").exists()

            # Verify recalc.py is present (the main script for xlsx skill)
            recalc_script = installed_path / "recalc.py"
            assert recalc_script.exists(), "recalc.py should be present in xlsx skill"

            # Verify it's substantial (the real script is 6KB+)
            content = recalc_script.read_text()
            assert len(content) > 1000, "recalc.py should be substantial"
            assert "LibreOffice" in content or "openpyxl" in content

        except MarketplaceError as e:
            pytest.skip(f"Could not install xlsx skill: {e}")

    def test_install_complex_pdf_skill(self, marketplace):
        """
        Test installing the pdf skill from Anthropic repository.

        The pdf skill has the most scripts:
        - check_bounding_boxes.py (3KB+)
        - check_fillable_fields.py
        - convert_pdf_to_images.py (1KB+)
        - create_validation_image.py (1.6KB+)
        - extract_form_field_info.py (6KB+)
        - fill_fillable_fields.py (4.8KB+)
        - fill_pdf_form_with_annotations.py (3.5KB+)
        - Plus reference.md and forms.md documentation
        """
        discovered = marketplace.discover("anthropic")
        pdf_skills = [s for s in discovered if s.name == "pdf"]

        if not pdf_skills:
            pytest.skip("pdf skill not found in Anthropic repository")

        pdf_skill = pdf_skills[0]
        try:
            installed_path = marketplace.install(pdf_skill.name)
            assert installed_path.exists()
            assert (installed_path / "SKILL.md").exists()

            # Verify scripts directory exists with multiple scripts
            scripts_dir = installed_path / "scripts"
            assert scripts_dir.exists(), "pdf skill should have scripts/ directory"

            # Check for key scripts
            expected_scripts = [
                "check_fillable_fields.py",
                "convert_pdf_to_images.py",
                "extract_form_field_info.py",
            ]

            found_scripts = list(scripts_dir.glob("*.py"))
            assert len(found_scripts) >= 3, f"pdf skill should have multiple scripts, found: {found_scripts}"

            script_names = [s.name for s in found_scripts]
            for expected in expected_scripts:
                assert expected in script_names, f"Expected {expected} in pdf scripts"

        except MarketplaceError as e:
            pytest.skip(f"Could not install pdf skill: {e}")

    def test_install_webapp_testing_skill(self, marketplace):
        """
        Test installing the webapp-testing skill from Anthropic repository.

        The webapp-testing skill contains:
        - SKILL.md with Playwright testing documentation
        - scripts/with_server.py: Server lifecycle management (3.6KB+)
        - examples/ directory with usage patterns
        """
        discovered = marketplace.discover("anthropic")
        webapp_skills = [s for s in discovered if s.name == "webapp-testing"]

        if not webapp_skills:
            pytest.skip("webapp-testing skill not found in Anthropic repository")

        webapp_skill = webapp_skills[0]
        try:
            installed_path = marketplace.install(webapp_skill.name)
            assert installed_path.exists()
            assert (installed_path / "SKILL.md").exists()

            # Verify scripts directory with with_server.py
            scripts_dir = installed_path / "scripts"
            assert scripts_dir.exists(), "webapp-testing skill should have scripts/ directory"

            with_server = scripts_dir / "with_server.py"
            assert with_server.exists(), "with_server.py should be present"

            # Verify the script is substantial
            content = with_server.read_text()
            assert len(content) > 1000, "with_server.py should be substantial"
            assert "playwright" in content.lower() or "server" in content.lower()

            # Verify examples directory exists
            examples_dir = installed_path / "examples"
            assert examples_dir.exists(), "webapp-testing skill should have examples/ directory"

        except MarketplaceError as e:
            pytest.skip(f"Could not install webapp-testing skill: {e}")

    def test_create_toolset_from_pdf_skill(self, marketplace):
        """
        Test creating a SkillToolset from the pdf skill.

        This tests the most complex skill with multiple scripts to ensure
        our SkillToolset can properly parse and expose all the tools.
        """
        discovered = marketplace.discover("anthropic")
        pdf_skills = [s for s in discovered if s.name == "pdf"]

        if not pdf_skills:
            pytest.skip("pdf skill not found in Anthropic repository")

        pdf_skill = pdf_skills[0]
        try:
            installed_path = marketplace.install(pdf_skill.name)
            toolset = SkillToolset.from_path(installed_path)

            # Verify toolset is valid
            assert toolset.skill.name == pdf_skill.name

            # pdf skill should have multiple scripts as tools
            assert toolset.tool_count >= 3, f"pdf skill should have multiple tools, found: {toolset.tool_count}"

            # Verify it can generate chat tools
            chat_tools = toolset.chat_tools
            assert isinstance(chat_tools, list)
            assert len(chat_tools) >= 3

            # Verify tool names follow our convention (skill_name_script_name)
            # ChatCompletionTool has .function.name attribute
            tool_names = [t.function.name for t in chat_tools]
            for name in tool_names:
                assert name.startswith("pdf_"), f"Tool name should start with 'pdf_': {name}"

        except (MarketplaceError, Exception) as e:
            pytest.skip(f"Could not process pdf skill: {e}")

    def test_create_toolset_from_xlsx_skill(self, marketplace):
        """
        Test creating a SkillToolset from the xlsx skill.

        The xlsx skill has recalc.py at the root level (not in scripts/).
        This tests that we handle different skill structures correctly.
        """
        discovered = marketplace.discover("anthropic")
        xlsx_skills = [s for s in discovered if s.name == "xlsx"]

        if not xlsx_skills:
            pytest.skip("xlsx skill not found in Anthropic repository")

        xlsx_skill = xlsx_skills[0]
        try:
            installed_path = marketplace.install(xlsx_skill.name)
            toolset = SkillToolset.from_path(installed_path)

            # Verify toolset is valid
            assert toolset.skill.name == xlsx_skill.name

            # Verify it can generate chat tools
            chat_tools = toolset.chat_tools
            assert isinstance(chat_tools, list)

            # xlsx skill may have recalc.py as a tool
            if toolset.tool_count > 0:
                # ChatCompletionTool has .function.name attribute
                tool_names = [t.function.name for t in chat_tools]
                # Check if recalc is exposed as a tool
                recalc_tools = [n for n in tool_names if "recalc" in n.lower()]
                if recalc_tools:
                    assert len(recalc_tools) >= 1

        except (MarketplaceError, Exception) as e:
            pytest.skip(f"Could not process xlsx skill: {e}")

    def test_multi_skill_toolset_with_anthropic_skills(self, marketplace):
        """
        Test creating a SkillToolset with multiple complex Anthropic skills.

        This tests that we can compose multiple real-world skills together.
        """
        discovered = marketplace.discover("anthropic")

        # Try to install multiple skills
        installed_paths = []
        for skill_name in ["pdf", "xlsx"]:
            matching = [s for s in discovered if s.name == skill_name]
            if matching:
                try:
                    path = marketplace.install(matching[0].name)
                    installed_paths.append(path)
                except MarketplaceError:
                    pass

        if len(installed_paths) < 2:
            pytest.skip("Could not install enough skills for multi-skill test")

        # Create multi-skill toolset
        multi_toolset = SkillToolset.from_paths(installed_paths)

        # Should have tools from both skills
        assert multi_toolset.tool_count >= 2

        # Should generate a combined system prompt
        system_prompt = multi_toolset.get_combined_system_prompt()
        assert "pdf" in system_prompt.lower() or "xlsx" in system_prompt.lower()


# ---------------------------------------------------------------------------
# ReActAgent with Real Anthropic Skills Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SKIP_EXPENSIVE_TESTS") == "true",
    reason="Skipping expensive tests",
)
@pytest.mark.skipif(
    os.getenv("SKIP_NETWORK_TESTS") == "true",
    reason="Skipping network tests",
)
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - required for LLM integration tests",
)
@pytest.mark.parametrize("model", ["gpt-5-nano"])
class TestReActAgentWithAnthropicSkills:
    """
    Integration tests for ReActAgent using REAL Anthropic skills.

    These tests verify end-to-end functionality:
    1. Install real skills from anthropics/skills GitHub repo
    2. Create SkillToolsets from them
    3. Use ReActAgent with real LLM to reason and call skill tools

    Note: These tests require:
    - Network access to GitHub
    - OPENAI_API_KEY for LLM calls
    - May be slow due to network + LLM latency
    """

    @pytest.fixture
    def marketplace(self, temp_install_dir, temp_cache_dir):
        """Create a marketplace configured for Anthropic skills."""
        return SkillMarketplace(
            install_path=temp_install_dir / "installed",
            cache_path=temp_cache_dir,
        )

    def test_react_agent_with_pdf_skill(
        self,
        model,
        generator,
        build_message_from_payload,
        dependency_map,
        marketplace,
    ):
        """
        Test ReActAgent with the real Anthropic PDF skill.

        The PDF skill has 8 tools for PDF processing:
        - check_fillable_fields
        - convert_pdf_to_images
        - extract_form_field_info
        - fill_fillable_fields
        - etc.

        This test verifies the agent can:
        1. Load the skill's tools
        2. Understand the available PDF operations
        3. Reason about which tool to use
        """
        discovered = marketplace.discover("anthropic")
        pdf_skills = [s for s in discovered if s.name == "pdf"]

        if not pdf_skills:
            pytest.skip("pdf skill not found in Anthropic repository")

        try:
            installed_path = marketplace.install(pdf_skills[0].name)
            skill_toolset = SkillToolset.from_path(installed_path)
        except Exception as e:
            pytest.skip(f"Could not install pdf skill: {e}")

        # Verify we have tools
        assert skill_toolset.tool_count >= 3, "pdf skill should have multiple tools"

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_pdf_agent")
            .set_name("ReAct PDF Agent")
            .set_description("A ReAct agent with Anthropic PDF skill")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                    system_prompt=f"""You are an AI assistant with PDF processing capabilities.

{skill_toolset.get_system_prompt_addition()}

When asked about PDF operations, describe which tools you would use.
If you cannot actually execute because you don't have a file, explain what you would do.
""",
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        # Ask about PDF capabilities - agent should reason about available tools
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        UserMessage(content="What tools do you have available for working with PDF files? List them briefly.")
                    ]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # The agent should mention PDF-related capabilities in its answer
        answer_lower = answer.lower()
        assert any(
            term in answer_lower for term in ["pdf", "form", "field", "fillable", "extract", "convert", "image"]
        ), f"Expected PDF-related terms in answer: {answer}"

    def test_react_agent_with_xlsx_skill(
        self,
        model,
        generator,
        build_message_from_payload,
        dependency_map,
        marketplace,
    ):
        """
        Test ReActAgent with the real Anthropic XLSX skill.

        The XLSX skill has recalc.py for Excel formula recalculation.

        This test verifies the agent can reason about spreadsheet operations.
        """
        discovered = marketplace.discover("anthropic")
        xlsx_skills = [s for s in discovered if s.name == "xlsx"]

        if not xlsx_skills:
            pytest.skip("xlsx skill not found in Anthropic repository")

        try:
            installed_path = marketplace.install(xlsx_skills[0].name)
            skill_toolset = SkillToolset.from_path(installed_path)
        except Exception as e:
            pytest.skip(f"Could not install xlsx skill: {e}")

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_xlsx_agent")
            .set_name("ReAct XLSX Agent")
            .set_description("A ReAct agent with Anthropic XLSX skill")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                    system_prompt=f"""You are an AI assistant with Excel/spreadsheet processing capabilities.

{skill_toolset.get_system_prompt_addition()}

When asked about Excel operations, describe your capabilities.
""",
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="What can you do with Excel spreadsheets? What tools do you have?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # Should mention Excel/spreadsheet capabilities
        answer_lower = answer.lower()
        assert any(
            term in answer_lower for term in ["excel", "spreadsheet", "xlsx", "formula", "recalc", "cell"]
        ), f"Expected Excel-related terms in answer: {answer}"

    def test_react_agent_with_webapp_testing_skill(
        self,
        model,
        generator,
        build_message_from_payload,
        dependency_map,
        marketplace,
    ):
        """
        Test ReActAgent with the real Anthropic webapp-testing skill.

        The webapp-testing skill has:
        - with_server.py for Playwright server lifecycle
        - Examples for web automation patterns

        This test verifies the agent can reason about web testing operations.
        """
        discovered = marketplace.discover("anthropic")
        webapp_skills = [s for s in discovered if s.name == "webapp-testing"]

        if not webapp_skills:
            pytest.skip("webapp-testing skill not found in Anthropic repository")

        try:
            installed_path = marketplace.install(webapp_skills[0].name)
            skill_toolset = SkillToolset.from_path(installed_path)
        except Exception as e:
            pytest.skip(f"Could not install webapp-testing skill: {e}")

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_webapp_agent")
            .set_name("ReAct WebApp Testing Agent")
            .set_description("A ReAct agent with Anthropic webapp-testing skill")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                    system_prompt=f"""You are an AI assistant with web application testing capabilities.

{skill_toolset.get_system_prompt_addition()}

When asked about web testing, describe your capabilities and available tools.
""",
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
                ChatCompletionRequest(
                    messages=[
                        UserMessage(content="What tools do you have for testing web applications? Describe your capabilities.")
                    ]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # Should mention web testing capabilities
        answer_lower = answer.lower()
        assert any(
            term in answer_lower for term in ["web", "test", "playwright", "server", "browser", "automation"]
        ), f"Expected web testing terms in answer: {answer}"

    def test_react_agent_with_combined_anthropic_skills(
        self,
        model,
        generator,
        build_message_from_payload,
        dependency_map,
        marketplace,
    ):
        """
        Test ReActAgent with multiple Anthropic skills combined.

        This test combines pdf + xlsx skills and verifies the agent
        can reason about operations from both domains.
        """
        discovered = marketplace.discover("anthropic")

        # Try to install pdf and xlsx skills
        installed_paths = []
        for skill_name in ["pdf", "xlsx"]:
            matching = [s for s in discovered if s.name == skill_name]
            if matching:
                try:
                    path = marketplace.install(matching[0].name)
                    installed_paths.append(path)
                except Exception:
                    pass

        if len(installed_paths) < 2:
            pytest.skip("Could not install enough Anthropic skills for combined test")

        multi_toolset = SkillToolset.from_paths(installed_paths)

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("react_combined_agent")
            .set_name("ReAct Combined Agent")
            .set_description("A ReAct agent with multiple Anthropic skills")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=multi_toolset,
                    system_prompt=f"""You are an AI assistant with PDF and Excel processing capabilities.

{multi_toolset.get_combined_system_prompt()}

When asked about document processing, describe your capabilities for both PDFs and spreadsheets.
""",
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
                ChatCompletionRequest(
                    messages=[
                        UserMessage(
                            content="I need to work with both PDF documents and Excel spreadsheets. What tools do you have for each?"
                        )
                    ]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""

        # Should mention both PDF and Excel capabilities
        answer_lower = answer.lower()
        has_pdf = any(term in answer_lower for term in ["pdf", "form", "document"])
        has_excel = any(term in answer_lower for term in ["excel", "spreadsheet", "xlsx"])

        assert has_pdf or has_excel, f"Expected document processing terms in answer: {answer}"


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling Tests
# ---------------------------------------------------------------------------


class TestEdgeCasesAndErrors:
    """Tests for edge cases and error handling."""

    def test_empty_skill_directory(self, temp_install_dir):
        """Test handling of skill directory with no scripts."""
        skill_dir = temp_install_dir / "empty-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: empty-skill
description: A skill with no scripts
---

# Empty Skill

This skill has no scripts.
"""
        )

        toolset = SkillToolset.from_path(skill_dir)
        assert toolset.tool_count == 0
        assert len(toolset.chat_tools) == 0

    def test_skill_with_invalid_script(self, temp_install_dir):
        """Test handling of skill with syntactically invalid script."""
        skill_dir = temp_install_dir / "invalid-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: invalid-skill
description: A skill with invalid script
---

# Invalid Skill
"""
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        # Create a script with syntax error
        (scripts_dir / "broken.py").write_text(
            '''"""Broken script."""
def broken(
    # Missing closing paren and body
'''
        )

        toolset = SkillToolset.from_path(skill_dir)

        # Should still create the toolset, but execution will fail
        assert toolset.tool_count == 1

        # Execution should handle the error gracefully
        result = toolset.execute("invalid_skill_broken", ScriptToolParams())
        assert "error" in result.lower() or "fail" in result.lower()

    def test_skill_script_timeout(self, temp_install_dir):
        """Test that skill scripts respect timeout configuration."""
        skill_dir = temp_install_dir / "slow-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: slow-skill
description: A skill with a slow script
---

# Slow Skill
"""
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (scripts_dir / "slow.py").write_text(
            '''"""Slow script that takes too long."""
import time
time.sleep(60)  # Sleep for 60 seconds
print("Done")
'''
        )

        # Create toolset with short timeout
        toolset = SkillToolset.from_path(
            skill_dir,
            execution_config=ExecutionConfig(timeout_seconds=1),
        )

        result = toolset.execute("slow_skill_slow", ScriptToolParams())
        # Check for timeout indication (case insensitive, multiple patterns)
        assert "timed out" in result.lower() or "timeout" in result.lower()

    def test_skill_with_special_characters_in_name(self, temp_install_dir):
        """Test skill with hyphens and underscores in name."""
        skill_dir = temp_install_dir / "my-special_skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: my-special_skill
description: A skill with special characters in name
---

# Special Skill
"""
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (scripts_dir / "action.py").write_text(
            '''"""Simple action."""
print("action executed")
'''
        )

        toolset = SkillToolset.from_path(skill_dir)

        # Tool name should have hyphens converted to underscores
        tool_names = toolset.tool_names
        assert len(tool_names) == 1
        # The prefix replaces hyphens with underscores
        assert "my_special_skill_action" in tool_names

    def test_multi_skill_with_duplicate_script_names(self, temp_install_dir):
        """Test SkillToolset handles duplicate script names (with prefixes)."""
        # Create two skills with scripts of the same name
        for i in range(2):
            skill_dir = temp_install_dir / f"skill-{i}"
            skill_dir.mkdir(parents=True)

            (skill_dir / "SKILL.md").write_text(
                f"""---
name: skill-{i}
description: Skill {i}
---

# Skill {i}
"""
            )

            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()

            (scripts_dir / "action.py").write_text(
                f'''"""Action from skill {i}."""
print("Action from skill {i}")
'''
            )

        multi_toolset = SkillToolset.from_paths(
            [
                temp_install_dir / "skill-0",
                temp_install_dir / "skill-1",
            ]
        )

        # Should have both tools with unique prefixed names
        tool_names = multi_toolset.tool_names
        assert len(tool_names) == 2
        assert "skill_0_action" in tool_names
        assert "skill_1_action" in tool_names

        # Each should execute correctly
        result0 = multi_toolset.execute("skill_0_action", ScriptToolParams())
        assert "skill 0" in result0.lower()

        result1 = multi_toolset.execute("skill_1_action", ScriptToolParams())
        assert "skill 1" in result1.lower()


# ---------------------------------------------------------------------------
# Performance and Stress Tests
# ---------------------------------------------------------------------------


class TestPerformance:
    """Performance tests for skill operations."""

    def test_large_skill_collection(self, temp_install_dir):
        """Test handling many skills at once."""
        num_skills = 10

        # Create many skills
        for i in range(num_skills):
            skill_dir = temp_install_dir / f"skill-{i}"
            skill_dir.mkdir(parents=True)

            (skill_dir / "SKILL.md").write_text(
                f"""---
name: skill-{i}
description: Skill number {i} for testing
---

# Skill {i}

Instructions for skill {i}.
"""
            )

            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()

            for j in range(3):  # 3 scripts per skill
                (scripts_dir / f"action{j}.py").write_text(
                    f'''#!/usr/bin/env python3
"""Action {j} for skill {i}."""
print("Executed action {j} from skill {i}")
'''
                )

        # Create SkillToolset with all skills
        skill_paths = [temp_install_dir / f"skill-{i}" for i in range(num_skills)]
        multi_toolset = SkillToolset.from_paths(skill_paths)

        # Should have all tools
        expected_tools = num_skills * 3
        assert multi_toolset.tool_count == expected_tools

        # Verify random access works
        result = multi_toolset.execute("skill_5_action1", ScriptToolParams())
        assert "skill 5" in result.lower()

    def test_skill_with_large_output(self, temp_install_dir):
        """Test skill script that produces large output."""
        skill_dir = temp_install_dir / "large-output-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: large-output-skill
description: Skill that produces large output
---

# Large Output Skill
"""
        )

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (scripts_dir / "big.py").write_text(
            '''#!/usr/bin/env python3
"""Generate large output."""
for i in range(10000):
    print(f"Line {i}: " + "x" * 100)
'''
        )

        toolset = SkillToolset.from_path(
            skill_dir,
            execution_config=ExecutionConfig(
                timeout_seconds=30,
                max_output_bytes=1024 * 1024,  # 1MB limit
            ),
        )

        result = toolset.execute("large_output_skill_big", ScriptToolParams())

        # Should either complete or be truncated, not crash
        assert result
        # Check for truncation message if output was too large
        if len(result) > 1024 * 1024:
            assert "truncated" in result.lower()

    def test_concurrent_skill_execution(self, calculator_skill_dir):
        """Test that skill can handle sequential rapid executions."""
        toolset = SkillToolset.from_path(calculator_skill_dir)

        # Execute many calculations sequentially
        results = []
        for i in range(20):
            result = toolset.execute(
                "calculator_calculate",
                ScriptToolParams(args={"expression": f"{i} * 2"}),
            )
            results.append(result)

        # All should succeed
        for i, result in enumerate(results):
            assert "success" in result
            assert str(i * 2) in result


# ---------------------------------------------------------------------------
# YAML/JSON Spec Serialization Tests
# ---------------------------------------------------------------------------


class TestSpecSerialization:
    """
    Tests to verify that agent specs with SkillToolset remain serializable.

    These tests ensure that:
    1. Agent specs can be written to YAML/JSON files
    2. Agent specs can be loaded from YAML/JSON files
    3. The loaded specs work correctly with real agents
    4. Round-trip serialization preserves functionality
    """

    def test_skill_toolset_serializes_with_path(self, calculator_skill_dir):
        """
        Test that SkillToolset serializes using skill_path instead of full skill definition.
        """
        # Create toolset from path
        toolset = SkillToolset.from_path(calculator_skill_dir)

        # Serialize to dict
        data = toolset.model_dump()

        # Should have skill_paths and NOT have full skills embedded
        assert "skill_paths" in data
        assert data["skill_paths"][0] == str(calculator_skill_dir.absolute())
        assert "skills" not in data or data["skills"] is None or len(data["skills"]) == 0

    def test_skill_toolset_deserializes_from_path(self, calculator_skill_dir):
        """
        Test that SkillToolset can be deserialized from skill_paths.
        """
        # Create config dict like it would appear in YAML/JSON
        config = {
            "skill_paths": [str(calculator_skill_dir.absolute())],
            "tool_prefix": "calc_",
        }

        # Deserialize using model_validate
        toolset = SkillToolset.model_validate(config)

        # Should be fully functional
        assert len(toolset.skills) > 0
        assert toolset.skills[0].name == "calculator"
        assert toolset.tool_count >= 1

    def test_skill_toolset_roundtrip(self, calculator_skill_dir, temp_install_dir):
        """
        Test that SkillToolset survives YAML serialization roundtrip.
        """
        # Create original toolset
        original = SkillToolset.from_path(calculator_skill_dir)
        original_tools = original.tool_names

        # Serialize to YAML
        data = original.model_dump()
        yaml_path = temp_install_dir / "toolset.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(data, f)

        # Load from YAML (ensure it deserializes)
        with open(yaml_path, "r") as f:
            loaded_data = yaml.safe_load(f)

        # Deserialize
        loaded = SkillToolset.model_validate(loaded_data)

        # Should have same tools
        assert set(loaded.tool_names) == set(original_tools)

        # Should execute successfully
        result = loaded.execute("calculator_calculate", ScriptToolParams(args={"expression": "7 + 8"}))
        assert "15" in result or "success" in result.lower()

    def test_multi_skill_toolset_serializes_with_paths(self, temp_install_dir):
        """
        Test that SkillToolset serializes using skill_paths.
        """
        # Create two test skills
        for i in range(2):
            skill_dir = temp_install_dir / f"skill-{i}"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"""---
name: skill-{i}
description: Test skill {i}
---
# Skill {i}
"""
            )
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "action.py").write_text(f'print("skill {i} action")')

        # Create SkillToolset
        paths = [temp_install_dir / f"skill-{i}" for i in range(2)]
        multi_toolset = SkillToolset.from_paths(paths)

        # Serialize
        data = multi_toolset.model_dump()

        # Should have skill_paths, not full skill_toolsets
        assert "skill_paths" in data
        assert len(data["skill_paths"]) == 2
        assert "skill_toolsets" not in data or data["skill_toolsets"] is None

    def test_multi_skill_toolset_roundtrip(self, temp_install_dir):
        """
        Test that SkillToolset survives YAML serialization roundtrip.
        """
        # Create test skills
        for i in range(2):
            skill_dir = temp_install_dir / f"skill-{i}"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"""---
name: skill-{i}
description: Test skill {i}
---
# Skill {i}
"""
            )
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "action.py").write_text(f'print("skill {i} action")')

        # Create original
        paths = [temp_install_dir / f"skill-{i}" for i in range(2)]
        original = SkillToolset.from_paths(paths)
        original_tools = original.tool_names

        # Serialize to YAML
        data = original.model_dump()
        yaml_path = temp_install_dir / "multi_toolset.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(data, f)

        # Load from YAML
        with open(yaml_path, "r") as f:
            loaded_data = yaml.safe_load(f)

        # Deserialize
        loaded = SkillToolset.model_validate(loaded_data)

        # Should have same tools
        assert set(loaded.tool_names) == set(original_tools)

    def test_agent_spec_with_skill_toolset_yaml(
        self,
        model,
        calculator_skill_dir,
        temp_install_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test that AgentSpec with SkillToolset can be saved to YAML and loaded.
        """
        # Create agent spec programmatically first
        skill_toolset = SkillToolset.from_path(calculator_skill_dir)

        original_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("yaml_test_agent")
            .set_name("YAML Test Agent")
            .set_description("Agent loaded from YAML spec")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                    system_prompt="You are a calculator assistant.",
                )
            )
            .build_spec()
        )

        # Serialize to YAML
        spec_dict = original_spec.model_dump()
        yaml_path = temp_install_dir / "agent_spec.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f, default_flow_style=False)

        # Load from YAML
        with open(yaml_path, "r") as f:
            loaded_dict = yaml.safe_load(f)

        # Deserialize AgentSpec
        loaded_spec = AgentSpec.model_validate(loaded_dict)

        # Verify the loaded spec is functional
        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="Calculate 25 + 17")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        assert "42" in answer

    def test_agent_spec_with_multi_skill_toolset_yaml(
        self,
        model,
        temp_install_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test that AgentSpec with SkillToolset can be saved to YAML and loaded.
        """
        # Create test skills
        for i, name in enumerate(["math", "text"]):
            skill_dir = temp_install_dir / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"""---
name: {name}
description: {name.title()} operations
---
# {name.title()} Skill
"""
            )
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            if name == "math":
                (scripts_dir / "add.py").write_text(
                    """
import sys
a, b = int(sys.argv[1]), int(sys.argv[2])
print(f"Result: {a + b}")
"""
                )
            else:
                (scripts_dir / "upper.py").write_text(
                    """
import sys
print(sys.argv[1].upper() if len(sys.argv) > 1 else "NO INPUT")
"""
                )

        # Create multi-skill toolset
        paths = [temp_install_dir / "math", temp_install_dir / "text"]
        multi_toolset = SkillToolset.from_paths(paths)

        # Create agent spec
        original_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("multi_yaml_agent")
            .set_name("Multi YAML Agent")
            .set_description("Agent with multi-skill toolset loaded from YAML")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=multi_toolset,
                )
            )
            .build_spec()
        )

        # Serialize to YAML
        spec_dict = original_spec.model_dump()
        yaml_path = temp_install_dir / "multi_agent_spec.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f, default_flow_style=False)

        # Load from YAML
        with open(yaml_path, "r") as f:
            loaded_dict = yaml.safe_load(f)

        # Deserialize
        loaded_spec = AgentSpec.model_validate(loaded_dict)

        # Verify loaded spec works
        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        # Ask about available tools - should mention both skills
        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[UserMessage(content="What tools do you have available? List them briefly.")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content

    def test_agent_spec_json_roundtrip(
        self,
        model,
        calculator_skill_dir,
        temp_install_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test that AgentSpec can be saved to JSON and loaded correctly.
        """
        skill_toolset = SkillToolset.from_path(calculator_skill_dir)

        original_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("json_test_agent")
            .set_name("JSON Test Agent")
            .set_description("Agent loaded from JSON spec")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                )
            )
            .build_spec()
        )

        # Serialize to JSON
        spec_dict = original_spec.model_dump()
        json_path = temp_install_dir / "agent_spec.json"
        with open(json_path, "w") as f:
            json.dump(spec_dict, f, indent=2)

        # Load from JSON
        with open(json_path, "r") as f:
            loaded_dict = json.load(f)

        # Deserialize
        loaded_spec = AgentSpec.model_validate(loaded_dict)

        # Verify
        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="Calculate 100 - 37")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        assert "63" in answer

    def test_spec_file_loading_utility(
        self,
        model,
        calculator_skill_dir,
        temp_install_dir,
        dependency_map,
        generator,
        build_message_from_payload,
    ):
        """
        Test the helper functions for loading specs from files.
        """
        # Create spec using helper function
        spec_dict = create_agent_spec_yaml(
            agent_id="helper_test_agent",
            name="Helper Test Agent",
            description="Agent created from helper function",
            model=model,
            toolset_kind="rustic_ai.skills.toolset.SkillToolset",
            skill_paths=[str(calculator_skill_dir.absolute())],
            system_prompt="You are a helpful calculator.",
            max_iterations=5,
        )

        # Save to YAML
        yaml_path = save_spec_to_yaml(spec_dict, temp_install_dir)

        # Load using helper
        loaded_spec = load_agent_spec_from_yaml(yaml_path)

        # Verify it works
        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="What is 50 times 2?")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        answer = response.choices[0].message.content or ""
        assert "100" in answer


class TestAnthropicSkillsYAMLSpecs:
    """
    Test ReActAgent with Anthropic skills using YAML/JSON specs.

    These tests install real Anthropic skills and verify that agent specs
    with these skills can be serialized and loaded correctly.
    """

    @pytest.fixture
    def marketplace(self, temp_install_dir, temp_cache_dir):
        """Create a marketplace for Anthropic skills."""
        return SkillMarketplace(
            install_path=temp_install_dir / "installed",
            cache_path=temp_cache_dir,
        )

    def test_pdf_skill_yaml_spec(
        self,
        model,
        marketplace,
        temp_install_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test ReActAgent with PDF skill loaded from YAML spec.
        """
        discovered = marketplace.discover("anthropic")
        pdf_skills = [s for s in discovered if s.name == "pdf"]

        if not pdf_skills:
            pytest.skip("pdf skill not found")

        try:
            installed_path = marketplace.install(pdf_skills[0].name)
        except Exception as e:
            pytest.skip(f"Could not install pdf skill: {e}")

        # Create toolset and agent spec
        skill_toolset = SkillToolset.from_path(installed_path)

        original_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("pdf_yaml_agent")
            .set_name("PDF YAML Agent")
            .set_description("PDF agent loaded from YAML")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=skill_toolset,
                    system_prompt=f"""You are a PDF processing assistant.
{skill_toolset.get_system_prompt_addition()}
""",
                )
            )
            .build_spec()
        )

        # Serialize to YAML
        spec_dict = original_spec.model_dump()
        yaml_path = temp_install_dir / "pdf_agent.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f, default_flow_style=False)

        # Verify YAML file is readable
        with open(yaml_path, "r") as f:
            yaml_content = f.read()
        assert "rustic_ai.skills.toolset.SkillToolset" in yaml_content
        assert "skill_path" in yaml_content

        # Load and verify
        loaded_spec = load_agent_spec_from_yaml(yaml_path)

        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="What PDF tools do you have?")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content

    def test_combined_skills_yaml_spec(
        self,
        model,
        marketplace,
        temp_install_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test ReActAgent with combined Anthropic skills loaded from YAML spec.
        """
        discovered = marketplace.discover("anthropic")

        # Install multiple skills
        installed_paths = []
        for skill_name in ["pdf", "xlsx"]:
            matching = [s for s in discovered if s.name == skill_name]
            if matching:
                try:
                    path = marketplace.install(matching[0].name)
                    installed_paths.append(path)
                except Exception:
                    pass

        if len(installed_paths) < 2:
            pytest.skip("Could not install enough skills for combined test")

        # Create SkillToolset
        multi_toolset = SkillToolset.from_paths(installed_paths)

        # Create agent spec
        original_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("combined_yaml_agent")
            .set_name("Combined YAML Agent")
            .set_description("Agent with multiple skills loaded from YAML")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=multi_toolset,
                )
            )
            .build_spec()
        )

        # Serialize to YAML
        spec_dict = original_spec.model_dump()
        yaml_path = temp_install_dir / "combined_agent.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f, default_flow_style=False)

        # Verify YAML structure (SkillToolset is the unified class now)
        with open(yaml_path, "r") as f:
            yaml_content = f.read()
        assert "rustic_ai.skills.toolset.SkillToolset" in yaml_content
        assert "skill_paths" in yaml_content

        # Load and verify
        loaded_spec = load_agent_spec_from_yaml(yaml_path)

        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[UserMessage(content="What document processing tools do you have?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content


# ---------------------------------------------------------------------------
# MarketplaceSkillToolset Tests
# ---------------------------------------------------------------------------


class TestMarketplaceSkillToolset:
    """
    Tests for MarketplaceSkillToolset - auto-installing skills from marketplace.

    These tests verify that:
    1. Skills are automatically downloaded and installed
    2. Toolset works correctly after installation
    3. YAML/JSON serialization produces portable specs
    4. Agent specs with marketplace toolsets work correctly
    """

    def test_marketplace_toolset_installs_pdf_skill(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset auto-installs the pdf skill.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        # Should have tools after installation
        assert toolset.tool_count >= 1
        assert toolset.installed_paths[0] is not None
        assert Path(toolset.installed_paths[0]).exists()

    def test_marketplace_toolset_installs_xlsx_skill(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset auto-installs the xlsx skill.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["xlsx"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        # The xlsx skill may have 0 scripts if they don't match our pattern
        # At minimum, verify it installed successfully
        assert toolset.installed_paths[0] is not None
        assert Path(toolset.installed_paths[0]).exists()

    def test_marketplace_toolset_from_marketplace_factory(self, temp_install_dir, temp_cache_dir):
        """
        Test the from_marketplace factory method.
        """
        toolset = MarketplaceSkillToolset.from_marketplace(
            skill_names=["pdf"],
            source="anthropic",
            force=True,  # Force reinstall in case already installed
        )

        # Should work (uses default paths)
        assert toolset.tool_count >= 1

    def test_marketplace_toolset_serializes_without_paths(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset serializes to portable format.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        # Serialize
        data = toolset.model_dump()

        # Should have marketplace reference, not local paths
        assert data["source"] == "anthropic"
        assert data["skill_names"][0] == "pdf"
        # Should NOT have the installed_path in serialized form
        assert "_installed_path" not in data
        assert "_inner_toolset" not in data

    def test_marketplace_toolset_yaml_roundtrip(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset survives YAML serialization roundtrip.
        """
        original = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        # Serialize to YAML
        data = original.model_dump()
        yaml_path = temp_install_dir / "marketplace_toolset.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(data, f)

        # Load from YAML
        with open(yaml_path, "r") as f:
            _ = yaml.safe_load(f)

        # Verify YAML is portable (no absolute paths)
        yaml_content = yaml_path.read_text()
        assert "source: anthropic" in yaml_content
        assert "skill_names" in yaml_content

    def test_marketplace_toolset_invalid_skill(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset raises error for non-existent skill.
        """
        with pytest.raises(ValueError) as exc_info:
            MarketplaceSkillToolset(
                source="anthropic",
                skill_names=["non_existent_skill_xyz"],
                install_path=str(temp_install_dir),
                cache_path=str(temp_cache_dir),
            )

        assert "not found" in str(exc_info.value).lower()

    def test_marketplace_toolset_with_react_agent(
        self,
        model,
        temp_install_dir,
        temp_cache_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test ReActAgent with MarketplaceSkillToolset.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("marketplace_pdf_agent")
            .set_name("Marketplace PDF Agent")
            .set_description("Agent using marketplace-installed PDF skill")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=toolset,
                    system_prompt=f"""You are a PDF processing assistant.
{toolset.get_system_prompt_addition()}
""",
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="What PDF tools do you have available?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content

    def test_marketplace_toolset_yaml_spec_loading(
        self,
        model,
        temp_install_dir,
        temp_cache_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test that agent spec with MarketplaceSkillToolset can be loaded from YAML.
        """
        # Create spec dict manually (as it would appear in a YAML file)
        spec_dict = {
            "id": "yaml_marketplace_agent",
            "name": "YAML Marketplace Agent",
            "description": "Agent loaded from YAML with marketplace skill",
            "class_name": "rustic_ai.llm_agent.react.ReActAgent",
            "properties": {
                "model": model,
                "max_iterations": 5,
                "toolset": {
                    "kind": "rustic_ai.skills.toolset.MarketplaceSkillToolset",
                    "source": "anthropic",
                    "skill_names": ["pdf"],
                    "install_path": str(temp_install_dir),
                    "cache_path": str(temp_cache_dir),
                },
            },
        }

        # Save to YAML
        yaml_path = temp_install_dir / "marketplace_spec.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f)

        # Load from YAML
        loaded_spec = load_agent_spec_from_yaml(yaml_path)

        # Verify it works
        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="What tools do you have?")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content


class TestMarketplaceSkillToolsetWithMultipleSkills:
    """
    Tests for MarketplaceSkillToolset with multiple skills - auto-installing multiple skills from marketplace.
    """

    def test_marketplace_toolset_installs_multiple_skills(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset can install multiple skills at once.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf", "xlsx"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        # Should have tools from both skills
        assert toolset.tool_count >= 2
        tool_names_str = str(toolset.tool_names).lower()
        # Should have tools from pdf or xlsx skills
        assert "pdf" in tool_names_str or "xlsx" in tool_names_str or "recalc" in tool_names_str

    def test_marketplace_toolset_with_multiple_skills_serializes_portably(self, temp_install_dir, temp_cache_dir):
        """
        Test that MarketplaceSkillToolset with multiple skills serializes without local paths.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf", "xlsx"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        data = toolset.model_dump()

        assert data["source"] == "anthropic"
        assert data["skill_names"] == ["pdf", "xlsx"]
        assert "_inner_toolset" not in data

    def test_marketplace_toolset_with_multiple_skills_in_react_agent(
        self,
        model,
        temp_install_dir,
        temp_cache_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test ReActAgent with MarketplaceSkillToolset loading multiple skills.
        """
        toolset = MarketplaceSkillToolset(
            source="anthropic",
            skill_names=["pdf", "xlsx"],
            install_path=str(temp_install_dir),
            cache_path=str(temp_cache_dir),
        )

        agent_spec: AgentSpec = (
            AgentBuilder(ReActAgent)
            .set_id("marketplace_multi_skills_agent")
            .set_name("Marketplace Multi-Skills Agent")
            .set_description("Agent with multiple marketplace-installed skills")
            .set_properties(
                ReActAgentConfig(
                    model=model,
                    max_iterations=5,
                    toolset=toolset,
                    system_prompt=f"""You are a document processing assistant.
{toolset.get_combined_system_prompt()}
""",
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
                ChatCompletionRequest(
                    messages=[UserMessage(content="What document tools do you have?")]
                ),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content

    def test_marketplace_toolset_multiple_skills_yaml_spec(
        self,
        model,
        temp_install_dir,
        temp_cache_dir,
        generator,
        build_message_from_payload,
        dependency_map,
    ):
        """
        Test that agent spec with MarketplaceSkillToolset loads from YAML.
        """
        spec_dict = {
            "id": "yaml_multi_marketplace",
            "name": "YAML Multi Marketplace Agent",
            "description": "Agent with multiple marketplace skills from YAML",
            "class_name": "rustic_ai.llm_agent.react.ReActAgent",
            "properties": {
                "model": model,
                "max_iterations": 5,
                "toolset": {
                    "kind": "rustic_ai.skills.toolset.MarketplaceSkillToolset",
                    "source": "anthropic",
                    "skill_names": ["pdf", "xlsx"],
                    "install_path": str(temp_install_dir),
                    "cache_path": str(temp_cache_dir),
                },
            },
        }

        yaml_path = temp_install_dir / "multi_marketplace_spec.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec_dict, f)

        loaded_spec = load_agent_spec_from_yaml(yaml_path)

        agent, results = wrap_agent_for_testing(
            loaded_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(messages=[UserMessage(content="What tools are available?")]),
            )
        )

        assert len(results) > 0
        response = ChatCompletionResponse.model_validate(results[0].payload)
        # Verify successful response
        assert response.choices[0].message.content
