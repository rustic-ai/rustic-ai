from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from rustic_ai.core.agents.commons.media import MediaLink, MediaUtils
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionRequest,
    FileContentPart,
    ImageContentPart,
    UserMessage,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils.json_utils import JsonDict


class LLMAgentUtils:
    @staticmethod
    def has_attachments(message: Message) -> bool:
        """
        Check if the payload has attachments.
        """
        payload: JsonDict = message.payload
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            return False

        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue

            content = msg.get("content")
            # content can be:
            # - dict with key "root": [...]
            # - list (from Pydantic RootModel dumps)
            # - str (plain text) -> ignore
            root = []
            if isinstance(content, dict):
                maybe_root = content.get("root", [])
                if isinstance(maybe_root, list):
                    root = maybe_root
            elif isinstance(content, list):
                root = content
            else:
                # Non-collection content (e.g., a plain string) should be ignored safely
                continue

            for part in root:
                if isinstance(part, dict) and ("file_url" in part or "image_url" in part):
                    return True

        return False

    @staticmethod
    def has_no_attachments(message: Message) -> bool:
        """
        Check if the payload has no attachments.
        """
        return not LLMAgentUtils.has_attachments(message)

    @staticmethod
    def is_http_url(url: str | None) -> bool:
        if not url:
            return False
        # Robust guard in case url is not a plain str (e.g., AnyUrl)
        try:
            s = str(url)
        except Exception:
            return False
        return s.startswith("http://") or s.startswith("https://")

    @staticmethod
    def filter_attachments(payload: ChatCompletionRequest, keep_http_attachments: bool) -> ChatCompletionRequest:
        """
        Remove attachments from the payload.
        If keep_http_attachments is True, retain file/image attachments whose URL starts with http(s).
        """
        payload_copy = payload.model_copy(deep=True)
        filtered_messages = []

        for message in payload_copy.messages:
            # Keep non-user messages as-is
            if not isinstance(message, UserMessage):
                filtered_messages.append(message)
                continue

            content = message.content

            # For plain text content, keep as-is
            if isinstance(content, str) or content is None:
                filtered_messages.append(message)
                continue

            # For structured content (ArrayOfContentParts), remove only attachments
            if isinstance(content, ArrayOfContentParts):
                parts = list(getattr(content, "root", []) or [])

                kept_parts = []
                for part in parts:
                    # Keep non-attachment parts always
                    if not isinstance(part, (FileContentPart, ImageContentPart)):
                        kept_parts.append(part)
                        continue

                    # For attachments, only keep if HTTP(S) and flag allows
                    if keep_http_attachments:
                        if isinstance(part, FileContentPart):
                            url = getattr(getattr(part, "file_url", None), "url", None)
                            if LLMAgentUtils.is_http_url(url):
                                kept_parts.append(part)
                                continue
                        elif isinstance(part, ImageContentPart):
                            url = getattr(getattr(part, "image_url", None), "url", None)
                            if LLMAgentUtils.is_http_url(url):
                                kept_parts.append(part)
                                continue

                # If no non-attachment parts remain, preserve the message with empty string content
                if not kept_parts:
                    filtered_messages.append(message.model_copy(update={"content": ""}))
                    continue

                new_content = content.model_copy(update={"root": kept_parts})
                filtered_messages.append(message.model_copy(update={"content": new_content}))
                continue

            # Unknown content type: keep as-is
            filtered_messages.append(message)

        payload_copy.messages = filtered_messages

        return payload_copy

    @staticmethod
    def extract_attachments(payload: ChatCompletionRequest, filesystem: FileSystem) -> list[MediaLink]:
        """
        Extract attachments (files/images) from user messages as MediaLink objects.
        Only FileContentPart and ImageContentPart are extracted; text parts are ignored.
        """
        attachments: list[MediaLink] = []

        for message in payload.messages:
            if not isinstance(message, UserMessage):
                continue

            content = message.content
            if not isinstance(content, ArrayOfContentParts):
                # Plain strings or other types have no structured attachments
                continue

            for part in content.root or []:
                if isinstance(part, FileContentPart) and part.file_url and part.file_url.url:
                    url = part.file_url.url
                    attachments.append(MediaUtils.medialink_from_file(filesystem, url))
                elif isinstance(part, ImageContentPart) and part.image_url and part.image_url.url:
                    url = part.image_url.url
                    attachments.append(MediaUtils.medialink_from_file(filesystem, url))

        return attachments

    @staticmethod
    def extract_last_user_message(payload: ChatCompletionRequest) -> UserMessage | None:
        """
        Extract the last user message from the payload.
        """
        for message in reversed(payload.messages):
            if isinstance(message, UserMessage):
                return message
        return None
