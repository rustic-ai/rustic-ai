import mimetypes
import uuid

from diffusers import StableDiffusion3Pipeline
import torch

from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import (
    Agent,
    agent,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.huggingface.agents.models import (
    ImageGenerationRequest,
    PyTorchAgentProps,
)


class RunwaymlStableDiffusionProps(PyTorchAgentProps):
    model_id: str = "stabilityai/stable-diffusion-3.5-medium"


class RunwaymlStableDiffusionAgent(Agent[RunwaymlStableDiffusionProps]):
    def __init__(self) -> None:
        """
        Initializes the RunwaymlStableDiffusionAgent with the specified agent specification and sets up the Stable Diffusion pipeline.

        Note:
            If you run into a "Fatal Python error: Bus error", try passing `safety_checker=None` to the `from_pretrained` method.
            Reference: https://huggingface.co/docs/diffusers/en/using-diffusers/loading#safety-checker

        Args:
            agent_spec (AgentSpec[RunwaymlStableDiffusionProps]): The agent specification containing the properties for the Stable Diffusion agent.
        """
        self.torch_device = self.config.torch_device
        model_id = self.config.model_id

        self._pipeline = StableDiffusion3Pipeline.from_pretrained(
            model_id, torch_dtype=torch.float32, use_safetensors=True
        )
        self._pipeline.to(torch.device(self.torch_device))

    @agent.processor(ImageGenerationRequest, depends_on=["filesystem:guild_fs:True"])
    def generate_image(self, ctx: agent.ProcessContext[ImageGenerationRequest], guild_fs: FileSystem) -> None:
        """
        Generates an image from the given prompt using the stable diffusion model.
        The underlying model takes the generation prompt as input and returns a list of images.
        The generated image format is "png".
        Note: This method leverages the filesystem dependency to save the generated images.
        """
        image_gen_request = ctx.payload

        prompt = [image_gen_request.generation_prompt] * image_gen_request.num_images
        try:
            output_images = self._pipeline(
                prompt,
                guidance_scale=image_gen_request.guidance_scale,
                num_inference_steps=image_gen_request.num_inference_steps,
                height=image_gen_request.height,
                width=image_gen_request.width,
            ).images
            result = ImageGenerationResponse(files=[], errors=[], request=image_gen_request.model_dump_json())
            for i, image in enumerate(output_images):
                filename = f"{uuid.uuid4()}.{image_gen_request.image_format}"
                try:
                    with guild_fs.open(filename, "wb") as f:
                        image.save(f)
                    # Create a MediaLink object for the image
                    media_link = MediaLink(
                        url=filename, name=filename, mimetype=mimetypes.guess_type(filename)[0], on_filesystem=True
                    )
                    result.files.append(media_link)
                except Exception as e:
                    result.errors.append(f"Failed to write image file {filename}:{e}")
            ctx.send(result)
        except Exception as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(), error_type="ImageGenerationError", error_message=str(e)
                )
            )
