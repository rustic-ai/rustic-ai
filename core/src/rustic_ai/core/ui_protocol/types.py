from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from rustic_ai.core import AgentTag


class DataFormat(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tagged_users: list[AgentTag] = []


class TextFormat(DataFormat):
    text: str


class FileData(BaseModel):
    name: str
    url: str


class FilesWithTextFormat(DataFormat):
    files: list[FileData]
    text: Optional[str]


class QuestionFormat(DataFormat):
    options: list[str]


class QuestionResponse(BaseModel):
    data: str


class FormSchema(BaseModel):
    type: str = "object"
    properties: Dict[str, JsonValue]
    required: list[str] = []


class FormFormat(DataFormat):
    schema_: FormSchema = Field(alias="schema")


class FormResponse(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
