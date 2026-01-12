from pydantic import BaseModel, Field
import pytest

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.python_orchestrator import (
    PythonOrchestratorParams,
    PythonOrchestratorToolset,
)
from rustic_ai.llm_agent.react.toolset import ReActToolset


# Define simple tools for testing
class AddParams(BaseModel):
    a: int
    b: int


class GreetParams(BaseModel):
    name: str = Field(default="World")


class SimpleToolset(ReActToolset):
    def get_toolspecs(self):
        return [
            ToolSpec(
                name="add_numbers",
                description="Adds two numbers",
                parameter_class=AddParams
            ),
            ToolSpec(
                name="greet_user",
                description="Greets a user",
                parameter_class=GreetParams
            )
        ]

    def execute(self, tool_name, args):
        if tool_name == "add_numbers":
            return str(args.a + args.b)
        elif tool_name == "greet_user":
            return f"Hello, {args.name}!"
        return "Unknown tool"


@pytest.fixture
def orchestrator():
    inner = SimpleToolset()
    return PythonOrchestratorToolset(inner_toolset=inner)


def test_tool_documentation_generation(orchestrator):
    """Test that tool signatures are generated correctly for the prompt."""
    specs = orchestrator.get_toolspecs()
    assert len(specs) == 1
    assert specs[0].name == "python_orchestrator"

    desc = specs[0].description
    assert "add_numbers(a, b)" in desc
    # Optional arguments should indicate default/None
    # GreetParams has a default, so it might appear as required or optional depending on schema generation
    # Pydantic schema for field with default is usually not required.
    assert "greet_user" in desc


def test_execution_simple_math(orchestrator):
    """Test executing simple pure python code."""
    code = "print(1 + 1)"
    params = PythonOrchestratorParams(code=code)
    result = orchestrator.execute("python_orchestrator", params)

    assert "2" in result


def test_execution_calling_inner_tool(orchestrator):
    """Test python code calling an injected tool."""
    code = """
result = add_numbers(a=10, b=20)
print(f"Result is {result}")
"""
    params = PythonOrchestratorParams(code=code)
    result = orchestrator.execute("python_orchestrator", params)

    assert "Result is 30" in result


def test_execution_calling_multiple_tools(orchestrator):
    """Test chaining multiple tool calls."""
    code = """
sum_val = add_numbers(a=5, b=5)
# sum_val returned as string "10"
msg = greet_user(name="User" + sum_val)
print(msg)
"""
    params = PythonOrchestratorParams(code=code)
    result = orchestrator.execute("python_orchestrator", params)

    assert "Hello, User10!" in result


def test_execution_error_handling(orchestrator):
    """Test that errors in the python script are returned properly."""
    code = "1 / 0"
    params = PythonOrchestratorParams(code=code)
    result = orchestrator.execute("python_orchestrator", params)

    # Logic in python_orchestrator should catch exception formatted with traceback
    assert "Error executing code" in result or "ZeroDivisionError" in result


def test_tool_call_validation_error(orchestrator):
    """Test calling a tool with invalid arguments from within script."""
    code = "add_numbers(a='invalid', b=2)"  # 'a' should be int
    params = PythonOrchestratorParams(code=code)
    orchestrator.execute("python_orchestrator", params)

    # The tool wrapper catches the validation error and returns it as string
    # print the result to verify if it was printed or just returned
    # The wrapper returns the error string. If the script doesn't print it, it won't be in stdout.
    # We should make the script print it or check side effects.

    # Let's adjust expected behavior:
    # If the tool fails, it returns error string. The script continues unless it raises exception.
    # So `ret = add_numbers(...)` -> ret will be "Error calling tool..."

    code_check = """
ret = add_numbers(a='invalid', b=2)
print(ret)
"""
    params2 = PythonOrchestratorParams(code=code_check)
    result2 = orchestrator.execute("python_orchestrator", params2)

    assert "Error calling tool 'add_numbers'" in result2
    assert "validation error" in result2.lower()
