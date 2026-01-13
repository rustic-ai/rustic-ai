from typing import Dict, List, Optional, Set

try:
    from e2b_code_interpreter import Sandbox
except ImportError:
    Sandbox = None

from .code_executor import CodeExecutor
from .exceptions import ExecutorError
from .models import CodeSnippet, ExecutionException, ExecutionResult


class E2BExecutor(CodeExecutor):
    """
    Executes code using E2B's secure cloud sandboxes.
    Requires 'e2b-code-interpreter' package and E2B_API_KEY environment variable.
    """

    def __init__(self, timeout: int = 60, api_key: Optional[str] = None):
        super().__init__()
        if Sandbox is None:
            raise ImportError("The 'e2b-code-interpreter' package is required for E2BExecutor.")

        # We start the sandbox lazily or eagerly?
        # A sandbox session maps to an Executor instance.
        self.sandbox: Optional[Sandbox] = None
        self.timeout = timeout
        self.api_key = api_key

    @property
    def supported_languages(self) -> Set[str]:
        return {"python"}

    def _ensure_sandbox(self):
        if not self.sandbox:
            try:
                self.sandbox = Sandbox(api_key=self.api_key, timeout=self.timeout)
            except Exception as e:
                raise ExecutorError(f"Failed to create E2B Sandbox: {e}")

    def _do_run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int],
        input_files: Optional[Dict[str, bytes]],
        output_filenames: Optional[List[str]],
    ) -> ExecutionResult:
        self._ensure_sandbox()
        assert self.sandbox is not None

        try:
            # Handle input files by writing them into the sandbox filesystem before execution.
            # We normalize content to bytes, accepting both bytes and str for robustness.
            # The E2B SDK accepts bytes for file contents; str values are encoded as UTF-8 here.
            if input_files:
                for name, content in input_files.items():
                    if isinstance(content, bytes):
                        file_bytes = content
                    elif isinstance(content, str):
                        file_bytes = content.encode("utf-8")
                    else:
                        raise ExecutorError(
                            f"Unsupported file content type for '{name}': {type(content).__name__}; "
                            "expected bytes or str."
                        )
                    self.sandbox.files.write(name, file_bytes)

            execution = self.sandbox.run_code(code.code)

            # E2B execution result objects
            stdout = "".join(execution.logs.stdout)
            stderr = "".join(execution.logs.stderr)

            # Retrieve output files
            output_files_dict = {}
            if output_filenames:
                for name in output_filenames:
                    try:
                        # read() returns bytes?
                        content = self.sandbox.files.read(name)
                        output_files_dict[name] = content
                    except Exception:
                        # Ignore failures to read individual output files; missing or unreadable
                        # outputs are treated as absent and do not fail the overall execution.
                        pass

            exit_code = 1 if execution.error else 0
            # If there is a runtime error, it's in execution.error
            exception_obj = None
            if execution.error:
                # Construct exception info
                stderr += f"\n{execution.error.name}: {execution.error.value}\n{execution.error.traceback}"

            return ExecutionResult(
                input_snippet=code,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                exception=exception_obj,
                output_files=output_files_dict,
            )

        except Exception as e:
            return ExecutionResult(
                input_snippet=code,
                exit_code=-1,
                exception=ExecutionException.from_exception(e),
            )

    def _do_shutdown(self) -> None:
        if self.sandbox:
            self.sandbox.close()
