# Mock e2b_code_interpreter module if not present
import sys
from unittest.mock import MagicMock, patch

import pytest

from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful import (
    CodeSnippet,
    E2BExecutor,
)

if "e2b_code_interpreter" not in sys.modules:
    sys.modules["e2b_code_interpreter"] = MagicMock()


@pytest.fixture
def mock_sandbox():
    with patch("rustic_ai.core.guild.agent_ext.depends.code_execution.stateful.e2b_executor.Sandbox") as mock:
        yield mock


def test_initialization(mock_sandbox):
    """Test executor initialization"""
    executor = E2BExecutor(api_key="sk-test")
    # Sandbox should not be initialized yet (lazy)
    mock_sandbox.assert_not_called()

    # Trigger ensure_sandbox
    executor._ensure_sandbox()
    mock_sandbox.assert_called_once_with(api_key="sk-test", timeout=60)


def test_basic_execution(mock_sandbox):
    """Test basic code execution flow"""
    # Setup mock return
    mock_instance = mock_sandbox.return_value
    mock_execution = MagicMock()
    mock_execution.logs.stdout = ["Hello", " ", "World"]
    mock_execution.logs.stderr = []
    mock_execution.error = None
    mock_instance.run_code.return_value = mock_execution

    executor = E2BExecutor(api_key="sk-test")
    snippet = CodeSnippet(language="python", code="print('Hello World')")

    result = executor.run(snippet)

    assert result.exit_code == 0
    assert result.stdout == "Hello World"
    assert result.stderr == ""

    # Verify Sandbox method calls
    mock_instance.run_code.assert_called_once_with("print('Hello World')")


def test_execution_with_files(mock_sandbox):
    """Test execution with input and output files"""
    mock_instance = mock_sandbox.return_value
    mock_execution = MagicMock()
    mock_execution.logs.stdout = []
    mock_execution.logs.stderr = []
    mock_execution.error = None
    mock_instance.run_code.return_value = mock_execution

    # Mock file read
    mock_instance.files.read.return_value = b"OUTPUT DATA"

    executor = E2BExecutor(api_key="sk-test")
    snippet = CodeSnippet(language="python", code="process files")

    executor.run(
        snippet,
        input_files={"in.txt": b"INPUT DATA"},
        output_filenames=["out.txt"]
    )

    # Check input file write
    mock_instance.files.write.assert_called_with("in.txt", b"INPUT DATA")

    # Check output file read
    mock_instance.files.read.assert_called_with("out.txt")


def test_execution_error(mock_sandbox):
    """Test handling of execution errors"""
    mock_instance = mock_sandbox.return_value
    mock_execution = MagicMock()
    mock_execution.logs.stdout = []
    mock_execution.logs.stderr = []

    # Setup error object
    mock_error = MagicMock()
    mock_error.name = "ValueError"
    mock_error.value = "Test Error"
    mock_error.traceback = "Traceback..."
    mock_execution.error = mock_error

    mock_instance.run_code.return_value = mock_execution

    executor = E2BExecutor(api_key="sk-test")
    snippet = CodeSnippet(language="python", code="raise ValueError")

    result = executor.run(snippet)

    assert result.exit_code == 1
    assert "ValueError: Test Error" in result.stderr
    assert "Traceback..." in result.stderr


def test_state_persistence_intention(mock_sandbox):
    """Test that Sandbox instance is reused (stateful)"""
    executor = E2BExecutor(api_key="sk-test")

    # First run
    mock_instance = mock_sandbox.return_value
    mock_instance.run_code.return_value = MagicMock(error=None, logs=MagicMock(stdout=[], stderr=[]))
    executor.run(CodeSnippet(language="python", code="x=1"))

    # Second run
    executor.run(CodeSnippet(language="python", code="print(x)"))

    # Should maintain same sandbox instance (mock_sandbox called only once)
    assert mock_sandbox.call_count == 1
    assert mock_instance.run_code.call_count == 2
