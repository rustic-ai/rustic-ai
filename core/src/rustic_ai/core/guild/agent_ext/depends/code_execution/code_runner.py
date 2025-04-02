import sys
import traceback
from abc import ABC, abstractmethod
from io import StringIO
from typing import List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.utils.json_utils import JsonDict


class CodeBlock(BaseModel):
    language: str
    code: str
    globals: JsonDict = Field(default_factory=lambda: {})
    locals: JsonDict = Field(default_factory=lambda: {})


class CodeException(BaseModel):
    etype: str
    message: str
    traceback: List[str]

    def __str__(self):
        return f"{self.etype}: {self.message}\n{''.join(self.traceback)}"

    @classmethod
    def from_exception(cls, e: Exception):
        return cls(
            etype=type(e).__name__,
            message=str(e),
            traceback=traceback.format_exception(type(e), value=e, tb=e.__traceback__),
        )


class CodeResult(BaseModel):
    code: CodeBlock
    output: str
    error: str
    exit_code: int
    exception: Optional[CodeException] = None


class CodeRunner(ABC):

    supported_languages: List[str] = ["python"]

    @abstractmethod
    def run(self, code: CodeBlock) -> CodeResult:
        pass

    def validate_and_run(self, code: List[CodeBlock]) -> List[CodeResult]:
        results: List[CodeResult] = []
        for block in code:
            if block.language not in self.supported_languages:
                result = CodeResult(
                    code=block,
                    output="",
                    error=f"Unsupported language: {block.language}",
                    exit_code=1,
                )

            else:
                try:
                    result = self.run(block)
                except Exception as e:
                    result = CodeResult(
                        code=block,
                        output="",
                        error="",
                        exit_code=1,
                        exception=CodeException.from_exception(e),
                    )

            results.append(result)

        return results


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
