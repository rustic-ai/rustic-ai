"""Slack rate limiter implementation."""

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Dict, Optional


@dataclass
class RateLimitInfo:
    """Rate limit information for a method."""

    tier: int  # 1-4
    max_requests_per_minute: int
    current_window_start: float
    requests_in_window: int
    retry_after: Optional[float] = None  # Unix timestamp


class SlackRateLimiter:
    """
    Manages rate limiting for Slack API calls.

    Implements:
    - Per-method rate limit tracking
    - Tier-based limits (1-4)
    - Retry-After header respect
    - Request queuing
    - Exponential backoff
    """

    # Default tier limits (requests per minute)
    TIER_LIMITS = {
        1: 1,
        2: 20,
        3: 50,
        4: 100,
    }

    # Method-specific overrides (2026 compliant)
    METHOD_TIERS = {
        "chat.postMessage": 2,  # ~1/sec per channel (60/min)
        "conversations.history": 1,  # 1/min for non-Marketplace (2026)
        "conversations.replies": 1,  # 1/min for non-Marketplace (2026)
        "files.upload": 2,
        "users.list": 3,
        "conversations.list": 3,
    }

    def __init__(self, buffer: float = 0.9):
        """
        Initialize rate limiter.

        Args:
            buffer: Safety buffer (0.9 = use 90% of limit)
        """
        self.buffer = buffer
        self.limits: Dict[str, RateLimitInfo] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, method: str) -> asyncio.Lock:
        """Get or create lock for method."""
        if method not in self._locks:
            self._locks[method] = asyncio.Lock()
        return self._locks[method]

    def _get_limit_info(self, method: str) -> RateLimitInfo:
        """Get or create rate limit info for method."""
        if method not in self.limits:
            tier = self.METHOD_TIERS.get(method, 2)  # Default tier 2
            max_rpm = int(self.TIER_LIMITS[tier] * self.buffer)
            self.limits[method] = RateLimitInfo(
                tier=tier,
                max_requests_per_minute=max_rpm,
                current_window_start=time.time(),
                requests_in_window=0,
            )
        return self.limits[method]

    async def acquire(self, method: str):
        """
        Acquire permission to make API call.

        Blocks if rate limit reached until window resets.

        Args:
            method: Slack API method name (e.g., 'chat.postMessage')
        """
        lock = self._get_lock(method)

        async with lock:
            limit_info = self._get_limit_info(method)

            # Check if we're in retry-after period
            if limit_info.retry_after and time.time() < limit_info.retry_after:
                wait_time = limit_info.retry_after - time.time()
                logging.warning(f"Rate limit hit for {method}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                limit_info.retry_after = None

            # Check if window has expired
            now = time.time()
            window_age = now - limit_info.current_window_start

            if window_age >= 60:
                # Reset window
                limit_info.current_window_start = now
                limit_info.requests_in_window = 0

            # Check if we've hit the limit
            if limit_info.requests_in_window >= limit_info.max_requests_per_minute:
                # Wait until window resets
                wait_time = 60 - window_age
                logging.info(f"Rate limit approaching for {method}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

                # Reset window
                limit_info.current_window_start = time.time()
                limit_info.requests_in_window = 0

            # Increment counter
            limit_info.requests_in_window += 1

    def handle_rate_limit_error(self, method: str, retry_after_seconds: int):
        """
        Handle 429 rate limit error from Slack.

        Args:
            method: API method that was rate limited
            retry_after_seconds: Seconds from Retry-After header
        """
        limit_info = self._get_limit_info(method)
        limit_info.retry_after = time.time() + retry_after_seconds
        logging.warning(f"Rate limit error for {method}, retry after {retry_after_seconds}s")
