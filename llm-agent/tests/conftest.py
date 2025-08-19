import os

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority
from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver


@pytest.fixture
def generator() -> GemstoneGenerator:
    return GemstoneGenerator(1)


@pytest.fixture
def build_message_from_payload():
    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
    ) -> Message:
        # Ensure payload is a plain dict for Message payload
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        # Derive format if not provided
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else get_qualified_class_name(Message),
        )

    return _build_message_from_payload


@pytest.fixture(
    params=[
        pytest.param(
            "gpt-5",
            marks=pytest.mark.skipif("OPENAI_API_KEY" not in os.environ, reason="OPENAI_API_KEY not set"),
            id="gpt-5",
        )
    ]
)
def dependency_map(request):
    model = request.param
    return {
        "llm": DependencySpec(
            class_name=LiteLLMResolver.get_qualified_class_name(),
            properties={"model": model},
        ),
        "filesystem": DependencySpec(
            class_name=FileSystemResolver.get_qualified_class_name(),
            properties={
                "path_base": f"/tmp/tests/{shortuuid.uuid()}",
                "protocol": "file",
                "storage_options": {
                    "auto_mkdir": True,
                },
            },
        ),
    }
