from abc import ABC, abstractmethod
import asyncio
import time
from typing import Dict, List, Optional, Set

from .exceptions import ExecutorError, ShutdownError, ValidationError
from .models import CodeSnippet, ExecutionException, ExecutionResult


class CodeValidator(ABC):
    """Abstract base class for code validation implementations.

    This class defines the interface for code validators that check whether a given
    code snippet is valid for execution. Implementations can enforce language
    restrictions, security policies, or other validation rules.

    Example:
        class MyValidator(CodeValidator):
            def is_valid(self, snippet):
                return snippet.language == "python"

            def explain(self, snippet):
                return "Only Python code is allowed" if snippet.language != "python" else None
    """

    @abstractmethod
    def is_valid(self, snippet: CodeSnippet) -> bool:
        """Check if the given code snippet is valid for execution.

        Args:
            snippet: The CodeSnippet instance to validate.

        Returns:
            bool: True if the code is valid and can be executed, False otherwise.
        """
        pass

    @abstractmethod
    def explain(self, snippet: CodeSnippet) -> Optional[str]:
        """Provide an explanation for why a code snippet is invalid.

        Args:
            snippet: The CodeSnippet instance that was validated.

        Returns:
            Optional[str]: A human-readable explanation of why the code is invalid,
                         or None if the code is valid.
        """
        pass


class DefaultCodeValidator(CodeValidator):
    """A basic code validator that checks if the code's language is supported.

    This validator simply verifies that the programming language specified in the
    code snippet is in the set of supported languages provided during initialization.

    Args:
        supported_languages: A set of strings representing the supported programming
                           language identifiers.

    Example:
        validator = DefaultCodeValidator({"python", "javascript"})
        snippet = CodeSnippet(language="python", code="print('hello')")
        is_valid = validator.is_valid(snippet)  # Returns True
    """

    def __init__(self, supported_languages: Set[str]):
        self._supported_languages = supported_languages

    def is_valid(self, snippet: CodeSnippet) -> bool:
        """Check if the snippet's language is supported.

        Args:
            snippet: The CodeSnippet instance to validate.

        Returns:
            bool: True if the language is supported, False otherwise.
        """
        return snippet.language in self._supported_languages

    def explain(self, snippet: CodeSnippet) -> Optional[str]:
        """Explain why a language is not supported.

        Args:
            snippet: The CodeSnippet instance to validate.

        Returns:
            Optional[str]: An explanation message if the language is not supported,
                         None otherwise.
        """
        if snippet.language not in self._supported_languages:
            return f"Unsupported language: {snippet.language}. Supported: {sorted(self._supported_languages)}"
        return None


