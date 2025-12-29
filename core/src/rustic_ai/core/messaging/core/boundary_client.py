from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message


class BoundaryClient(Client):
    """
    Wrapper around any Client that adds shared namespace capabilities for cross-guild communication.

    This client enables boundary agents (Gateway, Envoy) to communicate across guild boundaries
    by providing methods to publish to and subscribe from the shared (organization) namespace.

    The BoundaryClient delegates all standard client operations to the wrapped inner client,
    while adding additional methods for shared namespace operations.

    Usage:
        # In a BoundaryContext
        boundary_client = BoundaryClient(inner_client, organization_id="org-123")

        # Send a message to another guild's inbox
        boundary_client.publish_to_guild_inbox("target-guild-id", message)
    """

    def __init__(self, inner_client: Client, organization_id: str):
        """
        Initialize the BoundaryClient.

        Args:
            inner_client: The underlying client to wrap. Can be any Client implementation
                          (MessageTrackingClient, SimpleClient, etc.)
            organization_id: The organization ID to use as the shared namespace.
        """
        # Don't call super().__init__() - we delegate to inner client
        self._inner = inner_client
        self._organization_id = organization_id
        self._shared_activated = False

    def __getattr__(self, name):
        """Delegate all unimplemented methods/attributes to the inner client."""
        return getattr(self._inner, name)

    def notify_new_message(self, message: Message) -> None:
        """Forward notifications to the wrapped client."""
        self._inner.notify_new_message(message)

    # =========================================================================
    # Shared Namespace Operations
    # =========================================================================

    def _ensure_shared_namespace(self) -> None:
        """Activate shared namespace on first use."""
        if not self._shared_activated:
            self._inner._messaging.activate_shared_namespace(self._organization_id)
            self._shared_activated = True

    def publish_to_guild_inbox(self, target_guild_id: str, message: Message) -> None:
        """
        Publish a message to another guild's inbox in the shared namespace.

        Args:
            target_guild_id: The ID of the guild to send the message to.
            message: The message to publish.
        """
        self._ensure_shared_namespace()
        message_copy = message.model_copy(deep=True)
        message_copy.topics = [f"guild_inbox:{target_guild_id}"]
        self._inner._messaging.publish_to_shared(self._inner, message_copy)
