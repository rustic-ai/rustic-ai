from typing import Optional, Union

from litellm.utils import ModelResponse as LitellmModelResponse
from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.core.utils.json_utils import JsonDict


class ResponseUtils:
    @staticmethod
    def from_litellm(litellm_response: LitellmModelResponse) -> ChatCompletionResponse:
        response_dict = litellm_response.model_dump()
        response = ChatCompletionResponse.model_validate(response_dict)

        return response


def transform_response_format(value: Optional[Union[dict, str]]):
    if value is None:
        return None
    result: JsonDict = {
        "type": "json_schema",
        "json_schema": {
            "schema": {},
            "strict": True
        },
    }
    if isinstance(value, dict):
        result["json_schema"]["schema"] = value
        return result
    if isinstance(value, str):
        format_type = get_class_from_name(value)
        # If it's a Pydantic model class, convert to JSON schema
        if isinstance(format_type, type) and issubclass(format_type, BaseModel):
            result["json_schema"]["schema"] = format_type.model_json_schema()
            return result
    return None
