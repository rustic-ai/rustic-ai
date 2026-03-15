"""NATS connection manager - provides async-to-sync bridge for nats-py."""

import asyncio
import logging
import ssl
import threading
from typing import Optional, Union

from pydantic import BaseModel, Field


class NATSBackendConfig(BaseModel):
    """Configuration for the NATS messaging backend."""

    servers: list = Field(default_factory=lambda: ["nats://localhost:4222"])
    name: Optional[str] = Field(default=None)
    user: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    token: Optional[str] = Field(default=None)
    tls: bool = Field(default=False)
    connect_timeout: float = Field(default=10.0)
    reconnect_time_wait: float = Field(default=2.0)
    max_reconnect_attempts: int = Field(default=-1)
    ping_interval: int = Field(default=120)
    max_outstanding_pings: int = Field(default=2)

    # Pub/sub retry and reconnection settings
    pubsub_retry_enabled: bool = Field(default=True)
    pubsub_retry_initial_delay: float = Field(default=1.0)
    pubsub_retry_max_delay: float = Field(default=60.0)
    pubsub_retry_multiplier: float = Field(default=2.0)
    pubsub_health_check_interval: float = Field(default=10.0)

    # Immediate retry settings
    pubsub_immediate_retry_attempts: int = Field(default=3)
    pubsub_immediate_retry_delay: float = Field(default=0.1)
    pubsub_immediate_retry_multiplier: float = Field(default=2.0)

    # Fail-fast settings
    pubsub_max_retry_attempts: int = Field(default=5)
    pubsub_max_retry_time: float = Field(default=300.0)
    pubsub_crash_on_failure: bool = Field(default=True)

    # Health monitoring settings
    pubsub_health_monitoring_enabled: bool = Field(default=True)
    pubsub_health_monitor_initial_delay: float = Field(default=1.0)

    # Message TTL in seconds
    message_ttl: int = Field(default=3600)


class NATSConnectionManager:
    """Manages NATS connection lifecycle with async-to-sync bridge."""

    def __init__(self, nats_client: Union[object, NATSBackendConfig, dict]) -> None:
        """
        Initialize the connection manager.

        Args:
            nats_client: A NATS client instance, NATSBackendConfig, or dict.
                         Dict with "nats_client" key uses the provided client directly.
                         Other dicts are converted to NATSBackendConfig.
        """
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._owns_loop: bool = False
        self._client = None
        self._js = None
        self._config: Optional[NATSBackendConfig] = None
        self._owns_client: bool = False

        if isinstance(nats_client, dict):
            if "nats_client" in nats_client:
                actual_client = nats_client["nats_client"]
                if not hasattr(actual_client, "jetstream"):
                    raise ValueError("nats_client in dict must be a NATS client instance")
                # Use the client's event loop
                self._loop = getattr(actual_client, "_loop", None)
                self._client = actual_client
                self._owns_client = False
                self._owns_loop = False
            else:
                # Convert dict to NATSBackendConfig
                nats_client = NATSBackendConfig(**nats_client)

        if isinstance(nats_client, NATSBackendConfig):
            self._config = nats_client
            self._start_event_loop()
            self._client = self.run_async(self._connect(nats_client))
            self._owns_client = True
        elif hasattr(nats_client, "jetstream") and self._client is None:
            # Pre-connected NATS client
            self._loop = getattr(nats_client, "_loop", None)
            self._client = nats_client
            self._owns_client = False
            self._owns_loop = False
        elif self._client is None:
            raise ValueError("Invalid NATS client: must be NATSBackendConfig, dict, or NATS client instance")

        # If we have a client but no loop yet (loop extracted from client), ensure we can run async ops
        if self._loop is None:
            self._start_event_loop()

        # Get JetStream context (synchronous)
        self._js = self._client.jetstream()

    def _start_event_loop(self) -> None:
        """Start a dedicated event loop in a daemon thread."""
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="nats-event-loop",
        )
        self._loop_thread.start()
        self._owns_loop = True

    def run_async(self, coro, timeout: int = 30):
        """Run an async coroutine synchronously using the dedicated event loop.

        Args:
            coro: Coroutine to execute
            timeout: Timeout in seconds

        Returns:
            The result of the coroutine
        """
        if self._loop is None:
            raise RuntimeError("Event loop not initialized")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _connect(self, config: NATSBackendConfig):
        """Async helper to connect to NATS."""
        import nats as nats_module

        kwargs: dict = {
            "servers": config.servers,
            "connect_timeout": config.connect_timeout,
            "reconnect_time_wait": config.reconnect_time_wait,
            "max_reconnect_attempts": config.max_reconnect_attempts,
            "ping_interval": config.ping_interval,
            "max_outstanding_pings": config.max_outstanding_pings,
        }

        if config.name:
            kwargs["name"] = config.name
        if config.user:
            kwargs["user"] = config.user
        if config.password:
            kwargs["password"] = config.password
        if config.token:
            kwargs["token"] = config.token
        if config.tls:
            tls_context = ssl.create_default_context()
            kwargs["tls"] = tls_context

        return await nats_module.connect(**kwargs)

    def get_client(self):
        """Get the NATS client instance."""
        return self._client

    def get_js(self):
        """Get the JetStream context."""
        return self._js

    def get_config(self) -> Optional[NATSBackendConfig]:
        """Get the configuration if available."""
        return self._config

    def close(self) -> None:
        """Close the NATS connection and stop the event loop."""
        if self._owns_client and self._client:
            drain_coro = self._client.drain()
            if self._loop and self._loop.is_running():
                try:
                    self.run_async(drain_coro, timeout=5)
                except Exception as e:
                    logging.warning(f"Error draining NATS connection: {e}")
            else:
                drain_coro.close()  # Discard cleanly without RuntimeWarning

        if self._owns_loop and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread:
                self._loop_thread.join(timeout=2)
