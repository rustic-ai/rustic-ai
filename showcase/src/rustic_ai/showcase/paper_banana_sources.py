"""Guild-owned bounded acquisition for uploaded web links."""

from dataclasses import dataclass
from email.message import Message
from pathlib import PurePosixPath
import time
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import aiohttp

from rustic_ai.core.guild.agent_ext.depends import DependencyResolver


def source_uri(url: str) -> str:
    """Keep attribution without propagating signed query strings or fragments."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))


def origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Invalid upload URL")
    return parts.scheme, parts.hostname.lower(), parts.port or (443 if parts.scheme == "https" else 80)


@dataclass(frozen=True)
class AcquiredUpload:
    data: bytes
    name: str | None
    mime_type: str | None


class HttpUploadSourceReader:
    """Network policy and credentials belong to the configured guild dependency."""

    def __init__(self, allowed_origins: list[str], headers: dict[str, str] | None = None):
        self.allowed_origins = frozenset(origin(value) for value in allowed_origins)
        self.headers = dict(headers or {})

    def staged_path(self, url: str, guild_id: str, guild_path: str) -> str:
        """Resolve upload transport references within the selected guild filesystem."""
        parts = urlsplit(url)
        path = parts.path
        api_prefix = "/rustic/api/guilds/"
        if path.startswith(api_prefix):
            prefix = api_prefix + guild_id + "/files/"
            if parts.scheme or parts.netloc or not path.startswith(prefix):
                raise ValueError("Upload does not belong to this guild")
            path = unquote(path[len(prefix) :])
        elif parts.scheme == "file":
            if parts.netloc:
                raise ValueError("Invalid staged file host")
            path = unquote(path)
            root = guild_path.rstrip("/") + "/"
            path = path[len(root) :] if root != "/" and path.startswith(root) else path.lstrip("/")
        elif not parts.scheme and not parts.netloc:
            path = url  # A staged filename may contain literal query/fragment characters.
            if path.startswith("/"):
                root = guild_path.rstrip("/") + "/"
                if root == "/" or not path.startswith(root):
                    raise ValueError("Source is outside the staged filesystem")
                path = path[len(root) :]
        else:
            raise ValueError("Invalid staged source URL")
        if not path or path.startswith("/") or ".." in PurePosixPath(path).parts or "\\" in path or "\0" in path:
            raise ValueError("Invalid staged path")
        return path

    async def read(self, url: str, max_bytes: int, deadline: float) -> AcquiredUpload:
        if len(url) > 4096 or max_bytes < 0:
            raise ValueError("Invalid upload source")
        initial_origin = origin(url)
        async with aiohttp.ClientSession(trust_env=False, cookie_jar=aiohttp.DummyCookieJar()) as session:
            for _ in range(4):
                if origin(url) not in self.allowed_origins:
                    raise ValueError("Upload origin is not configured")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Upload deadline expired")
                async with session.get(
                    url,
                    headers=self.headers if origin(url) == initial_origin else {},
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=remaining),
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError("Upload redirect has no destination")
                        url = urljoin(url, location)
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(min(65536, max_bytes + 1)):
                        if len(data) + len(chunk) > max_bytes:
                            raise ValueError("Upload exceeds byte limit")
                        data.extend(chunk)
                    disposition = Message()
                    disposition["Content-Disposition"] = response.headers.get("Content-Disposition", "")
                    name = disposition.get_filename()
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0] or None
                    return AcquiredUpload(bytes(data), name, mime)
        raise ValueError("Upload redirect limit exceeded")


class HttpUploadSourceResolver(DependencyResolver[HttpUploadSourceReader]):
    def __init__(self, allowed_origins: list[str] | None = None, headers: dict[str, str] | None = None):
        super().__init__()
        self.reader = HttpUploadSourceReader(allowed_origins or [], headers)

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> HttpUploadSourceReader:
        return self.reader
