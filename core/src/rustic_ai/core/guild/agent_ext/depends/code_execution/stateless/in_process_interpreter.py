from io import StringIO
import sys

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)

from .code_runner import CodeRunner
from .models import CodeBlock, CodeResult


class InProcessCodeInterpreter(CodeRunner):
    def run(self, block: CodeBlock) -> CodeResult:
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = cap_stdout = StringIO()
        sys.stderr = cap_stderr = StringIO()

        exec(block.code, block.globals, block.locals)

        if "__builtins__" in block.globals:
            del block.globals["__builtins__"]

        sys.stdout = old_stdout
        sys.stderr = old_stderr

        output = cap_stdout.getvalue()
        error = cap_stderr.getvalue()
        exit_code = 0 if not error else 1

        return CodeResult(code=block, output=output, error=error, exit_code=exit_code)


class InProcessCodeInterpreterResolver(DependencyResolver[CodeRunner]):
    memoize_resolution: bool = False

    def resolve(self, guild_id: str, agent_id: str) -> CodeRunner:
        return InProcessCodeInterpreter()
