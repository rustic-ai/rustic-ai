import io
from types import SimpleNamespace

import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    ChatCompletionError,
    ChatCompletionRequest,
    FileContentPart,
    FileUrl,
    ImageContentPart,
    ImageUrl,
    ResponseCodes,
    TextContentPart,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig

from rustic_ai.testing.helpers import wrap_agent_for_testing


class AsyncFileSystem:
    asynchronous = True

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.read_paths: list[str] = []

    async def _cat_file(self, path: str) -> bytes:
        self.read_paths.append(path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class SyncFileSystem:
    asynchronous = False

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def open(self, path: str, mode: str, encoding: str | None = None):
        del encoding
        data = self.files[path]
        return io.BytesIO(data) if "b" in mode else io.StringIO(data.decode("utf-8"))


class UnusedLLM(LLM):
    def completion(self, *args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("LLM must not be invoked after attachment conversion fails")

    async def async_completion(self, *args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("LLM must not be invoked after attachment conversion fails")

    @property
    def model(self) -> str:
        return "unused-model"

    def get_config(self) -> dict:
        return {"model": self.model}


class UnusedLLMResolver(DependencyResolver[LLM]):
    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> LLM:
        return UnusedLLM()


def make_agent() -> LLMAgent:
    spec = (
        AgentBuilder(LLMAgent)
        .set_id("attachment-agent")
        .set_name("Attachment Agent")
        .set_description("Tests attachment conversion")
        .set_properties(LLMAgentConfig(model="test-model"))
        .build_spec()
    )
    dependency_map = {
        "llm": DependencySpec(class_name=get_qualified_class_name(UnusedLLMResolver), properties={}),
        "filesystem": DependencySpec(
            class_name=get_qualified_class_name(FileSystemResolver),
            properties={
                "path_base": "/tmp/rustic-attachment-test",
                "protocol": "file",
                "storage_options": {"auto_mkdir": True},
            },
        ),
    }
    agent, _ = wrap_agent_for_testing(spec, dependency_map=dependency_map)
    return agent


def attachment_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=[
            UserMessage(
                content=ArrayOfContentParts(
                    root=[
                        TextContentPart(text="Use both attachments."),
                        FileContentPart(file_url=FileUrl(url="notes.txt")),
                        ImageContentPart(image_url=ImageUrl(url="image.png")),
                    ]
                )
            )
        ]
    )


@pytest.mark.asyncio
async def test_converts_text_and_image_with_async_filesystem():
    filesystem = AsyncFileSystem({"notes.txt": b"hello", "image.png": b"\x89PNG"})

    converted = await make_agent()._convert_filesystem_images_to_base64(attachment_request(), filesystem)

    content = converted.messages[0].content
    assert isinstance(content, ArrayOfContentParts)
    assert isinstance(content.root[1], TextContentPart)
    assert "--- Content of notes.txt ---\nhello\n--- End of notes.txt ---" == content.root[1].text
    assert isinstance(content.root[2], ImageContentPart)
    assert str(content.root[2].image_url.url) == "data:image/png;base64,iVBORw=="
    assert filesystem.read_paths == ["notes.txt", "image.png"]


@pytest.mark.asyncio
async def test_converts_text_and_image_with_sync_filesystem():
    filesystem = SyncFileSystem({"notes.txt": b"hello", "image.png": b"\x89PNG"})

    converted = await make_agent()._convert_filesystem_images_to_base64(attachment_request(), filesystem)

    content = converted.messages[0].content
    assert isinstance(content, ArrayOfContentParts)
    assert isinstance(content.root[1], TextContentPart)
    assert content.root[1].text.endswith("hello\n--- End of notes.txt ---")
    assert isinstance(content.root[2], ImageContentPart)
    assert str(content.root[2].image_url.url).startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_attachment_read_failure_sends_one_sanitized_error():
    agent = make_agent()
    errors: list[ChatCompletionError] = []
    ctx = SimpleNamespace(payload=attachment_request(), send_error=errors.append)

    await LLMAgent.invoke_llm_with_attachments.__wfn__(agent, ctx, UnusedLLM(), AsyncFileSystem({}))

    assert len(errors) == 1
    assert errors[0].status_code == ResponseCodes.RESPONSE_PROCESSING_ERROR
    assert errors[0].message == "attachment_read_failed"
    assert errors[0].request_messages == []


@pytest.mark.asyncio
async def test_invalid_utf8_sends_sanitized_error_without_partial_request():
    agent = make_agent()
    errors: list[ChatCompletionError] = []
    ctx = SimpleNamespace(payload=attachment_request(), send_error=errors.append)
    filesystem = AsyncFileSystem({"notes.txt": b"\xff", "image.png": b"\x89PNG"})

    await LLMAgent.invoke_llm_with_attachments.__wfn__(agent, ctx, UnusedLLM(), filesystem)

    assert [error.message for error in errors] == ["attachment_read_failed"]
