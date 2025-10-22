"""Agent placement service for K8s pods.

This service decides which agent host pod should run a new agent.
Initial implementation uses round-robin, but can be extended for
resource-aware placement.
"""

import logging
from typing import List, Optional

import redis
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from rustic_ai.core.guild.agent import AgentSpec

logger = logging.getLogger(__name__)


class AgentPlacementService:
    """
    Decides which agent host pod to create agents on.

    Initial implementation: Round-robin placement
    Future: Resource-aware placement based on CPU/memory/agent count
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        k8s_namespace: str = "default",
        service_name: str = "agent-host",
        grpc_port: int = 50051,
    ):
        """
        Initialize the placement service.

        Args:
            redis_client: Redis client for tracking placement counter
            k8s_namespace: Kubernetes namespace where agent hosts run
            service_name: Name of the K8s service for agent hosts
            grpc_port: gRPC port for agent host communication
        """
        self.redis = redis_client
        self.k8s_namespace = k8s_namespace
        self.service_name = service_name
        self.grpc_port = grpc_port

        # Initialize K8s client
        try:
            # Try in-cluster config first (when running in K8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            # Fall back to kubeconfig (for local development)
            try:
                config.load_kube_config()
                logger.info("Loaded Kubernetes configuration from kubeconfig")
            except config.ConfigException as e:
                logger.warning(f"Could not load Kubernetes configuration: {e}")
                logger.warning("K8s pod discovery will not work")

        self.k8s_api = client.CoreV1Api()

    def select_host(self, agent_spec: AgentSpec) -> str:
        """
        Select optimal host for agent placement.

        Uses round-robin strategy to distribute agents evenly across
        available agent host pods.

        Args:
            agent_spec: The agent specification (for future resource-aware placement)

        Returns:
            Host address in format "hostname:port"

        Raises:
            RuntimeError: If no agent host pods are available
        """
        hosts = self._list_available_hosts()

        if not hosts:
            raise RuntimeError("No agent host pods available")

        # Round-robin placement using Redis counter
        counter = self.redis.incr("placement:counter")
        selected_index = (counter - 1) % len(hosts)  # -1 because incr returns new value
        selected = hosts[selected_index]

        logger.debug(
            f"Selected host {selected} for agent {agent_spec.id} "
            f"(counter={counter}, index={selected_index}, total_hosts={len(hosts)})"
        )

        return selected

    def _list_available_hosts(self) -> List[str]:
        """
        Query K8s for available agent host pods.

        Returns:
            List of host addresses in format "hostname:port"

        Raises:
            RuntimeError: If K8s API query fails
        """
        try:
            # Get endpoints for the agent-host service
            endpoints = self.k8s_api.read_namespaced_endpoints(
                name=self.service_name, namespace=self.k8s_namespace
            )

            hosts = []

            # Extract pod hostnames from endpoints
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        for address in subset.addresses:
                            # Use pod name as hostname
                            if address.target_ref and address.target_ref.name:
                                hostname = address.target_ref.name
                                host_address = f"{hostname}:{self.grpc_port}"
                                hosts.append(host_address)

            logger.debug(f"Discovered {len(hosts)} agent host pods: {hosts}")
            return hosts

        except ApiException as e:
            logger.error(f"Failed to query K8s endpoints: {e}")
            raise RuntimeError(f"Failed to discover agent host pods: {e}")

    def get_host_count(self) -> int:
        """
        Get the number of available agent host pods.

        Returns:
            Number of available hosts
        """
        try:
            hosts = self._list_available_hosts()
            return len(hosts)
        except Exception as e:
            logger.error(f"Failed to get host count: {e}")
            return 0

    def reset_counter(self) -> None:
        """
        Reset the placement counter.

        Useful for testing or manual intervention.
        """
        self.redis.delete("placement:counter")
        logger.info("Reset placement counter")
