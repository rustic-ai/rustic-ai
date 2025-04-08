import pytest

from rustic_ai.core.guild.agent_ext.depends.code_execution.stateful import (
    CodeSnippet,
    PythonExecExecutor,
    ValidationError,
)


@pytest.fixture
def executor():
    return PythonExecExecutor()


@pytest.fixture
def executor_with_imports():
    return PythonExecExecutor(whitelisted_imports={"math", "json"}, default_imports={"m": "math", "json_lib": "json"})


def test_basic_execution(executor):
    """Test basic code execution"""
    snippet = CodeSnippet(language="python", code='x = 1 + 2\nprint(f"Result: {x}")')
    result = executor.run(snippet)

    assert result.exit_code == 0
    assert result.stdout == "Result: 3\n"
    assert result.stderr == ""
    assert result.exception is None


def test_state_persistence(executor):
    """Test that state persists between executions"""
    # First execution sets a variable
    snippet1 = CodeSnippet(language="python", code="x = 42")
    result1 = executor.run(snippet1)
    assert result1.exit_code == 0

    # Second execution uses the variable
    snippet2 = CodeSnippet(language="python", code="print(x)")
    result2 = executor.run(snippet2)
    assert result2.exit_code == 0
    assert result2.stdout == "42\n"


def test_error_handling(executor):
    """Test handling of runtime errors"""
    snippet = CodeSnippet(language="python", code="1/0")  # Division by zero error
    result = executor.run(snippet)

    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "ZeroDivisionError"
    assert "division by zero" in result.exception.message


def test_syntax_error_handling(executor):
    """Test handling of syntax errors"""
    snippet = CodeSnippet(language="python", code="if True print('invalid')")  # Missing colon
    result = executor.run(snippet)

    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "SyntaxError"


def test_blocked_direct_import(executor):
    """Test that direct imports are blocked by default"""
    snippet = CodeSnippet(language="python", code="import sys")
    result = executor.run(snippet)

    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "ImportError"
    assert "__import__ not found" in result.exception.message


def test_output_capture(executor):
    """Test capture of stdout and stderr"""
    snippet = CodeSnippet(
        language="python",
        code="""
print('to stdout')
raise Exception('to stderr')
""",
    )
    result = executor.run(snippet)

    assert "to stdout" in result.stdout
    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "Exception"
    assert "to stderr" in result.exception.message


def test_invalid_language(executor):
    """Test validation of programming language"""
    snippet = CodeSnippet(language="javascript", code="console.log('Hello')")

    with pytest.raises(ValidationError) as exc_info:
        executor.run(snippet)
    assert "Unsupported language: javascript" in str(exc_info.value)


def test_shutdown_clears_state(executor):
    """Test that shutdown clears the executor state"""
    # Set a variable
    snippet1 = CodeSnippet(language="python", code="x = 42")
    executor.run(snippet1)

    # Shutdown should clear state
    executor.shutdown()

    # Try to access variable after shutdown
    snippet2 = CodeSnippet(language="python", code="print(x)")
    result = executor.run(snippet2)
    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "NameError"
    assert "name 'x' is not defined" in result.exception.message


def test_whitelisted_imports(executor_with_imports):
    """Test that whitelisted imports are allowed"""
    snippet = CodeSnippet(language="python", code="from math import sqrt\nprint(sqrt(16))")
    result = executor_with_imports.run(snippet)

    assert result.exit_code == 0
    assert result.stdout.strip() == "4.0"
    assert result.stderr == ""
    assert result.exception is None


def test_blocked_non_whitelisted_import(executor_with_imports):
    """Test that non-whitelisted imports are blocked"""
    snippet = CodeSnippet(language="python", code="import sys")
    result = executor_with_imports.run(snippet)

    assert result.exit_code == -1
    assert result.exception is not None
    assert result.exception.type == "ImportError"
    assert "Import of 'sys' is not allowed" in result.exception.message


def test_default_imports_available(executor_with_imports):
    """Test that default imports are available"""
    snippet = CodeSnippet(language="python", code="print(m.pi)\nprint(json_lib.dumps([1,2,3]))")
    result = executor_with_imports.run(snippet)

    assert result.exit_code == 0
    assert "3.14159" in result.stdout  # math.pi
    assert "[1, 2, 3]" in result.stdout  # json.dumps result
    assert result.stderr == ""
    assert result.exception is None
