from litellm.utils import ModelResponse as LitellmModelResponse

from rustic_ai.core.guild.agent_ext.depends.llm.models import ChatCompletionResponse


class ResponseUtils:
    @staticmethod
    def from_litellm(litellm_response: LitellmModelResponse) -> ChatCompletionResponse:
        response_dict = litellm_response.model_dump()
        response = ChatCompletionResponse.model_validate(response_dict)

        return response