class CodeExecutor(ABC):
    """Abstract base class for code execution implementations.

    This class provides the interface and common functionality for executing code snippets
    in various programming languages. It handles validation, timing, and error management
    while delegating the actual execution to concrete implementations.

    The executor supports both synchronous and asynchronous execution modes, with
    optional timeout control and file I/O capabilities.

    Args:
        validator: Optional CodeValidator instance to use for code validation.
                 If None, a DefaultCodeValidator will be created using the
                 supported_languages property.

    Example:
        class PythonExecutor(CodeExecutor):
            @property
            def supported_languages(self):
                return {"python"}

            def _do_run(self, code, timeout, input_files, output_filenames):
                # Implementation for running Python code
                pass

            def _do_shutdown(self):
                # Cleanup implementation
                pass
    """

    def __init__(self, validator: Optional[CodeValidator] = None):
        self._validator = validator
        self._is_shutdown = False

    @property
    @abstractmethod
    def supported_languages(self) -> Set[str]:
        """Set of programming languages supported by this executor.

        Returns:
            Set[str]: A set of strings representing the supported programming
                      language identifiers.
        """
        pass

    @abstractmethod
    def _do_run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int],
        input_files: Optional[Dict[str, bytes]],
        output_filenames: Optional[List[str]],
    ) -> ExecutionResult:
        """Perform the actual execution of the code snippet.

        Args:
            code: The CodeSnippet instance to execute.
            timeout_seconds: Optional timeout in seconds for the execution.
            input_files: Optional dictionary of input file names and their contents.
            output_filenames: Optional list of output file names to be generated.

        Returns:
            ExecutionResult: The result of the code execution.
        """
        pass

    @abstractmethod
    def _do_shutdown(self) -> None:
        """Perform the actual shutdown process for the executor."""
        pass

    async def _do_run_async(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int],
        input_files: Optional[Dict[str, bytes]],
        output_filenames: Optional[List[str]],
    ) -> ExecutionResult:
        """Asynchronous wrapper for the _do_run method."""
        return await asyncio.to_thread(self._do_run, code, timeout_seconds, input_files, output_filenames)

    async def _do_shutdown_async(self) -> None:
        """Asynchronous wrapper for the _do_shutdown method."""
        await asyncio.to_thread(self._do_shutdown)

    def run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int] = 60,
        input_files: Optional[Dict[str, bytes]] = None,
        output_filenames: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """Run the code snippet synchronously.

        Args:
            code: The CodeSnippet instance to execute.
            timeout_seconds: Optional timeout in seconds for the execution.
            input_files: Optional dictionary of input file names and their contents.
            output_filenames: Optional list of output file names to be generated.

        Returns:
            ExecutionResult: The result of the code execution.

        Raises:
            ExecutorError: If the executor has already been shut down.
            ValidationError: If the code snippet is invalid.
        """
        if self._is_shutdown:
            raise ExecutorError("Executor has already been shut down.")

        start_time = time.monotonic()
        validator = self._validator or DefaultCodeValidator(self.supported_languages)

        if not validator.is_valid(code):
            explanation = validator.explain(code) or f"Unsupported language: {code.language}"
            raise ValidationError(explanation)

        result = None
        exception_obj = None
        try:
            result = self._do_run(code, timeout_seconds, input_files, output_filenames)
        except Exception as e:
            exception_obj = ExecutionException.from_exception(e)
            result = ExecutionResult(input_snippet=code, exit_code=-1, exception=exception_obj)

        result.duration_seconds = time.monotonic() - start_time
        if exception_obj:
            result.exception = exception_obj
            if result.exit_code == 0:
                result.exit_code = -1
        return result

    async def run_async(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int] = 60,
        input_files: Optional[Dict[str, bytes]] = None,
        output_filenames: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """Run the code snippet asynchronously.

        Args:
            code: The CodeSnippet instance to execute.
            timeout_seconds: Optional timeout in seconds for the execution.
            input_files: Optional dictionary of input file names and their contents.
            output_filenames: Optional list of output file names to be generated.

        Returns:
            ExecutionResult: The result of the code execution.

        Raises:
            ExecutorError: If the executor has already been shut down.
            ValidationError: If the code snippet is invalid.
        """
        if self._is_shutdown:
            raise ExecutorError("Executor has already been shut down.")

        start_time = time.monotonic()
        validator = self._validator or DefaultCodeValidator(self.supported_languages)

        if not validator.is_valid(code):
            explanation = validator.explain(code) or f"Unsupported language: {code.language}"
            raise ValidationError(explanation)

        result = None
        exception_obj = None
        try:
            if timeout_seconds is not None:
                result = await asyncio.wait_for(
                    self._do_run_async(code, timeout_seconds, input_files, output_filenames), timeout=timeout_seconds
                )
            else:
                result = await self._do_run_async(code, None, input_files, output_filenames)
        except asyncio.TimeoutError as e:
            exception_obj = ExecutionException.from_exception(e)
            result = ExecutionResult(input_snippet=code, exit_code=-1, exception=exception_obj, timed_out=True)
        except Exception as e:
            exception_obj = ExecutionException.from_exception(e)
            result = ExecutionResult(input_snippet=code, exit_code=-1, exception=exception_obj)

        result.duration_seconds = time.monotonic() - start_time
        if exception_obj:
            result.exception = exception_obj
            if result.exit_code == 0:
                result.exit_code = -1
        return result

    def shutdown(self) -> None:
        """Shut down the executor synchronously.

        Raises:
            ShutdownError: If an error occurs during shutdown.
        """
        if not self._is_shutdown:
            try:
                self._do_shutdown()
            except Exception as e:
                raise ShutdownError(f"Failed during shutdown: {e}") from e
            finally:
                self._is_shutdown = True

    async def shutdown_async(self) -> None:
        """Shut down the executor asynchronously.

        Raises:
            ShutdownError: If an error occurs during async shutdown.
        """
        if not self._is_shutdown:
            try:
                await self._do_shutdown_async()
            except Exception as e:
                raise ShutdownError(f"Failed during async shutdown: {e}") from e
            finally:
                self._is_shutdown = True
