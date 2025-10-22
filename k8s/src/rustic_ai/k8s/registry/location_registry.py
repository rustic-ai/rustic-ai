"""Redis-based agent location registry.

This registry stores only runtime data:
- Agent location (hostname:port)
- Host agent sets (for load balancing)

Configuration data (guild specs, agent specs) is managed
separately in the metastore.
"""

from typing import Optional, Dict, List
import redis


class AgentLocationRegistry:
    """
    Redis-based registry for agent runtime location tracking.

    This registry is responsible for:
    1. Tracking which agent host pod is running each agent
    2. Managing TTL-based liveness (60s expiration)
    3. Providing agent location lookup for routing
    4. Supporting placement decisions via host load queries
    """

    TTL_SECONDS = 60

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize the location registry.

        Args:
            redis_client: Redis client instance (must have decode_responses=True for string handling)
        """
        self.redis = redis_client

    def register(self, agent_id: str, host_address: str) -> None:
        """
        Register an agent's location with TTL.

        Args:
            agent_id: The agent ID
            host_address: The host address in format "hostname:port"

        Example:
            >>> registry.register("agent-123", "agent-host-2:50051")
        """
        # Set agent location with TTL
        key = f"agent_location:{agent_id}"
        self.redis.setex(key, self.TTL_SECONDS, host_address)

        # Add to host's agent set
        hostname = host_address.split(":")[0]
        host_key = f"host_agents:{hostname}"
        self.redis.sadd(host_key, agent_id)

    def heartbeat(self, agent_id: str) -> bool:
        """
        Refresh the TTL for an agent (heartbeat).

        This should be called periodically (e.g., every 20s) to keep
        the agent's location entry alive.

        Args:
            agent_id: The agent ID

        Returns:
            True if TTL was refreshed, False if key doesn't exist

        Example:
            >>> if registry.heartbeat("agent-123"):
            ...     print("Heartbeat successful")
        """
        key = f"agent_location:{agent_id}"
        return self.redis.expire(key, self.TTL_SECONDS) == 1

    def get_location(self, agent_id: str) -> Optional[str]:
        """
        Get the location of an agent.

        Args:
            agent_id: The agent ID

        Returns:
            Host address (hostname:port) or None if not found

        Example:
            >>> location = registry.get_location("agent-123")
            >>> if location:
            ...     print(f"Agent at {location}")
        """
        key = f"agent_location:{agent_id}"
        location = self.redis.get(key)
        return location

    def deregister(self, agent_id: str) -> None:
        """
        Deregister an agent.

        This removes the agent from both the location map and
        the host's agent set.

        Args:
            agent_id: The agent ID

        Example:
            >>> registry.deregister("agent-123")
        """
        # Get location to extract hostname
        key = f"agent_location:{agent_id}"
        location = self.redis.get(key)

        # Delete agent location
        self.redis.delete(key)

        # Remove from host's agent set
        if location:
            hostname = location.split(":")[0]
            host_key = f"host_agents:{hostname}"
            self.redis.srem(host_key, agent_id)

    def get_host_load(self) -> Dict[str, int]:
        """
        Get the number of agents on each host (for placement).

        Returns:
            Dictionary mapping hostname to agent count

        Example:
            >>> load = registry.get_host_load()
            >>> print(load)
            {'agent-host-1': 5, 'agent-host-2': 3}
        """
        load = {}

        # Scan for all host_agents:* keys
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="host_agents:*", count=100)

            for key in keys:
                # Extract hostname from key
                hostname = key.split(":", 1)[1]
                # Get cardinality of the set
                count = self.redis.scard(key)
                load[hostname] = count

            if cursor == 0:
                break

        return load

    def get_host_agents(self, hostname: str) -> List[str]:
        """
        Get all agent IDs on a specific host.

        Args:
            hostname: The hostname (without port)

        Returns:
            List of agent IDs

        Example:
            >>> agents = registry.get_host_agents("agent-host-2")
            >>> print(f"Found {len(agents)} agents")
        """
        host_key = f"host_agents:{hostname}"
        members = self.redis.smembers(host_key)
        return list(members)

    def cleanup_dead_agents(self) -> List[str]:
        """
        Clean up agents whose location entries have expired.

        This scans all host_agents sets and removes agent IDs
        that no longer have location entries (TTL expired).

        Returns:
            List of agent IDs that were cleaned up

        Example:
            >>> cleaned = registry.cleanup_dead_agents()
            >>> print(f"Cleaned up {len(cleaned)} dead agents")
        """
        cleaned = []

        # Scan for all host_agents:* keys
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="host_agents:*", count=100)

            for host_key in keys:
                # Get all agent IDs in this host's set
                agent_ids = self.redis.smembers(host_key)

                for agent_id in agent_ids:
                    # Check if location still exists
                    location_key = f"agent_location:{agent_id}"
                    if not self.redis.exists(location_key):
                        # Remove from host set
                        self.redis.srem(host_key, agent_id)
                        cleaned.append(agent_id)

            if cursor == 0:
                break

        return cleaned
