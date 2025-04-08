from abc import ABC, abstractmethod
from typing import List

from .models import CodeBlock, CodeException, CodeResult


class CodeRunner(ABC):
    supported_languages: List[str] = ["python"]

    @abstractmethod
    def run(self, code: CodeBlock) -> CodeResult:
        pass

    def validate_and_run(self, code: List[CodeBlock]) -> List[CodeResult]:
        results: List[CodeResult] = []
        for block in code:
            if block.language not in self.supported_languages:
                result = CodeResult(code=block, output="", error=f"Unsupported language: {block.language}", exit_code=1)
            else:
                try:
                    result = self.run(block)
                except Exception as e:
                    result = CodeResult(
                        code=block, output="", error="", exit_code=1, exception=CodeException.from_exception(e)
                    )

            results.append(result)

        return results
