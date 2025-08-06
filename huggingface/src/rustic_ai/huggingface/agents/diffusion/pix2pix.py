import mimetypes
import uuid

from PIL import Image, ImageOps
from diffusers import (
    EulerAncestralDiscreteScheduler,
    StableDiffusionInstructPix2PixPipeline,
)
import torch

from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.huggingface.agents.models import (
    ImageGenerationRequest,
    PyTorchAgentProps,
)


class ImageQuery(ImageGenerationRequest):
    image_path: str


class Pix2PixProps(PyTorchAgentProps):
    model_id: str = "timbrooks/instruct-pix2pix"


class Image2ImageAgent(Agent[Pix2PixProps]):
    """
    Generate image from a given image and a query
    """

    def __init__(self):
        self.torch_device = self.config.torch_device
        model_id = self.config.model_id

        self._pipeline = StableDiffusionInstructPix2PixPipeline.from_pretrained(model_id, safety_checker=None)
        self._pipeline.scheduler = EulerAncestralDiscreteScheduler.from_config(self._pipeline.scheduler.config)
        self._pipeline.to(torch.device(self.torch_device))

    @agent.processor(ImageQuery, depends_on=["filesystem:guild_fs:True"])
    def process_user_query(self, ctx: ProcessContext[ImageQuery], guild_fs: FileSystem) -> None:
        """
        Process the users query
        """
        image_gen_request = ctx.payload

        try:
            with guild_fs.open(image_gen_request.image_path, "rb") as f:
                loaded_image = Image.open(f)
                image = ImageOps.exif_transpose(loaded_image)
                if image is not None:
                    image = image.convert("RGB")
                else:
                    raise ValueError("Image cannot be none")

            prompt = [image_gen_request.generation_prompt] * image_gen_request.num_images
            image_input = [image] * image_gen_request.num_images
            output_images = self._pipeline(
                prompt,
                image=image_input,
                num_inference_steps=image_gen_request.num_inference_steps,
                guidance_scale=image_gen_request.guidance_scale,
                height=image_gen_request.height,
                width=image_gen_request.width,
            ).images

            result = ImageGenerationResponse(files=[], errors=[], request=image_gen_request.model_dump_json())
            for output_image in output_images:
                filename = f"{uuid.uuid4()}.{image_gen_request.image_format}"
                try:
                    with guild_fs.open(filename, "wb") as f:
                        output_image.save(f)
                    media_link = MediaLink(
                        url=filename, name=filename, mimetype=mimetypes.guess_type(filename)[0], on_filesystem=True
                    )
                    result.files.append(media_link)
                except Exception as e:
                    result.errors.append(f"Failed to write image file {filename}:{e}")
            ctx.send(result)
        except Exception as ex:
            ctx.send(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="ImageGenerationError",
                    error_message=str(ex),
                )
            )
