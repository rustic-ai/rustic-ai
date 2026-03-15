"""NATS messaging backend exceptions."""


class NATSConnectionFailureError(Exception):
    """Raised when NATS connection cannot be established after maximum retries."""

    pass
