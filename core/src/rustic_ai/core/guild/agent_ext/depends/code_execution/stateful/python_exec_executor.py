import io
import logging
import sys
from typing import Any, Dict, List, Optional, Set

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)

from .code_executor import CodeExecutor, CodeValidator, DefaultCodeValidator
from .exceptions import ValidationError
from .models import CodeSnippet, ExecutionException, ExecutionResult


class PythonExecExecutor(CodeExecutor):
    """
    Executes Python code snippets using Python's built-in `exec()` in a shared local context.
    Inherits boilerplate logic from BaseCodeExecutor.

    WARNING:
        This executor is NOT safe for running untrusted code due to the use of `exec()`.
        Use hardened sandboxes (e.g., Docker) in production or for untrusted code.
        Timeouts and file I/O parameters are NOT enforced/used by this specific implementation's
        `_do_run` method, although `run_async` provides external timeout via asyncio.
    """

    _local_vars: Dict[str, Any]  # Stores persistent state
    _allowed_builtins = {
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "chr",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "zip",
        "Exception",
        "ImportError",
        "NameError",
        "ZeroDivisionError",
    }

    def __init__(
        self,
        validator: Optional[CodeValidator] = None,
        whitelisted_imports: Optional[Set[str]] = None,
        default_imports: Optional[Dict[str, str]] = None,
    ):
        effective_validator = validator or DefaultCodeValidator({"python"})
        super().__init__(effective_validator)
        self._local_vars = {}
        self._whitelisted_imports = whitelisted_imports or set()
        self._default_imports = default_imports or {}

        # Get the builtins as a dictionary
        builtins_dict = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)

        # Start with an empty dict of restricted builtins
        self._restricted_builtins = {}

        # Copy allowed builtins
        for name in self._allowed_builtins:
            if name in builtins_dict:
                self._restricted_builtins[name] = builtins_dict[name]

        # Ensure basic built-in attributes are available
        self._restricted_builtins.update(
            {
                "__build_class__": builtins_dict["__build_class__"],
                "__name__": "__main__",
                "__doc__": None,
                "__package__": None,
            }
        )

        # Handle imports
        if self._whitelisted_imports:
            # Only add import functionality when whitelist is provided
            self._restricted_builtins["__import__"] = self._wrapped_import
        else:
            # When no whitelist is provided, ensure import functionality is completely disabled
            self._restricted_builtins.pop("import", None)
            self._restricted_builtins.pop("__import__", None)

        # Import default modules
        if self._default_imports:
            # Temporarily store original builtins
            original_builtins = dict(self._restricted_builtins)
            # Add full import capability just for importing default modules
            self._restricted_builtins["__import__"] = __import__
            try:
                self._import_default_modules()
            finally:
                # Restore original restricted builtins
                self._restricted_builtins = original_builtins

    def _wrapped_import(self, name: str, globals=None, locals=None, fromlist=(), level=0):
        """Safely handle imports by checking against whitelist"""
        # For 'from x import y' statements, check the base module
        module_name = name.split(".")[0]
        if module_name not in self._whitelisted_imports:
            raise ImportError(
                f"Import of '{module_name}' is not allowed. Allowed imports: {sorted(self._whitelisted_imports)}"
            )
        return __import__(name, globals, locals, fromlist, level)

    def _import_default_modules(self):
        """Import and initialize default modules in the execution context"""
        for alias, module_path in self._default_imports.items():
            try:
                module_parts = module_path.split(".")
                if len(module_parts) > 1:
                    # Handle submodule imports (e.g., 'numpy.random' as 'np_random')
                    base_module = __import__(module_parts[0])
                    module = base_module
                    for part in module_parts[1:]:
                        module = getattr(module, part)
                else:
                    # Handle simple imports (e.g., 'math' as 'm')
                    module = __import__(module_path)
                    module = sys.modules[module_path]  # Get the actual module
                self._local_vars[alias] = module
            except ImportError as e:
                logging.warning(f"Failed to import default module {module_path}: {e}")

    @property
    def supported_languages(self) -> Set[str]:
        return {"python"}

    def _do_run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int],
        input_files: Optional[Dict[str, bytes]],
        output_filenames: Optional[List[str]],
    ) -> ExecutionResult:
        """
        Executes Python code using `exec()`. Relies on base class for validation.

        NOTE: This implementation ignores timeout_seconds, input_files, and
              output_filenames parameters. Timeout for async is handled externally
              by the base class `run_async` method. File I/O is not supported.
        """
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        exit_code = 0
        exception_obj: Optional[ExecutionException] = None
        output_files_dict: Dict[str, bytes] = {}

        try:
            sys.stdout = stdout_buffer
            sys.stderr = stderr_buffer

            # Execute the code with our restricted builtins
            exec(code.code, {"__builtins__": self._restricted_builtins}, self._local_vars)
        except Exception as e:
            exit_code = -1
            exception_obj = ExecutionException.from_exception(e)
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        return ExecutionResult(
            input_snippet=code,
            stdout=stdout_buffer.getvalue(),
            stderr=stderr_buffer.getvalue(),
            exit_code=exit_code,
            exception=exception_obj,
            output_files=output_files_dict,
        )

    def run(
        self,
        code: CodeSnippet,
        timeout_seconds: Optional[int] = 60,
        input_files: Optional[Dict[str, bytes]] = None,
        output_filenames: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """Run the code snippet synchronously with shutdown handling.

        This implementation allows code execution after shutdown but with cleared state.
        """
        validator = self._validator or DefaultCodeValidator(self.supported_languages)

        if not validator.is_valid(code):
            explanation = validator.explain(code) or f"Unsupported language: {code.language}"
            raise ValidationError(explanation)

        result = None
        if self._is_shutdown:
            # After shutdown, execute with empty state
            old_vars = self._local_vars
            self._local_vars = {}
            try:
                result = self._do_run(code, timeout_seconds, input_files, output_filenames)
            finally:
                self._local_vars = old_vars
        else:
            result = self._do_run(code, timeout_seconds, input_files, output_filenames)

        return result

    def _do_shutdown(self) -> None:
        """
        Clears the persistent local variables and marks executor as shut down.
        """
        self._local_vars.clear()
        self._is_shutdown = True


class PythonExecExecutorResolver(DependencyResolver[CodeExecutor]):
    """Dependency resolver that creates PythonExecExecutor instances.

    This resolver can be configured with whitelisted imports and default imports
    that will be passed to each created executor instance. Each agent gets its
    own cached executor instance through the guild_id/agent_id cache structure.
    """

    memoize_resolution = True  # Cache per agent since the cache structure already provides isolation

    def __init__(
        self, whitelisted_imports: Optional[Set[str]] = None, default_imports: Optional[Dict[str, str]] = None
    ):
        super().__init__()
        self.whitelisted_imports = whitelisted_imports
        self.default_imports = default_imports

    def resolve(self, guild_id: str, agent_id: str) -> CodeExecutor:
        """Create a new PythonExecExecutor instance for the given guild/agent.
        The instance will be cached and reused for subsequent calls from the
        same agent, but different agents get different instances.

        Args:
            guild_id: The ID of the guild requesting the executor
            agent_id: The ID of the agent requesting the executor

        Returns:
            A new or cached PythonExecExecutor instance configured with the resolver's
            import settings
        """
        return PythonExecExecutor(whitelisted_imports=self.whitelisted_imports, default_imports=self.default_imports)
