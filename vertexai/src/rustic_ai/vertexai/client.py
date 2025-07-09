import os
from typing import Optional

from google import genai
from google.cloud import aiplatform
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

    This class handles the common initialization pattern for the Vertex AI SDK,
    ensuring that it's only initialized once per runtime. Other Vertex AI
    service implementations can inherit from this class to reuse this logic.
    """

    _is_vertexai_initialized = False

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """Initialize Vertex AI SDK if not already initialized.

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

            aiplatform.init(project=project_id, location=location)
            self._is_vertexai_initialized = True
            self.genai_client = genai.Client(
                vertexai=True, project=project_id, location=location, http_options=types.HttpOptions(api_version="v1")
            )
