from pydantic import Field

from rustic_ai.core.agents.commons import GenerationPromptRequest
from rustic_ai.core.guild import BaseAgentProps


class PyTorchAgentProps(BaseAgentProps):
    """
    Properties for the HuggingFace PyTorch agent.
    """

    torch_device: str = Field(default="cpu", title="Torch device to use for inference")
    model_id: str = Field(title="HuggingFace Model ID to use")


class ImageGenerationRequest(GenerationPromptRequest):
    """
    Represents a request for generating images using a given generation model.

    Args:
        num_images: The number of images to generate. Default is 1.
        height: The height of the generated images. Default is 512.
        width: The width of the generated images. Default is 512.
        num_inference_steps: The number of inference steps for generating the images. Default is 50.
        image_format: The format of the generated images. Default is "png".
        guidance_scale: The scale used for guiding the image generation. Default is 7.5.
    """

    num_images: int = Field(default=1)
    height: int = Field(default=512)
    width: int = Field(default=512)
    num_inference_steps: int = Field(default=50)
    image_format: str = Field(default="png")
    guidance_scale: float = Field(default=7.5)
