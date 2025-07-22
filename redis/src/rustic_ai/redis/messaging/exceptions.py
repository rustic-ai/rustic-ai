"""Redis messaging backend exceptions."""


class RedisConnectionFailureError(Exception):
    """Raised when Redis connection cannot be established after maximum retries."""

    pass
