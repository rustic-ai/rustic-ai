import mimetypes
from typing import Literal, Optional
import uuid

from google.genai import errors, types
from google.genai.types import PersonGeneration, SafetyFilterLevel
from pydantic import BaseModel

from rustic_ai.core import Agent
from rustic_ai.core.agents.commons.image_generation import ImageGenerationResponse
from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.vertexai.client import VertexAIBase, VertexAIConf


class VertexAiImagenAgentProps(BaseAgentProps, VertexAIConf):
    model_id: str = "imagen-3.0-fast-generate-001"
    add_watermark: Optional[bool] = True
    safety_filter_level: Optional[SafetyFilterLevel] = None
    person_generation: Optional[PersonGeneration] = None


class VertexAiImageGenerationRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    number_of_images: int = 1
    aspect_ratio: Optional[Literal["1:1", "9:16", "16:9", "4:3", "3:4"]] = None
    guidance_scale: Optional[float] = None
    language: Optional[str] = None
    seed: Optional[int] = None
    image_format: Optional[str] = "png"


class VertexAiImagenAgent(Agent[VertexAiImagenAgentProps], VertexAIBase):
    def __init__(self):
        VertexAIBase.__init__(self, self.config.project_id, self.config.location)
        print("initialized vertexai")

    @agent.processor(VertexAiImageGenerationRequest, depends_on=["filesystem:guild_fs:True"])
    def generate_image(self, ctx: agent.ProcessContext[VertexAiImageGenerationRequest], guild_fs: FileSystem) -> None:
        image_gen_request = ctx.payload
        gen_error_msg = "Failed to generate image as the prompt was too complicated or triggered a safety mechanism."
        result = ImageGenerationResponse(files=[], errors=[], request=image_gen_request.model_dump_json())
        try:
            model_response = self.genai_client.models.generate_images(
                model=self.config.model_id,
                prompt=image_gen_request.prompt,
                config=types.GenerateImagesConfig(
                    negative_prompt=image_gen_request.negative_prompt,
                    number_of_images=image_gen_request.number_of_images,
                    aspect_ratio=image_gen_request.aspect_ratio,
                    guidance_scale=image_gen_request.guidance_scale,
                    language=image_gen_request.language,
                    seed=image_gen_request.seed,
                    add_watermark=self.config.add_watermark,
                    safety_filter_level=self.config.safety_filter_level,
                    person_generation=self.config.person_generation,
                ),
            )

            output_images = model_response.generated_images if model_response.generated_images else []
            if not output_images:
                self.logger.info(f"Failed to generate image. Prompt was: {image_gen_request.prompt}")
                result.errors.append(gen_error_msg)
            else:
                for i, generated_image in enumerate(output_images):
                    if generated_image.image is not None:
                        # Note: the result is not a PIL.Image object but a custom Google one
                        image_obj: types.Image = generated_image.image

                        if image_obj.image_bytes is None:
                            self.logger.info(f"Failed to generate image. Prompt was: {image_gen_request.prompt}")
                            result.errors.append(gen_error_msg)
                            continue
                        filename = f"{uuid.uuid4()}.{image_gen_request.image_format}"
                        try:
                            with guild_fs.open(filename, "wb") as f:
                                f.write(image_obj.image_bytes)

                            # Create a MediaLink object for the image
                            media_link = MediaLink(
                                url=filename,
                                name=filename,
                                mimetype=mimetypes.guess_type(filename)[0],
                                on_filesystem=True,
                            )
                            result.files.append(media_link)
                        except Exception as e:
                            result.errors.append(f"Failed to write image file {filename}:{e}")
        except errors.APIError as generation_error:
            self.logger.error(
                f"Failed to generate image: {generation_error.message}. Prompt was: {image_gen_request.prompt}"
            )
            result.errors.append(f"Failed to generate image. {generation_error.message}")
        finally:
            ctx.send(result)
