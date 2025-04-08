import traceback
from typing import List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.utils.json_utils import JsonDict


class CodeBlock(BaseModel):
    language: str
    code: str
    globals: JsonDict = Field(default_factory=lambda: JsonDict())
    locals: JsonDict = Field(default_factory=lambda: JsonDict())


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
