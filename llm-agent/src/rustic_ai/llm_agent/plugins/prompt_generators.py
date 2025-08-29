from typing import Literal

from pydantic import BaseModel

from rustic_ai.core.utils.json_utils import JsonDict


class PromptGenerator(BaseModel):
    """Base class for prompt generators."""

    type: Literal["template"]
    update_on_message_format: str

    def generate_prompt(self, data: JsonDict) -> str:
        raise NotImplementedError("Subclasses must implement this method.")


class TemplatedPromptGenerator(PromptGenerator):
    """Prompt generator that uses a template for prompts."""

    type: Literal["template"] = "template"
    update_on_message_format: str

    template: str

    def generate_prompt(self, dict: JsonDict) -> str:
        return self.template.format(**dict)
