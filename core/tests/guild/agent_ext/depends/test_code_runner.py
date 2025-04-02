import pytest

from rustic_ai.core.guild.agent_ext.depends.code_execution.code_runner import (
    CodeBlock,
    CodeRunner,
    InProcessCodeInterpreter,
)
from rustic_ai.core.utils.json_utils import JsonDict


class TestCodeRunner:

    @pytest.fixture
    def interpreter(self):
        interpreter = InProcessCodeInterpreter()
        return interpreter

    def test_execute_valid_python_code(self, interpreter: CodeRunner):

        code_blocks = [CodeBlock(language="python", code="x = 1 + 1\nprint(x)", globals={}, locals={})]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert results[0].output.strip() == "2"
        assert results[0].error == ""

    def test_execute_invalid_python_code(self, interpreter: CodeRunner):

        code_blocks = [CodeBlock(language="python", code="x = 1 / 0\nprint(x)", globals={}, locals={})]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 1
        assert results[0].exception is not None
        assert "ZeroDivisionError" in results[0].exception.etype
        assert "division by zero" in results[0].exception.message

    def test_execute_syntax_error(self, interpreter: CodeRunner):

        code_blocks = [
            CodeBlock(
                language="python",
                code="def missing_colon()\n    pass",
                globals={},
                locals={},
            )
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 1
        assert results[0].exception is not None
        assert "SyntaxError" in results[0].exception.etype
        assert "expected ':'" in results[0].exception.message

    def test_execute_with_globals_and_locals(self, interpreter: CodeRunner):

        global_vars = {"y": 10}
        local_vars: JsonDict = {}
        code_blocks = [
            CodeBlock(
                language="python",
                code="x = y + 5\nprint(x)",
                globals=global_vars,
                locals=local_vars,
            )
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert results[0].output.strip() == "15"
        assert results[0].error == ""

    def test_execute_multiple_code_blocks(self, interpreter: CodeRunner):

        code_blocks = [
            CodeBlock(language="python", code="a = 5\nprint(a)", globals={}, locals={}),
            CodeBlock(
                language="python",
                code="b = a + 10\nprint(b)",
                globals={},
                locals={"a": 5},
            ),
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 2
        assert results[0].exit_code == 0
        assert results[0].output.strip() == "5"
        assert results[0].error == ""
        assert results[1].exit_code == 0
        assert results[1].output.strip() == "15"
        assert results[1].error == ""

    def test_execute_unsupported_language(self, interpreter: CodeRunner):

        code_blocks = [
            CodeBlock(
                language="javascript",
                code="console.log('Hello, World!')",
                globals={},
                locals={},
            )
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 1
        assert "unsupported language" in results[0].error.lower()
        assert results[0].output == ""

    def test_read_back_globals(self, interpreter: CodeRunner):
        global_vars: JsonDict = {"counter": 0}
        code_blocks = [
            CodeBlock(
                language="python",
                code="global counter\ncounter += 1\nprint(counter)",
                globals=global_vars,
                locals={},
            )
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert results[0].output.strip() == "1"

        result_vars = results[0].code.globals
        assert result_vars["counter"] == 1  # Verify global variable was updated

    def test_read_back_locals(self, interpreter: CodeRunner):
        local_vars: JsonDict = {}
        code_blocks = [
            CodeBlock(
                language="python",
                code="x = 42\ny = x * 2\nprint(y)",
                globals={},
                locals=local_vars,
            )
        ]

        results = interpreter.validate_and_run(code_blocks)

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert results[0].output.strip() == "84"

        result_vars = results[0].code.locals
        assert "x" in result_vars  # Verify local variable 'x' exists
        assert "y" in result_vars  # Verify local variable 'y' exists
        assert result_vars["x"] == 42
        assert result_vars["y"] == 84
