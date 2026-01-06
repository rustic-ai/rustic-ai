"""Tests for skills executor."""

import json
import os

import pytest

from rustic_ai.skills.executor import (
    ExecutionConfig,
    ExecutionResult,
    ScriptExecutor,
    SkillScriptRunner,
)
from rustic_ai.skills.models import SkillScript


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_success_result(self):
        """Test successful execution result."""
        result = ExecutionResult(
            success=True,
            output="Hello World",
            exit_code=0,
        )
        assert result.success
        assert result.output == "Hello World"
        assert result.error is None

    def test_failure_result(self):
        """Test failed execution result."""
        result = ExecutionResult(
            success=False,
            output="",
            error="Command not found",
            exit_code=127,
        )
        assert not result.success
        assert result.error == "Command not found"


class TestExecutionConfig:
    """Tests for ExecutionConfig model."""

    def test_defaults(self):
        """Test default configuration values."""
        config = ExecutionConfig()
        assert config.timeout_seconds == 30
        assert config.capture_stderr is True
        assert config.max_output_bytes == 1024 * 1024

    def test_custom_config(self):
        """Test custom configuration."""
        config = ExecutionConfig(
            timeout_seconds=60,
            env_vars={"MY_VAR": "value"},
            capture_stderr=False,
        )
        assert config.timeout_seconds == 60
        assert config.env_vars == {"MY_VAR": "value"}
        assert config.capture_stderr is False


