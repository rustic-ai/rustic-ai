"""Shared retry utilities for Redis messaging backend."""

import logging
import random
import ssl
import time
from typing import Any, Callable, Optional

import redis

from rustic_ai.redis.messaging.connection_manager import RedisBackendConfig
from rustic_ai.redis.messaging.exceptions import RedisConnectionFailureError

# Constants for consistent jitter behavior
JITTER_MIN = 0.5
JITTER_MAX = 1.5


def apply_jitter(delay: float) -> float:
    """Apply jitter to a delay value to prevent thundering herd effect.

    Args:
        delay: The base delay value

    Returns:
        The delay with jitter applied
    """
    return delay * random.uniform(JITTER_MIN, JITTER_MAX)


def calculate_exponential_backoff(delay: float, multiplier: float, max_delay: float) -> float:
    """Calculate the next delay using exponential backoff with jitter.

    Args:
        delay: Current delay value
        multiplier: Exponential backoff multiplier
        max_delay: Maximum delay cap

    Returns:
        The next delay value with exponential backoff and jitter applied
    """
    next_delay = min(delay * multiplier, max_delay)
    return apply_jitter(next_delay)


def execute_with_retry(
    operation_name: str,
    operation_func: Callable,
    config: Optional[RedisBackendConfig],
    shutdown_event: Optional[Any] = None,
    *args,
    **kwargs,
) -> Any:
    """Execute an operation with retry logic.

    Args:
        operation_name: Name of the operation for logging
        operation_func: The function to execute
        config: Redis backend configuration
        shutdown_event: Optional shutdown event to check for early termination
        *args: Arguments to pass to operation_func
        **kwargs: Keyword arguments to pass to operation_func

    Returns:
        The result of the operation_func

    Raises:
        RedisConnectionFailureError: If operation fails after all retries
        Exception: If operation fails with non-retryable error
    """
    if not config or not config.pubsub_retry_enabled:
        return operation_func(*args, **kwargs)

    max_attempts = config.pubsub_immediate_retry_attempts
    delay = config.pubsub_immediate_retry_delay
    multiplier = config.pubsub_immediate_retry_multiplier

    last_exception: Optional[Exception] = None

    # Immediate retries with exponential backoff
    for attempt in range(max_attempts):
        try:
            result = operation_func(*args, **kwargs)
            if attempt > 0:
                logging.info(f"{operation_name} succeeded after {attempt + 1} attempts")
            return result

        except (redis.exceptions.ConnectionError, ssl.SSLError, redis.exceptions.TimeoutError) as e:
            last_exception = e

            if attempt < max_attempts - 1:
                logging.warning(f"{operation_name} failed (attempt {attempt + 1}/{max_attempts}): {e}")

                # Check for shutdown if event is available
                if shutdown_event is not None:
                    if shutdown_event.wait(delay):
                        raise RedisConnectionFailureError(f"{operation_name} aborted due to shutdown")
                else:
                    # Simple sleep for cases without shutdown event
                    time.sleep(delay)

                # Apply exponential backoff with jitter
                delay = calculate_exponential_backoff(delay, multiplier, config.pubsub_retry_max_delay)
            else:
                logging.warning(f"{operation_name} failed all {max_attempts} attempts: {e}")
                break

        except Exception as e:
            logging.error(f"{operation_name} failed with non-retryable error: {e}")
            raise

    # All attempts failed
    error_msg = f"{operation_name} failed after all retry attempts"
    if last_exception:
        error_msg += f": {last_exception}"

    logging.error(error_msg)
    raise RedisConnectionFailureError(error_msg)
