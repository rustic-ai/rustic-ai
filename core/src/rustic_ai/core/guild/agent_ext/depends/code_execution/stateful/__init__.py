"""Code execution module for running arbitrary code snippets in a controlled environment.

This module provides a framework for safely executing code snippets in various programming
languages. It includes validation, execution, and result handling capabilities with both
synchronous and asynchronous support.

Key Components:
    - CodeExecutor: Abstract base class for implementing language-specific code executors
    - CodeValidator: Interface for implementing code validation rules
    - CodeSnippet: Container for code and its associated language
    - ExecutionResult: Complete representation of code execution outcomes
    - ExecutionException: Serializable exception information

Example:
    from rustic_ai.guild.agent_ext.depends.code_execution.stateful import (
        CodeSnippet,
        CodeExecutor,
        DefaultCodeValidator
    )

    snippet = CodeSnippet(language="python", code="print('Hello, World!')")
    executor = MyPythonExecutor()  # A concrete CodeExecutor implementation
    result = executor.run(snippet)
    print(result.stdout)  # Outputs: Hello, World!
"""

from .code_executor import CodeExecutor, CodeValidator, DefaultCodeValidator
from .exceptions import ExecutorError, ShutdownError, ValidationError
from .models import CodeSnippet, ExecutionException, ExecutionResult
from .python_exec_executor import PythonExecExecutor

__all__ = [
    "CodeExecutor",
    "CodeValidator",
    "DefaultCodeValidator",
    "ExecutorError",
    "ShutdownError",
    "ValidationError",
    "CodeSnippet",
    "ExecutionException",
    "ExecutionResult",
    "PythonExecExecutor",
]
