import traceback
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.utils.json_utils import JsonDict


class CodeSnippet(BaseModel):
    """A container for executable code and its associated programming language.

    This class represents a block of code to be executed by a CodeExecutor. It includes
    both the source code and the programming language identifier to help the executor
    determine how to run the code.

    Attributes:
        language: The programming language identifier (e.g., "python", "javascript").
        code: The actual source code to be executed.

    Example:
        snippet = CodeSnippet(
            language="python",
            code="print('Hello, World!')"
        )
    """

    language: str
    code: str


class ExecutionException(BaseModel):
    """A serializable representation of an exception that occurred during code execution.

    This class captures the essential information about an exception, including its type,
    message, and optionally the full traceback. It provides a convenient way to serialize
    and deserialize exception information, especially useful when exceptions need to be
    transmitted across process or network boundaries.

    Attributes:
        type: The name of the exception class (e.g., "ValueError", "SyntaxError").
        message: The string representation of the exception message.
        traceback: Optional string containing the formatted traceback information.

    Example:
        try:
            # Some code that may raise an exception
            raise ValueError("Invalid input")
        except Exception as e:
            ex = ExecutionException.from_exception(e)
    """

    type: str
    message: str
    traceback: Optional[str] = None

    @classmethod
    def from_exception(cls, e: Exception | str, include_traceback: bool = True):
        """Create an ExecutionException instance from a Python exception or error message.

        Args:
            e: Either an Exception instance or an error message string.
            include_traceback: Whether to include the traceback information if available.

        Returns:
            ExecutionException: A new instance containing the exception details.
        """
        if isinstance(e, str):
            return cls(type="GenericError", message=e, traceback=None)
        tb_str = None
        if include_traceback and hasattr(e, "__traceback__") and e.__traceback__:
            try:
                tb_str = "".join(traceback.format_exception(type(e), value=e, tb=e.__traceback__))
            except Exception:
                tb_str = f"Error formatting traceback for {type(e).__name__}"
        return cls(type=type(e).__name__, message=str(e), traceback=tb_str)


class ExecutionResult(BaseModel):
    """Represents the complete outcome of executing a code snippet.

    This class captures all relevant information about a code execution attempt, including
    the original input, output streams, execution status, performance metrics, and any
    errors that occurred.

    Attributes:
        input_snippet: The CodeSnippet that was executed.
        stdout: Captured standard output from the execution.
        stderr: Captured standard error output from the execution.
        exit_code: The process exit code (0 typically indicates success).
        exception: Optional ExecutionException if an error occurred.
        timed_out: Whether the execution exceeded its time limit.
        duration_seconds: How long the execution took in seconds.
        output_files: Dictionary mapping filenames to their binary contents.
        logs: List of log messages generated during execution.
        resources_used: Optional dictionary containing resource usage metrics.

    Example:
        result = ExecutionResult(
            input_snippet=snippet,
            stdout="Hello, World!\\n",
            stderr="",
            exit_code=0,
            duration_seconds=0.1
        )
    """

    input_snippet: CodeSnippet
    stdout: str = ""
    stderr: str = ""
    exit_code: int
    exception: Optional[ExecutionException] = None
    timed_out: bool = False
    duration_seconds: Optional[float] = None
    output_files: Dict[str, bytes] = Field(default_factory=dict)
    logs: List[str] = Field(default_factory=list)
    resources_used: Optional[JsonDict] = None
