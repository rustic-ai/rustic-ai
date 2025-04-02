import logging
from abc import ABC, abstractmethod
from random import uniform
from time import sleep

from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import Message


# Custom Exceptions
class MessageProcessingError(Exception):
    """Raised when there's an error in processing a message."""


class BackoffStrategy(ABC):
    """
    An abstract base class for defining backoff strategies.

    Backoff strategies are used by the RetryingClient to determine the delay time between retries.

    To create a custom backoff strategy, inherit from this class and implement the `get_delay` method.

    Example usage:
    ```
    class MyBackoffStrategy(BackoffStrategy):
        def get_delay(self, attempt):
            # calculate the delay time for the given retry attempt
            # ...
            return delay_time
    ```
    """

    @abstractmethod
    def get_delay(self, attempt: int) -> float:
        """
        Return the delay (in seconds) for a given retry attempt number.

        Args:
            attempt: The retry attempt number.

        Returns:
            The delay time (in seconds) for the given retry attempt.
        """
        pass  # pragma: no cover


class FixedBackoff(BackoffStrategy):
    """
    A backoff strategy that uses a fixed delay time between retries.

    Example usage:
    ```
    backoff_strategy = FixedBackoff(1.0)  # use a delay of 1 second between retries
    ```
    """

    def __init__(self, delay: float):
        """
        Initialize the FixedBackoff strategy with a fixed delay time.

        Args:
            delay: The delay time (in seconds) to use between retries.
        """
        self.delay = delay

    def get_delay(self, attempt: int) -> float:
        """
        Return the fixed delay time for all retry attempts.

        Args:
            attempt: The retry attempt number.

        Returns:
            The fixed delay time (in seconds).
        """
        return self.delay


class ExponentialBackoff(BackoffStrategy):
    """
    A backoff strategy that uses an exponentially increasing delay time between retries.

    Example usage:
    ```
    backoff_strategy = ExponentialBackoff()  # use an initial delay of 1 second and double the delay time with each retry
    ```
    """

    def __init__(self, initial_delay: float = 1.0):
        """
        Initialize the ExponentialBackoff strategy with an initial delay time.

        Args:
            initial_delay: The initial delay time (in seconds) to use for the first retry attempt.
        """
        self.initial_delay = initial_delay

    def get_delay(self, attempt: int) -> float:
        """
        Return the delay time for the given retry attempt using an exponentially increasing delay time.

        Args:
            attempt: The retry attempt number.

        Returns:
            The delay time (in seconds) for the given retry attempt.
        """
        return self.initial_delay * (2**attempt)


class RandomizedExponentialBackoff(ExponentialBackoff):
    """
    A backoff strategy that uses an exponentially increasing delay time between retries with randomization.

    Example usage:
    ```
    backoff_strategy = RandomizedExponentialBackoff()  # use an initial delay of 1 second and double the delay time with each retry, with randomization
    ```
    """

    def get_delay(self, attempt: int) -> float:
        """
        Return the delay time for the given retry attempt using an exponentially increasing delay time with randomization.

        Args:
            attempt: The retry attempt number.

        Returns:
            The delay time (in seconds) for the given retry attempt, with randomization.
        """
        delay = super().get_delay(attempt)
        delay2 = 2 * delay
        # Randomize between the delay and twice the delay
        ret_val = uniform(delay, delay2)

        if ret_val < delay:  # pragma: no cover
            ret_val = delay

        if ret_val > delay2:  # pragma: no cover
            ret_val = delay2
        return ret_val


class RetryingClient(Client):
    """
    A client that retries message processing a specified number of times using a specified backoff strategy.

    Args:
        client: The underlying client to use for message processing.
        max_retries: The maximum number of times to retry message processing.
        backoff_strategy: The backoff strategy to use for determining the delay time between retries.
    """

    def __init__(self, client: Client, max_retries: int, backoff_strategy: BackoffStrategy):
        super().__init__(f"retry_{client.id}", f"retry_{client.name}", self.retrying_handle_message)
        self._client = client
        self.max_retries = max_retries
        self.backoff_strategy = backoff_strategy

        if max_retries <= 0:
            raise ValueError("max_retries must be greater than 0.")

        # Replace the client's handle_message with a retrying version
        self._original_handle_message = client._message_handler
        client._message_handler = self.retrying_handle_message

    def notify_new_message(self, message: Message):
        """
        Redirects the message notifications to the underlying client without invoking its own handle_message.

        Args:
            message: The message to notify the underlying client about.
        """
        self._client.notify_new_message(message)

    def retrying_handle_message(self, message: Message):
        """
        A retrying version of handle_message that invokes the original handle_message with a retry wrapper.

        Args:
            message: The message to process.
        """
        for attempt in range(self.max_retries):
            try:
                self._original_handle_message(message)
                break
            except Exception as e:
                if attempt < self.max_retries - 1:
                    sleep_time = self.backoff_strategy.get_delay(attempt)
                    logging.warning(f"Failed to process message. Retrying... (attempt {attempt + 1})")
                    logging.warning(
                        f"""|
                        Encountered Error: {e}
                        Sleeping for {sleep_time} seconds."""
                    )
                    sleep(sleep_time)
                else:
                    logging.error(f"Failed after {self.max_retries} attempts. Error: {e}")
