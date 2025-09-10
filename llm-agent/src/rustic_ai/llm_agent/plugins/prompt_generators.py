from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from rustic_ai.core.utils.json_utils import JsonDict


class PromptGenerator(BaseModel, ABC):
    """Base class for prompt generators."""

    type: Literal["template"]
    update_on_message_format: str

    @abstractmethod
    def generate_prompt(self, data: JsonDict) -> str:
        """Generate a prompt based on the provided data."""
        pass


class TemplatedPromptGenerator(PromptGenerator):
    """Prompt generator that uses a template for prompts."""

    type: Literal["template"] = "template"
    update_on_message_format: str

    template: str

    def generate_prompt(self, dict: JsonDict) -> str:
        return self.template.format(**dict)
