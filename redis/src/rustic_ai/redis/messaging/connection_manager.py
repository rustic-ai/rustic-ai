import logging
import socket
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field
import redis
from redis.cluster import ClusterNode


class RedisBackendConfig(BaseModel):
    host: str
    port: int
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    ssl: bool = Field(default=False)
    ssl_certfile: Optional[str] = Field(default=None)
    ssl_keyfile: Optional[str] = Field(default=None)
    ssl_ca_certs: Optional[str] = Field(default=None)
    is_cluster: bool = Field(default=False)

    # Connection keepalive and stability settings
    socket_keepalive: bool = Field(default=True)
    socket_keepalive_options: Optional[Dict[int, int]] = Field(
        default_factory=lambda: {
            # Use getattr for cross-platform compatibility (Linux-specific constants)
            k: v
            for k, v in [
                (getattr(socket, "TCP_KEEPIDLE", None), 300),  # Start keepalive after 5 minutes of inactivity
                (getattr(socket, "TCP_KEEPINTVL", None), 60),  # Send keepalive probes every 60 seconds
                (getattr(socket, "TCP_KEEPCNT", None), 3),  # Close connection after 3 failed probes
            ]
            if k is not None
        }
    )
    health_check_interval: int = Field(default=30)  # Redis-level health check interval
    socket_connect_timeout: int = Field(default=10)  # Connection timeout
    socket_timeout: int = Field(default=30)  # Operation timeout

    # Pub/sub retry and reconnection settings
    pubsub_retry_enabled: bool = Field(default=True)
    pubsub_retry_initial_delay: float = Field(default=1.0)  # Initial retry delay in seconds
    pubsub_retry_max_delay: float = Field(default=60.0)  # Maximum retry delay in seconds
    pubsub_retry_multiplier: float = Field(default=2.0)  # Backoff multiplier
    pubsub_health_check_interval: float = Field(default=10.0)  # Check pub/sub health every N seconds

    # Immediate retry settings for individual operations
    pubsub_immediate_retry_attempts: int = Field(default=3)  # Quick retries before background reconnection
    pubsub_immediate_retry_delay: float = Field(default=0.1)  # Delay between immediate retries
    pubsub_immediate_retry_multiplier: float = Field(default=2.0)  # Backoff for immediate retries

    # Fail-fast settings for Ray workers
    pubsub_max_retry_attempts: int = Field(default=5)  # Max retry attempts before crashing
    pubsub_max_retry_time: float = Field(default=300.0)  # Max total retry time (5 minutes) before crashing
    pubsub_crash_on_failure: bool = Field(default=True)  # Crash the app when retries are exhausted

    # Health monitoring settings
    pubsub_health_monitoring_enabled: bool = Field(default=True)  # Enable health monitoring (can disable for tests)
    pubsub_health_monitor_initial_delay: float = Field(default=1.0)  # Initial delay before starting health monitoring


class RedisConnectionManager:
    """Manages Redis connection lifecycle and configuration."""

    def __init__(self, redis_client: Union[redis.StrictRedis, RedisBackendConfig, dict]) -> None:
        """
        Initialize the connection manager.

        Args:
            redis_client: A Redis client instance, configuration, or dict.
        """
        self.client: Union[redis.StrictRedis, redis.RedisCluster]
        self.config: Optional[RedisBackendConfig] = None

        if isinstance(redis_client, dict):
            # Check if dict contains a direct redis client
            if "redis_client" in redis_client:
                # Extract the redis client from the dict
                actual_client = redis_client["redis_client"]
                if isinstance(actual_client, (redis.StrictRedis, redis.RedisCluster)):
                    self.client = actual_client
                    self.config = None  # No config when passing client directly
                    return
                else:
                    raise ValueError("redis_client in dict must be a Redis client instance")
            else:
                # Try to convert dict to RedisBackendConfig
                redis_client = RedisBackendConfig(**redis_client)

        if isinstance(redis_client, RedisBackendConfig):
            self.config = redis_client
            self.client = self._create_client(redis_client)
        elif isinstance(redis_client, (redis.StrictRedis, redis.RedisCluster)):
            self.client = redis_client
        else:
            raise ValueError("Invalid Redis client")

    def _create_client(self, config: RedisBackendConfig) -> Union[redis.StrictRedis, redis.RedisCluster]:
        """Create a Redis client from configuration."""
        if config.is_cluster:
            return redis.RedisCluster(
                startup_nodes=[ClusterNode(config.host, config.port)],
                username=config.username,
                password=config.password,
                ssl=config.ssl,
                ssl_certfile=config.ssl_certfile,
                ssl_keyfile=config.ssl_keyfile,
                ssl_ca_certs=config.ssl_ca_certs,
                # Connection keepalive settings
                socket_keepalive=config.socket_keepalive,
                socket_keepalive_options=config.socket_keepalive_options,
                health_check_interval=config.health_check_interval,
                socket_connect_timeout=config.socket_connect_timeout,
                socket_timeout=config.socket_timeout,
                # Decode responses to strings for easier handling
                decode_responses=True,
            )  # type: ignore
        else:
            return redis.StrictRedis(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                ssl=config.ssl,
                ssl_certfile=config.ssl_certfile,
                ssl_keyfile=config.ssl_keyfile,
                ssl_ca_certs=config.ssl_ca_certs,
                # Connection keepalive settings
                socket_keepalive=config.socket_keepalive,
                socket_keepalive_options=config.socket_keepalive_options,
                health_check_interval=config.health_check_interval,
                socket_connect_timeout=config.socket_connect_timeout,
                socket_timeout=config.socket_timeout,
                # Decode responses to strings for easier handling
                decode_responses=True,
            )

    def get_client(self) -> Union[redis.StrictRedis, redis.RedisCluster]:
        """Get the Redis client instance."""
        return self.client

    def get_config(self) -> Optional[RedisBackendConfig]:
        """Get the configuration if available."""
        return self.config

    def close(self) -> None:
        """Close the Redis connection."""
        try:
            self.client.close()
        except Exception as e:
            logging.warning(f"Error closing Redis connection: {e}")
