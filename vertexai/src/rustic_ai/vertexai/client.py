import os
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict


class VertexAIConf(BaseModel):
    """Configuration class for Vertex AI.

    This class is used to encapsulate configuration details required for
    interacting with Vertex AI.

    Attributes:
        project_id (Optional[str]): The Google Cloud project ID associated with
            Vertex AI.
        location (Optional[str]): The region or location where the Vertex AI
            resources are hosted.
    """

    project_id: Optional[str] = None
    location: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class VertexAIBase:
    """Base class for Google Cloud Vertex AI services.

    This class constructs an explicitly configured Google GenAI client for
    Vertex AI. Each instance keeps its own project and location; no legacy
    AI Platform global initialization is required.
    """

    _is_vertexai_initialized = False

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """Initialize this instance's Google GenAI client.

        Args:
            project_id (Optional[str]): The Google Cloud project ID. If None,
                attempts to use the VERTEXAI_PROJECT environment variable.
            location (Optional[str]): The region or location where the Vertex AI
                resources are hosted. If None, attempts to use the VERTEXAI_LOCATION
                environment variable.

        Raises:
            ValueError: If project_id or location cannot be determined from
                parameters or environment variables.
        """
        if not self._is_vertexai_initialized:
            if project_id is None:
                project_id = os.environ.get("VERTEXAI_PROJECT")

            if location is None:
                location = os.environ.get("VERTEXAI_LOCATION")

            self._is_vertexai_initialized = True
            self.genai_client = genai.Client(
                vertexai=True, project=project_id, location=location, http_options=types.HttpOptions(api_version="v1")
            )
