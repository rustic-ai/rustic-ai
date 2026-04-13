"""Slack API client wrapper."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from cachetools import TTLCache
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from rustic_ai.slack.client.rate_limiter import SlackRateLimiter


class SlackAPIClient:
    """
    Wrapper around slack-sdk WebClient with rate limiting, retry logic, and caching.
    """

    def __init__(
        self,
        token: str,
        rate_limit_buffer: float = 0.9,
        max_retries: int = 3,
        enable_caching: bool = True,
        cache_ttl: int = 300,
    ):
        """
        Initialize Slack API client.

        Args:
            token: Slack bot token (xoxb-)
            rate_limit_buffer: Safety buffer for rate limits (0.9 = 90%)
            max_retries: Maximum retry attempts for failed requests
            enable_caching: Enable caching for users/channels
            cache_ttl: Cache time-to-live in seconds
        """
        self.client = WebClient(token=token)
        self.rate_limiter = SlackRateLimiter(buffer=rate_limit_buffer)
        self.max_retries = max_retries
        self.enable_caching = enable_caching

        # Caches
        if enable_caching:
            self._user_cache: Optional[TTLCache] = TTLCache(maxsize=1000, ttl=cache_ttl)
            self._channel_cache: Optional[TTLCache] = TTLCache(maxsize=500, ttl=cache_ttl)
        else:
            self._user_cache = None
            self._channel_cache = None

    async def _make_request(self, method: str, **kwargs) -> Dict[str, Any]:
        """Make rate-limited API request with retry logic."""
        await self.rate_limiter.acquire(method)

        for attempt in range(self.max_retries):
            try:
                # Run sync slack-sdk call in thread pool
                loop = asyncio.get_event_loop()
                # Use api_call with json parameter instead of direct kwargs
                response = await loop.run_in_executor(
                    None, lambda: self.client.api_call(method, json=kwargs)
                )
                # SlackResponse has a .data attribute that contains the actual dict
                return response.data
            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    self.rate_limiter.handle_rate_limit_error(method, retry_after)
                    # Retry after waiting
                    await asyncio.sleep(retry_after)
                    continue
                elif attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2**attempt
                    logging.warning(f"Request failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        raise RuntimeError(f"Max retries exceeded for {method}")

    # Message Operations

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict]] = None,
        reply_broadcast: bool = False,
        username: Optional[str] = None,
        icon_url: Optional[str] = None,
        icon_emoji: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message to a channel."""
        params: Dict[str, Any] = {
            "channel": channel,
            "text": text,
        }

        if thread_ts:
            params["thread_ts"] = thread_ts
        if blocks:
            params["blocks"] = blocks
        if reply_broadcast:
            params["reply_broadcast"] = reply_broadcast
        if username:
            params["username"] = username
        if icon_url:
            params["icon_url"] = icon_url
        if icon_emoji:
            params["icon_emoji"] = icon_emoji

        return await self._make_request("chat.postMessage", **params)

    async def update_message(
        self, channel: str, ts: str, text: str, blocks: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Update an existing message."""
        params: Dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }

        if blocks:
            params["blocks"] = blocks

        return await self._make_request("chat.update", **params)

    async def delete_message(self, channel: str, ts: str) -> Dict[str, Any]:
        """Delete a message."""
        return await self._make_request("chat.delete", channel=channel, ts=ts)

    async def get_conversation_history(
        self,
        channel: str,
        limit: int = 100,
        cursor: Optional[str] = None,
        oldest: Optional[str] = None,
        newest: Optional[str] = None,
        inclusive: bool = False,
    ) -> Dict[str, Any]:
        """Fetch message history from a channel."""
        params = {
            "channel": channel,
            "limit": limit,
            "inclusive": inclusive,
        }

        if cursor:
            params["cursor"] = cursor
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        return await self._make_request("conversations.history", **params)

    async def get_thread_replies(
        self, channel: str, thread_ts: str, cursor: Optional[str] = None, limit: int = 100
    ) -> Dict[str, Any]:
        """Fetch replies in a thread."""
        params = {
            "channel": channel,
            "ts": thread_ts,
            "limit": limit,
        }

        if cursor:
            params["cursor"] = cursor

        return await self._make_request("conversations.replies", **params)

    # Channel Operations

    async def list_conversations(
        self,
        types: Optional[List[str]] = None,
        exclude_archived: bool = True,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all channels."""
        if types is None:
            types = ["public_channel"]

        params: Dict[str, Any] = {
            "types": ",".join(types),
            "exclude_archived": exclude_archived,
            "limit": limit,
        }

        if cursor:
            params["cursor"] = cursor

        return await self._make_request("conversations.list", **params)

    async def create_channel(self, name: str, is_private: bool = False) -> Dict[str, Any]:
        """Create a new channel."""
        return await self._make_request("conversations.create", name=name, is_private=is_private)

    async def join_channel(self, channel: str) -> Dict[str, Any]:
        """Join a channel."""
        return await self._make_request("conversations.join", channel=channel)

    async def invite_to_channel(self, channel: str, users: List[str]) -> Dict[str, Any]:
        """Invite users to a channel."""
        return await self._make_request("conversations.invite", channel=channel, users=",".join(users))

    # User Operations

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get information about a user."""
        # Check cache
        if self.enable_caching and self._user_cache is not None and user_id in self._user_cache:
            return self._user_cache[user_id]

        result = await self._make_request("users.info", user=user_id)

        # Cache result
        if self.enable_caching and self._user_cache is not None:
            self._user_cache[user_id] = result

        return result

    async def list_users(self, limit: int = 100, cursor: Optional[str] = None) -> Dict[str, Any]:
        """List all users in workspace."""
        params: Dict[str, Any] = {"limit": limit}

        if cursor:
            params["cursor"] = cursor

        return await self._make_request("users.list", **params)

    # Reaction Operations

    async def add_reaction(self, channel: str, timestamp: str, name: str) -> Dict[str, Any]:
        """Add a reaction to a message."""
        return await self._make_request("reactions.add", channel=channel, timestamp=timestamp, name=name)

    async def get_reactions(self, channel: str, timestamp: str) -> Dict[str, Any]:
        """Get reactions for a message."""
        return await self._make_request("reactions.get", channel=channel, timestamp=timestamp)

    # File Operations

    async def upload_file(
        self, channels: List[str], content: bytes, filename: str, title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload a file using 2-step process."""
        # Step 1: Get upload URL
        upload_url_response = await self._make_request(
            "files.getUploadURLExternal", filename=filename, length=len(content)
        )

        upload_url = upload_url_response["upload_url"]
        file_id = upload_url_response["file_id"]

        # Step 2: Upload file to URL
        asyncio.get_event_loop()

        async with aiohttp.ClientSession() as session:
            async with session.post(upload_url, data=content) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"File upload failed: {await resp.text()}")

        # Step 3: Complete upload
        complete_params = {
            "files": [{"id": file_id, "title": title or filename}],
            "channel_id": channels[0] if channels else None,
        }

        return await self._make_request("files.completeUploadExternal", **complete_params)

    async def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """Get information about a file."""
        return await self._make_request("files.info", file=file_id)

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete a file."""
        return await self._make_request("files.delete", file=file_id)
