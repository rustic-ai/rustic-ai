"""Unit tests for AgentPlacementService."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import fakeredis
from kubernetes.client import V1Endpoints, V1EndpointSubset, V1EndpointAddress, V1ObjectReference

from rustic_ai.core.guild.agent import AgentSpec
from rustic_ai.k8s.placement.placement_service import AgentPlacementService


@pytest.fixture
def redis_client():
    """Provide a fake Redis client for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def agent_spec():
    """Provide a simple agent spec for testing."""
    return AgentSpec(
        id="test-agent-1",
        name="TestAgent",
        class_name="rustic_ai.core.agent.Agent",
        description="Test agent",
        organization_id="test-org",
        guild_id="test-guild",
    )


@pytest.fixture
def mock_k8s_endpoints():
    """Create mock K8s endpoints with 3 pods."""

    def _create_address(pod_name: str):
        """Helper to create endpoint address."""
        address = V1EndpointAddress(
            ip=f"10.0.0.{pod_name.split('-')[-1]}",  # Simple IP from pod name
            target_ref=V1ObjectReference(kind="Pod", name=pod_name, namespace="default"),
        )
        return address

    # Create 3 pod addresses
    addresses = [
        _create_address("agent-host-0"),
        _create_address("agent-host-1"),
        _create_address("agent-host-2"),
    ]

    # Create endpoint subset
    subset = V1EndpointSubset(addresses=addresses, not_ready_addresses=None, ports=None)

    # Create endpoints object
    endpoints = V1Endpoints(subsets=[subset])

    return endpoints


class TestAgentPlacementServiceInit:
    """Test initialization of AgentPlacementService."""

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_init_with_incluster_config(self, mock_config, redis_client):
        """Test initialization with in-cluster K8s config."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(
            redis_client=redis_client, k8s_namespace="test-ns", service_name="test-service"
        )

        assert service.k8s_namespace == "test-ns"
        assert service.service_name == "test-service"
        assert service.grpc_port == 50051
        mock_config.load_incluster_config.assert_called_once()

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_init_with_kubeconfig_fallback(self, mock_config, redis_client):
        """Test initialization falls back to kubeconfig."""
        # Make in-cluster config fail
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        mock_config.load_incluster_config.assert_called_once()
        mock_config.load_kube_config.assert_called_once()

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_init_with_custom_grpc_port(self, mock_config, redis_client):
        """Test initialization with custom gRPC port."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client, grpc_port=8080)

        assert service.grpc_port == 8080


class TestHostDiscovery:
    """Test K8s host discovery functionality."""

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_list_available_hosts(self, mock_config, redis_client, mock_k8s_endpoints):
        """Test listing available hosts from K8s endpoints."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock the K8s API response
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=mock_k8s_endpoints)

        hosts = service._list_available_hosts()

        assert len(hosts) == 3
        assert "agent-host-0:50051" in hosts
        assert "agent-host-1:50051" in hosts
        assert "agent-host-2:50051" in hosts

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_list_available_hosts_empty(self, mock_config, redis_client):
        """Test listing hosts when no pods are available."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock empty endpoints
        empty_endpoints = V1Endpoints(subsets=[])
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=empty_endpoints)

        hosts = service._list_available_hosts()

        assert len(hosts) == 0

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_list_available_hosts_no_subsets(self, mock_config, redis_client):
        """Test listing hosts when endpoints have no subsets."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock endpoints with None subsets
        endpoints = V1Endpoints(subsets=None)
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=endpoints)

        hosts = service._list_available_hosts()

        assert len(hosts) == 0

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_list_available_hosts_api_error(self, mock_config, redis_client):
        """Test handling of K8s API errors."""
        from kubernetes.client.rest import ApiException

        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock API exception
        service.k8s_api.read_namespaced_endpoints = Mock(
            side_effect=ApiException(status=404, reason="Not Found")
        )

        with pytest.raises(RuntimeError, match="Failed to discover agent host pods"):
            service._list_available_hosts()


class TestRoundRobinPlacement:
    """Test round-robin placement logic."""

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_select_host_round_robin(self, mock_config, redis_client, agent_spec, mock_k8s_endpoints):
        """Test round-robin host selection."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=mock_k8s_endpoints)

        # Select hosts multiple times and verify round-robin
        selections = []
        for i in range(6):  # 2 full rounds
            host = service.select_host(agent_spec)
            selections.append(host)

        # Should cycle through all 3 hosts twice
        expected = [
            "agent-host-0:50051",
            "agent-host-1:50051",
            "agent-host-2:50051",
            "agent-host-0:50051",
            "agent-host-1:50051",
            "agent-host-2:50051",
        ]

        assert selections == expected

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_select_host_single_pod(self, mock_config, redis_client, agent_spec):
        """Test host selection with only one pod."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock single pod
        address = V1EndpointAddress(
            ip="10.0.0.1", target_ref=V1ObjectReference(kind="Pod", name="agent-host-0", namespace="default")
        )
        subset = V1EndpointSubset(addresses=[address])
        endpoints = V1Endpoints(subsets=[subset])

        service.k8s_api.read_namespaced_endpoints = Mock(return_value=endpoints)

        # Select multiple times, should always get the same host
        for _ in range(3):
            host = service.select_host(agent_spec)
            assert host == "agent-host-0:50051"

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_select_host_no_pods_available(self, mock_config, redis_client, agent_spec):
        """Test error when no pods are available."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)

        # Mock empty endpoints
        endpoints = V1Endpoints(subsets=[])
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=endpoints)

        with pytest.raises(RuntimeError, match="No agent host pods available"):
            service.select_host(agent_spec)


class TestPlacementCounter:
    """Test placement counter management."""

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_counter_increments(self, mock_config, redis_client, agent_spec, mock_k8s_endpoints):
        """Test that counter increments with each selection."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=mock_k8s_endpoints)

        # Check initial counter
        assert redis_client.get("placement:counter") is None

        # Select host
        service.select_host(agent_spec)
        assert int(redis_client.get("placement:counter")) == 1

        # Select again
        service.select_host(agent_spec)
        assert int(redis_client.get("placement:counter")) == 2

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_reset_counter(self, mock_config, redis_client, agent_spec, mock_k8s_endpoints):
        """Test resetting the placement counter."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=mock_k8s_endpoints)

        # Select a few times
        for _ in range(3):
            service.select_host(agent_spec)

        assert int(redis_client.get("placement:counter")) == 3

        # Reset
        service.reset_counter()

        assert redis_client.get("placement:counter") is None

        # Next selection should start from 0 again
        service.select_host(agent_spec)
        assert int(redis_client.get("placement:counter")) == 1


class TestHostCount:
    """Test host count queries."""

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_get_host_count(self, mock_config, redis_client, mock_k8s_endpoints):
        """Test getting the number of available hosts."""
        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)
        service.k8s_api.read_namespaced_endpoints = Mock(return_value=mock_k8s_endpoints)

        count = service.get_host_count()
        assert count == 3

    @patch("rustic_ai.k8s.placement.placement_service.config")
    def test_get_host_count_error_handling(self, mock_config, redis_client):
        """Test get_host_count handles errors gracefully."""
        from kubernetes.client.rest import ApiException

        mock_config.load_incluster_config.return_value = None
        mock_config.ConfigException = Exception

        service = AgentPlacementService(redis_client=redis_client)
        service.k8s_api.read_namespaced_endpoints = Mock(side_effect=ApiException(status=500))

        # Should return 0 on error, not raise
        count = service.get_host_count()
        assert count == 0
