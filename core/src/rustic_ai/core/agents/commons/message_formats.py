from pydantic import BaseModel


class GenerationPromptRequest(BaseModel):
    """
    A class representing a text generation request.
    """

    generation_prompt: str


class GenerationPromptResponse(BaseModel):
    """
    A class representing a text generation response.
    """

    generation_prompt: str
    generated_response: str


class ErrorMessage(BaseModel):
    """
    A class representing an error message.
    """

    agent_type: str
    error_type: str
    error_message: str
