import threading
from typing import Any, Dict

from pydantic import BaseModel

from rustic_ai.core.messaging.core.message import AgentTag, Message, MessageConstants
from rustic_ai.core.utils import GemstoneGenerator, Priority

DEAD_LETTER_FALLBACK_NAMESPACE = "__dead_letter__"
DEAD_LETTER_QUEUE = "dead_letter_queue"

_DEAD_LETTER_GENERATOR = GemstoneGenerator(machine_id=0)
_DEAD_LETTER_GENERATOR_LOCK = threading.Lock()


class DeliveryFailurePayload(BaseModel):
    delivery_backend: str
    client_id: str
    original_topic: str
    original_message_id: int
    original_message: Dict[str, Any]
    error_type: str
    error_message: str


def build_dead_letter_message(
    *,
    backend_name: str,
    client_id: str,
    original_topic: str,
    original_message: Message,
    error: Exception,
) -> Message:
    payload = DeliveryFailurePayload(
        delivery_backend=backend_name,
        client_id=client_id,
        original_topic=original_topic,
        original_message_id=original_message.id,
        original_message=original_message.model_dump(mode="json"),
        error_type=type(error).__name__,
        error_message=str(error),
    )

    with _DEAD_LETTER_GENERATOR_LOCK:
        id_obj = _DEAD_LETTER_GENERATOR.get_id(Priority.NORMAL)

    return Message(
        id_obj=id_obj,
        sender=AgentTag(id="messaging_backend", name="MessagingBackend"),
        topics=DEAD_LETTER_QUEUE,
        payload=payload.model_dump(mode="json"),
        format=MessageConstants.RAW_JSON_FORMAT,
        in_response_to=original_message.id,
        is_error_message=True,
    )


def resolve_dead_letter_namespace(original_topic: str, namespace: str | None) -> str:
    if namespace:
        return namespace
    if ":" in original_topic:
        return original_topic.split(":", 1)[0]
    return DEAD_LETTER_FALLBACK_NAMESPACE


def resolve_dead_letter_topic(original_topic: str, namespace: str | None) -> str:
    if namespace and original_topic.startswith(f"{namespace}:"):
        return f"{namespace}:{DEAD_LETTER_QUEUE}"
    if ":" in original_topic:
        prefix = original_topic.split(":", 1)[0]
        return f"{prefix}:{DEAD_LETTER_QUEUE}"
    return DEAD_LETTER_QUEUE
