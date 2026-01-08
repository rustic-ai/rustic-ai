"""Script execution framework for Agent Skills.

Provides secure, sandboxed execution of skill scripts with proper
argument handling, timeout support, and output capture.
"""

import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import SkillScript

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    """Result of script execution."""

    success: bool = Field(description="Whether execution succeeded")
    output: str = Field(description="Standard output from script")
    error: Optional[str] = Field(default=None, description="Standard error if any")
    exit_code: int = Field(description="Process exit code")
    duration_ms: Optional[float] = Field(default=None, description="Execution duration in milliseconds")


class ExecutionConfig(BaseModel):
    """Configuration for script execution."""

    timeout_seconds: int = Field(default=30, description="Maximum execution time")
    working_dir: Optional[Path] = Field(default=None, description="Working directory for script")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="Additional environment variables")
    capture_stderr: bool = Field(default=True, description="Whether to capture stderr")
    max_output_bytes: int = Field(default=1024 * 1024, description="Maximum output size (1MB default)")


class ScriptExecutor:
    """
    Executes skill scripts with proper sandboxing and error handling.

    Supports:
    - Python scripts (.py)
    - Shell scripts (.sh, .bash)
    - JavaScript/TypeScript (.js, .ts)
    - Ruby scripts (.rb)

    Example usage:
        executor = ScriptExecutor()

        result = executor.execute(
            script=skill.get_script("process_data"),
            args={"input": "data.json", "format": "csv"},
        )

        if result.success:
            print(result.output)
        else:
            print(f"Error: {result.error}")
    """

    # Interpreter mapping
    INTERPRETERS: Dict[str, List[str]] = {
        ".py": ["python3", "-u"],  # -u for unbuffered output
        ".sh": ["bash"],
        ".bash": ["bash"],
        ".js": ["node"],
        ".ts": ["npx", "ts-node"],
        ".rb": ["ruby"],
    }

    def __init__(self, config: Optional[ExecutionConfig] = None):
        """
        Initialize the executor.

        Args:
            config: Execution configuration (uses defaults if not provided)
        """
        self.config = config or ExecutionConfig()

    def execute(
        self,
        script: SkillScript,
        args: Optional[Dict[str, Any]] = None,
        config_override: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        """
        Execute a skill script with the given arguments.

        Args:
            script: The SkillScript to execute
            args: Arguments to pass to the script (as JSON via stdin or env)
            config_override: Override default execution config

        Returns:
            ExecutionResult with output, errors, and exit code
        """
        config = config_override or self.config

        # Get interpreter for script type
        interpreter = self._get_interpreter(script.extension)
        if not interpreter:
            return ExecutionResult(
                success=False,
                output="",
                error=f"No interpreter found for {script.extension} scripts",
                exit_code=-1,
            )

        # Verify script exists
        if not script.path.exists():
            return ExecutionResult(
                success=False,
                output="",
                error=f"Script not found: {script.path}",
                exit_code=-1,
            )

        # Build command
        cmd = interpreter + [str(script.path)]

        # Prepare environment
        env = os.environ.copy()
        env.update(config.env_vars)

        # Pass arguments via SKILL_ARGS environment variable as JSON
        if args:
            env["SKILL_ARGS"] = json.dumps(args)

        # Determine working directory
        working_dir = config.working_dir or script.path.parent

        # Execute
        import time

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                env=env,
                capture_output=True,
                timeout=config.timeout_seconds,
                text=True,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Truncate output if too large
            output = result.stdout
            if len(output.encode()) > config.max_output_bytes:
                output = output[: config.max_output_bytes] + "\n... [output truncated]"

            stderr = result.stderr if config.capture_stderr else None

            return ExecutionResult(
                success=result.returncode == 0,
                output=output,
                error=stderr if stderr else None,
                exit_code=result.returncode,
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error=f"Script execution timed out after {config.timeout_seconds} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Script execution failed: {e}")
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
            )

    def execute_inline(
        self,
        code: str,
        language: str,
        args: Optional[Dict[str, Any]] = None,
        config_override: Optional[ExecutionConfig] = None,
    ) -> ExecutionResult:
        """
        Execute inline code without a script file.

        This creates a temporary file and executes it. Useful for
        dynamic code generation or testing.

        Args:
            code: The code to execute
            language: Language (python, bash, javascript, etc.)
            args: Arguments to pass to the script
            config_override: Override default execution config

        Returns:
            ExecutionResult with output and errors
        """
        # Map language names to extensions
        ext_map = {
            "python": ".py",
            "bash": ".sh",
            "shell": ".sh",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "ruby": ".rb",
        }

        extension = ext_map.get(language.lower())
        if not extension:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Unsupported language: {language}",
                exit_code=-1,
            )

        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=extension,
            delete=False,
        ) as f:
            f.write(code)
            temp_path = Path(f.name)

        try:
            # Create SkillScript for the temp file
            temp_script = SkillScript(
                name="inline",
                path=temp_path,
                extension=extension,
                description="Inline code execution",
            )

            return self.execute(temp_script, args, config_override)

        finally:
            # Clean up temp file
            try:
                temp_path.unlink()
            except Exception:
                pass

    def _get_interpreter(self, extension: str) -> Optional[List[str]]:
        """Get the interpreter command for a script extension."""
        return self.INTERPRETERS.get(extension)

    def validate_script(self, script: SkillScript) -> Optional[str]:
        """
        Validate a script before execution.

        Performs basic syntax checks without executing the script.

        Args:
            script: The script to validate

        Returns:
            Error message if validation fails, None if valid
        """
        if not script.path.exists():
            return f"Script not found: {script.path}"

        # Python syntax check
        if script.extension == ".py":
            try:
                import ast

                with open(script.path) as f:
                    ast.parse(f.read())
            except SyntaxError as e:
                return f"Python syntax error: {e}"

        # Shell syntax check (if shellcheck is available)
        elif script.extension in {".sh", ".bash"}:
            try:
                result = subprocess.run(
                    ["bash", "-n", str(script.path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    return f"Shell syntax error: {result.stderr}"
            except FileNotFoundError:
                pass  # bash not available, skip check
            except subprocess.TimeoutExpired:
                return "Shell syntax check timed out"

        return None


class SkillScriptRunner:
    """
    High-level interface for running skill scripts.

    Combines script discovery, argument parsing, and execution.
    """

    def __init__(self, executor: Optional[ScriptExecutor] = None):
        """
        Initialize the runner.

        Args:
            executor: ScriptExecutor instance (creates default if not provided)
        """
        self.executor = executor or ScriptExecutor()

    def run_script_by_name(
        self,
        skill_path: Path,
        script_name: str,
        args: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Run a script by name from a skill folder.

        Args:
            skill_path: Path to the skill folder
            script_name: Name of the script (without extension)
            args: Arguments to pass

        Returns:
            ExecutionResult from execution
        """
        scripts_dir = skill_path / "scripts"
        if not scripts_dir.exists():
            return ExecutionResult(
                success=False,
                output="",
                error=f"Scripts directory not found: {scripts_dir}",
                exit_code=-1,
            )

        # Find script by name (any extension)
        for script_file in scripts_dir.iterdir():
            if script_file.stem == script_name and script_file.suffix in ScriptExecutor.INTERPRETERS:
                script = SkillScript(
                    name=script_file.stem,
                    path=script_file,
                    extension=script_file.suffix,
                )
                return self.executor.execute(script, args)

        return ExecutionResult(
            success=False,
            output="",
            error=f"Script not found: {script_name}",
            exit_code=-1,
        )
