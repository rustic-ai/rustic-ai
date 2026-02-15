import base64
import mimetypes
from typing import Optional

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    ImageContentPart,
    ImageUrl,
    SystemMessage,
    UserMessage,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.json_utils import JsonDict
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.llm_agent_helper import LLMAgentHelper
from rustic_ai.llm_agent.llm_agent_utils import LLMAgentUtils


class LLMAgent(Agent[LLMAgentConfig]):
    """
    A simple LLM Agent that simply invokes an LLM.
    """

    _system_prompt: Optional[str] = None
    _updated: bool = False

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_no_attachments(msg),
        depends_on=["llm"],
    )
    def invoke_llm(self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM):
        """
        Invoke the LLM with the given context. All the LLM configuration parameters are passed along.
        """
        prompt = ctx.payload

        if self._system_prompt:
            # If the system prompt was updated, add it to the messages.
            messages = [SystemMessage(content=self._system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})
        elif self.config.default_system_prompt:
            # If there is a default system prompt, use it.
            messages = [SystemMessage(content=self.config.default_system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})

        LLMAgentHelper.invoke_llm_and_handle_response(
            self,
            self.config,
            llm,
            ctx,
            prompt,
        )

    @processor(
        ChatCompletionRequest,
        predicate=lambda self, msg: LLMAgentUtils.has_attachments(msg),
        depends_on=["llm", "filesystem:guild_fs:True"],
    )
    def invoke_llm_with_attachments(
        self, ctx: ProcessContext[ChatCompletionRequest], llm: LLM, guild_fs: FileSystem
    ):
        """
        Invoke the LLM with attachments. Converts filesystem image paths to base64 data URLs.
        """
        prompt = self._convert_filesystem_images_to_base64(ctx.payload, guild_fs)

        if self._system_prompt:
            messages = [SystemMessage(content=self._system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})
        elif self.config.default_system_prompt:
            messages = [SystemMessage(content=self.config.default_system_prompt)] + prompt.messages
            prompt = prompt.model_copy(update={"messages": messages})

        LLMAgentHelper.invoke_llm_and_handle_response(
            self,
            self.config,
            llm,
            ctx,
            prompt,
        )

    def _convert_filesystem_images_to_base64(
        self, request: ChatCompletionRequest, filesystem: FileSystem
    ) -> ChatCompletionRequest:
        """
        Convert filesystem image paths to base64 data URLs in the request.
        """
        request_copy = request.model_copy(deep=True)
        converted_messages = []

        for message in request_copy.messages:
            if not isinstance(message, UserMessage):
                converted_messages.append(message)
                continue

            content = message.content
            if not isinstance(content, ArrayOfContentParts):
                converted_messages.append(message)
                continue

            converted_parts = []
            for part in content.root or []:
                if isinstance(part, ImageContentPart) and part.image_url and part.image_url.url:
                    url = str(part.image_url.url)
                    # Check if this is a filesystem path (not an HTTP URL or data URL)
                    if not url.startswith(("http://", "https://", "data:")):
                        try:
                            # Read the image from filesystem and convert to base64
                            with filesystem.open(url, "rb") as f:
                                image_bytes = f.read()
                            b64_content = base64.b64encode(image_bytes).decode("utf-8")
                            mimetype = mimetypes.guess_type(url)[0] or "image/png"
                            data_url = f"data:{mimetype};base64,{b64_content}"
                            # Create new ImageContentPart with base64 data URL
                            converted_part = ImageContentPart(
                                image_url=ImageUrl(url=data_url, detail=part.image_url.detail)
                            )
                            converted_parts.append(converted_part)
                            continue
                        except Exception as e:
                            self.logger.error(f"Failed to read image {url} from filesystem: {e}")
                            # Fall through to append original part
                converted_parts.append(part)

            new_content = content.model_copy(update={"root": converted_parts})
            converted_messages.append(message.model_copy(update={"content": new_content}))

        request_copy.messages = converted_messages
        return request_copy

    def _is_system_prompt_update(self, msg: Message) -> bool:
        config = self.config
        if config.system_prompt_generator and msg.format == config.system_prompt_generator.update_on_message_format:
            return True
        return False

    @processor(JsonDict, predicate=lambda self, msg: self._is_system_prompt_update(msg))
    def update_system_prompt(self, ctx: ProcessContext[JsonDict]):
        """
        Update the system prompt using the system prompt generator.
        """
        if not self.config.system_prompt_generator:
            return

        self._system_prompt = (
            self.config.system_prompt_generator.generate_prompt(ctx.payload)
            if self.config.system_prompt_generator
            else self.config.default_system_prompt
        )
        self._updated = True
