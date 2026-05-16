"""Rate limiter for JIRA API requests."""

import asyncio
from collections import defaultdict
import logging
import time
from typing import Dict


class JiraRateLimiter:
    """
    Rate limiter to prevent hitting JIRA API rate limits.

    JIRA Cloud typically has limits around:
    - 10 requests per second per IP
    - Different limits for different endpoints
    """

    def __init__(self, requests_per_second: float = 8.0, buffer: float = 0.9):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second
            buffer: Safety buffer (0.9 = 90% of limit)
        """
        self.requests_per_second = requests_per_second * buffer
        self.min_interval = 1.0 / self.requests_per_second
        self.last_request_time: Dict[str, float] = defaultdict(float)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, endpoint: str = "default") -> None:
        """
        Acquire permission to make a request.

        Args:
            endpoint: Endpoint identifier for per-endpoint rate limiting
        """
        async with self._locks[endpoint]:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time[endpoint]

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logging.debug(f"Rate limiting {endpoint}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request_time[endpoint] = time.time()

    def handle_rate_limit_error(self, endpoint: str, retry_after: int) -> None:
        """
        Handle a rate limit error by updating the last request time.

        Args:
            endpoint: Endpoint that was rate limited
            retry_after: Seconds to wait before retry
        """
        self.last_request_time[endpoint] = time.time() + retry_after
        logging.warning(f"Rate limited on {endpoint}, retry after {retry_after}s")