class TestScriptExecutor:
    """Tests for ScriptExecutor class."""

    def test_execute_python_script(self, temp_dir):
        """Test executing a Python script."""
        script_path = temp_dir / "test.py"
        script_path.write_text('print("Hello from Python")')

        script = SkillScript(
            name="test",
            path=script_path,
            extension=".py",
        )

        executor = ScriptExecutor()
        result = executor.execute(script)

        assert result.success
        assert "Hello from Python" in result.output
        assert result.exit_code == 0

    def test_execute_shell_script(self, temp_dir):
        """Test executing a shell script."""
        script_path = temp_dir / "test.sh"
        script_path.write_text('#!/bin/bash\necho "Hello from Bash"')
        script_path.chmod(0o755)

        script = SkillScript(
            name="test",
            path=script_path,
            extension=".sh",
        )

        executor = ScriptExecutor()
        result = executor.execute(script)

        assert result.success
        assert "Hello from Bash" in result.output

    def test_execute_with_args(self, temp_dir):
        """Test executing script with arguments."""
        script_path = temp_dir / "args_test.py"
        script_path.write_text("""
import json
import os

args = json.loads(os.environ.get("SKILL_ARGS", "{}"))
print(f"Got args: {args}")
""")

        script = SkillScript(
            name="args_test",
            path=script_path,
            extension=".py",
        )

        executor = ScriptExecutor()
        result = executor.execute(script, args={"input": "test", "count": 42})

        assert result.success
        assert "Got args:" in result.output
        assert "input" in result.output

    def test_execute_script_error(self, temp_dir):
        """Test handling script errors."""
        script_path = temp_dir / "error.py"
        script_path.write_text("raise ValueError('Test error')")

        script = SkillScript(
            name="error",
            path=script_path,
            extension=".py",
        )

        executor = ScriptExecutor()
        result = executor.execute(script)

        assert not result.success
        assert result.exit_code != 0
        assert result.error is not None
        assert "ValueError" in result.error

    def test_execute_nonexistent_script(self, temp_dir):
        """Test error when script doesn't exist."""
        script = SkillScript(
            name="nonexistent",
            path=temp_dir / "nonexistent.py",
            extension=".py",
        )

        executor = ScriptExecutor()
        result = executor.execute(script)

        assert not result.success
        assert "not found" in result.error

    def test_execute_timeout(self, temp_dir):
        """Test script timeout."""
        script_path = temp_dir / "slow.py"
        script_path.write_text("import time; time.sleep(10)")

        script = SkillScript(
            name="slow",
            path=script_path,
            extension=".py",
        )

        config = ExecutionConfig(timeout_seconds=1)
        executor = ScriptExecutor(config)
        result = executor.execute(script)

        assert not result.success
        assert "timed out" in result.error

    def test_execute_with_env_vars(self, temp_dir):
        """Test executing script with custom environment variables."""
        script_path = temp_dir / "env_test.py"
        script_path.write_text("""
import os
print(f"MY_VAR={os.environ.get('MY_VAR', 'not set')}")
""")

        script = SkillScript(
            name="env_test",
            path=script_path,
            extension=".py",
        )

        config = ExecutionConfig(env_vars={"MY_VAR": "custom_value"})
        executor = ScriptExecutor(config)
        result = executor.execute(script)

        assert result.success
        assert "MY_VAR=custom_value" in result.output

    def test_execute_inline_python(self):
        """Test executing inline Python code."""
        executor = ScriptExecutor()
        result = executor.execute_inline(
            code='print("Hello inline")',
            language="python",
        )

        assert result.success
        assert "Hello inline" in result.output

    def test_execute_inline_bash(self):
        """Test executing inline bash code."""
        executor = ScriptExecutor()
        result = executor.execute_inline(
            code='echo "Hello bash"',
            language="bash",
        )

        assert result.success
        assert "Hello bash" in result.output

    def test_execute_inline_with_args(self):
        """Test executing inline code with arguments."""
        executor = ScriptExecutor()
        result = executor.execute_inline(
            code="""
import json
import os
args = json.loads(os.environ.get("SKILL_ARGS", "{}"))
print(f"Value: {args.get('value')}")
""",
            language="python",
            args={"value": "test123"},
        )

        assert result.success
        assert "Value: test123" in result.output

    def test_execute_inline_unsupported_language(self):
        """Test error for unsupported language."""
        executor = ScriptExecutor()
        result = executor.execute_inline(
            code="print('hello')",
            language="cobol",  # unsupported
        )

        assert not result.success
        assert "Unsupported language" in result.error

    def test_validate_script_valid_python(self, temp_dir):
        """Test validating valid Python script."""
        script_path = temp_dir / "valid.py"
        script_path.write_text("print('hello')")

        script = SkillScript(
            name="valid",
            path=script_path,
            extension=".py",
        )

        executor = ScriptExecutor()
        error = executor.validate_script(script)

        assert error is None

    def test_validate_script_invalid_python(self, temp_dir):
        """Test validating invalid Python script."""
        script_path = temp_dir / "invalid.py"
        script_path.write_text("print('hello'")  # missing paren

        script = SkillScript(
            name="invalid",
            path=script_path,
            extension=".py",
        )

        executor = ScriptExecutor()
        error = executor.validate_script(script)

        assert error is not None
        assert "syntax error" in error.lower()

    def test_validate_script_nonexistent(self, temp_dir):
        """Test validating nonexistent script."""
        script = SkillScript(
            name="nonexistent",
            path=temp_dir / "nonexistent.py",
            extension=".py",
        )

        executor = ScriptExecutor()
        error = executor.validate_script(script)

        assert error is not None
        assert "not found" in error


class TestSkillScriptRunner:
    """Tests for SkillScriptRunner class."""

    def test_run_script_by_name(self, sample_skill_dir):
        """Test running a script by name."""
        runner = SkillScriptRunner()
        result = runner.run_script_by_name(
            sample_skill_dir,
            "process",
            args={"test": "value"},
        )

        assert result.success
        assert "Processing" in result.output

    def test_run_script_not_found(self, sample_skill_dir):
        """Test error when script not found."""
        runner = SkillScriptRunner()
        result = runner.run_script_by_name(
            sample_skill_dir,
            "nonexistent",
        )

        assert not result.success
        assert "not found" in result.error

    def test_run_script_no_scripts_dir(self, minimal_skill_dir):
        """Test error when scripts directory doesn't exist."""
        runner = SkillScriptRunner()
        result = runner.run_script_by_name(
            minimal_skill_dir,
            "any_script",
        )

        assert not result.success
        assert "Scripts directory not found" in result.error
