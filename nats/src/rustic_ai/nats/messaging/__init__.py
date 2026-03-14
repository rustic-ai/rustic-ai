"""NATS messaging backend module."""

from rustic_ai.nats.messaging.backend import NATSMessagingBackend
from rustic_ai.nats.messaging.connection_manager import NATSBackendConfig
from rustic_ai.nats.messaging.exceptions import NATSConnectionFailureError
from rustic_ai.nats.messaging.retry_utils import (
    apply_jitter,
    calculate_exponential_backoff,
    execute_with_retry,
)

__all__ = [
    "NATSMessagingBackend",
    "NATSBackendConfig",
    "NATSConnectionFailureError",
    "apply_jitter",
    "calculate_exponential_backoff",
    "execute_with_retry",
]
