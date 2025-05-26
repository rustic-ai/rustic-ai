from typing import List

from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.media import MediaLink


class ImageGenerationResponse(BaseModel):
    files: List[MediaLink] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    request: str = Field(default_factory=str)
