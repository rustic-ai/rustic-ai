"""K8s-native execution engine for distributed agent orchestration.

This engine distributes agent processes across Kubernetes pods using gRPC.
It implements the ExecutionEngine interface for seamless integration with
the Rustic AI framework.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type

import grpc
import redis

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig
from rustic_ai.k8s.placement.placement_service import AgentPlacementService
from rustic_ai.k8s.registry.location_registry import AgentLocationRegistry

# Import generated gRPC stubs
try:
    from rustic_ai.k8s.proto import agent_host_pb2, agent_host_pb2_grpc
except ImportError:
    # Stubs not generated yet
    agent_host_pb2 = None
    agent_host_pb2_grpc = None

logger = logging.getLogger(__name__)


class K8sExecutionEngine(ExecutionEngine):
    """
    Kubernetes-native execution engine for distributed agent orchestration.
    
    This engine:
    - Distributes agents across K8s pods using round-robin placement
    - Communicates with agent host pods via gRPC
    - Tracks agent locations in Redis
    - Manages gRPC channel pooling for efficient communication
    - Implements full ExecutionEngine interface
    
    Architecture:
    - Agent host pods run multiple agent processes (like Ray workers)
    - gRPC for remote procedure calls (CreateAgent, StopAgent, etc.)
    - Redis for location tracking and placement coordination
    - K8s Endpoints API for service discovery
    
    Example:
        redis_client = redis.Redis.from_url("redis://localhost:6379")
        engine = K8sExecutionEngine(
            guild_id="guild-123",
            organization_id="org-456",
            redis_client=redis_client,
            k8s_namespace="default",
            service_name="agent-host",
        )
        
        engine.run_agent(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=0,
        )
    """

    def __init__(
        self,
        guild_id: str,
        organization_id: str,
        redis_client: redis.Redis,
        k8s_namespace: str = "default",
        service_name: str = "agent-host",
        grpc_port: int = 50051,
    ):
        """
        Initialize the K8s execution engine.
        
        Args:
            guild_id: The ID of the guild this engine manages
            organization_id: The organization ID
            redis_client: Redis client for location registry and placement
            k8s_namespace: Kubernetes namespace for agent host pods
            service_name: Name of the agent host K8s service
            grpc_port: gRPC port for agent host pods (default: 50051)
        """
        super().__init__(guild_id, organization_id)
        
        self.redis_client = redis_client
        self.k8s_namespace = k8s_namespace
        self.service_name = service_name
        self.grpc_port = grpc_port
        
        # Initialize placement service
        self.placement_service = AgentPlacementService(
            redis_client=redis_client,
            k8s_namespace=k8s_namespace,
            service_name=service_name,
            grpc_port=grpc_port,
        )
        
        # Initialize location registry
        self.location_registry = AgentLocationRegistry(redis_client)
        
        # gRPC channel pool (hostname:port -> channel)
        self.grpc_channels: Dict[str, grpc.Channel] = {}
        
        logger.info(
            f"K8sExecutionEngine initialized: "
            f"guild_id={guild_id}, namespace={k8s_namespace}, "
            f"service={service_name}, grpc_port={grpc_port}"
        )

    def _get_grpc_channel(self, host_address: str) -> grpc.Channel:
        """
        Get or create a gRPC channel for the given host.
        
        This implements connection pooling for efficiency.
        
        Args:
            host_address: Host address in format "hostname:port"
            
        Returns:
            gRPC channel for the host
        """
        if host_address not in self.grpc_channels:
            # Create new channel
            channel = grpc.insecure_channel(host_address)
            self.grpc_channels[host_address] = channel
            logger.debug(f"Created new gRPC channel to {host_address}")
        
        return self.grpc_channels[host_address]

    def _get_stub(self, host_address: str) -> Any:
        """
        Get a gRPC stub for the given host.
        
        Args:
            host_address: Host address in format "hostname:port"
            
        Returns:
            AgentHostService stub
        """
        channel = self._get_grpc_channel(host_address)
        return agent_host_pb2_grpc.AgentHostServiceStub(channel)

    def run_agent(
        self,
        guild_spec: GuildSpec,
        agent_spec: AgentSpec,
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
        default_topic: str = "default_topic",
    ) -> Optional[Agent]:
        """
        Run an agent on a K8s agent host pod.
        
        This method:
        1. Selects a host using AgentPlacementService (round-robin)
        2. Serializes specs to JSON
        3. Calls CreateAgent RPC on the selected host
        4. Location is automatically registered by the agent host
        
        Args:
            guild_spec: The guild specification
            agent_spec: The agent specification
            messaging_config: Configuration for messaging
            machine_id: Unique machine identifier
            client_type: Type of client to use for the agent
            client_properties: Properties to initialize the client with
            default_topic: Default topic for the agent (unused)
            
        Returns:
            None (agent runs remotely, not locally)
            
        Raises:
            RuntimeError: If agent creation fails
        """
        try:
            agent_id = agent_spec.id
            
            # Select a host for placement
            logger.info(f"Selecting host for agent {agent_id}")
            host_address = self.placement_service.select_host(agent_spec)
            
            logger.info(f"Selected host {host_address} for agent {agent_id}")
            
            # Serialize specs to JSON
            agent_spec_json = agent_spec.model_dump_json()
            guild_spec_json = guild_spec.model_dump_json()
            messaging_config_json = messaging_config.model_dump_json()
            client_properties_json = json.dumps(client_properties)
            
            # Get gRPC stub
            stub = self._get_stub(host_address)
            
            # Create CreateAgentRequest
            request = agent_host_pb2.CreateAgentRequest(
                agent_spec=agent_spec_json.encode('utf-8'),
                guild_spec=guild_spec_json.encode('utf-8'),
                messaging_config=messaging_config_json.encode('utf-8'),
                machine_id=machine_id,
                client_type=client_type.__name__,
                client_properties=client_properties_json.encode('utf-8'),
            )
            
            # Call CreateAgent RPC
            logger.info(f"Creating agent {agent_id} on {host_address}")
            response = stub.CreateAgent(request, timeout=60)
            
            if not response.success:
                raise RuntimeError(
                    f"Failed to create agent {agent_id} on {host_address}: "
                    f"{response.error}"
                )
            
            logger.info(
                f"Successfully created agent {agent_id} on {host_address} "
                f"(pid={response.pid})"
            )
            
            return None  # Agent runs remotely
            
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error creating agent {agent_spec.id}: "
                f"code={e.code()}, details={e.details()}",
                exc_info=True,
            )
            raise RuntimeError(
                f"gRPC error creating agent {agent_spec.id}: {e.details()}"
            ) from e
        except Exception as e:
            logger.error(f"Failed to run agent {agent_spec.id}: {e}", exc_info=True)
            raise

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stop an agent running on a K8s agent host pod.
        
        This method:
        1. Looks up the agent's location in Redis
        2. Calls StopAgent RPC on the host
        3. Location is automatically deregistered by the agent host
        
        Args:
            guild_id: The ID of the guild containing the agent
            agent_id: The ID of the agent to stop
            
        Raises:
            RuntimeError: If agent location not found or stop fails
        """
        try:
            # Look up agent location
            host_address = self.location_registry.get_location(agent_id)
            
            if not host_address:
                raise RuntimeError(
                    f"Agent {agent_id} not found in location registry"
                )
            
            logger.info(f"Stopping agent {agent_id} on {host_address}")
            
            # Get gRPC stub
            stub = self._get_stub(host_address)
            
            # Create StopAgentRequest
            request = agent_host_pb2.StopAgentRequest(
                agent_id=agent_id,
                timeout=10,  # 10s graceful shutdown timeout
            )
            
            # Call StopAgent RPC
            response = stub.StopAgent(request, timeout=30)
            
            if not response.success:
                logger.warning(
                    f"Failed to stop agent {agent_id} on {host_address}: "
                    f"{response.error}"
                )
            else:
                logger.info(f"Successfully stopped agent {agent_id}")
                
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error stopping agent {agent_id}: "
                f"code={e.code()}, details={e.details()}",
                exc_info=True,
            )
            raise RuntimeError(
                f"gRPC error stopping agent {agent_id}: {e.details()}"
            ) from e
        except Exception as e:
            logger.error(f"Failed to stop agent {agent_id}: {e}", exc_info=True)
            raise

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Get all agents running in a guild.
        
        This method queries each agent host pod to list agents in the guild.
        
        Args:
            guild_id: The ID of the guild
            
        Returns:
            Dictionary mapping agent_id to AgentSpec
        """
        try:
            agents: Dict[str, AgentSpec] = {}
            
            # Get all available hosts
            hosts = self.placement_service._list_available_hosts()
            
            # Query each host for agents in this guild
            for host_address in hosts:
                try:
                    stub = self._get_stub(host_address)
                    
                    # Create ListAgentsRequest
                    request = agent_host_pb2.ListAgentsRequest(guild_id=guild_id)
                    
                    # Call ListAgents RPC
                    response = stub.ListAgents(request, timeout=10)
                    
                    # Add agents to result
                    for agent_info in response.agents:
                        # Reconstruct AgentSpec from agent_info
                        # Note: We only have limited info from AgentInfo
                        # In production, you might want to store full specs in Redis
                        agents[agent_info.agent_id] = AgentSpec(
                            id=agent_info.agent_id,
                            name=agent_info.agent_name,
                            guild_id=agent_info.guild_id,
                            organization_id=self.organization_id,
                            class_name="",  # Not available from AgentInfo
                            description="",  # Not available from AgentInfo
                        )
                        
                except grpc.RpcError as e:
                    logger.warning(
                        f"Failed to list agents on {host_address}: "
                        f"code={e.code()}, details={e.details()}"
                    )
                    # Continue with other hosts
                    
            return agents
            
        except Exception as e:
            logger.error(f"Failed to get agents in guild {guild_id}: {e}", exc_info=True)
            return {}

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Find agents by name in a guild.
        
        Args:
            guild_id: The ID of the guild
            agent_name: The name of the agent
            
        Returns:
            List of AgentSpecs matching the name
        """
        agents = self.get_agents_in_guild(guild_id)
        return [spec for spec in agents.values() if spec.name == agent_name]

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Check if an agent is currently running.
        
        This uses the location registry to check liveness.
        
        Args:
            guild_id: The ID of the guild
            agent_id: The ID of the agent
            
        Returns:
            True if agent is running, False otherwise
        """
        location = self.location_registry.get_location(agent_id)
        return location is not None

    def shutdown(self) -> None:
        """
        Shutdown the execution engine.
        
        This closes all gRPC channels and cleans up resources.
        Note: This does NOT stop running agents on agent host pods.
        """
        logger.info("Shutting down K8sExecutionEngine")
        
        # Close all gRPC channels
        for host_address, channel in self.grpc_channels.items():
            try:
                logger.debug(f"Closing gRPC channel to {host_address}")
                channel.close()
            except Exception as e:
                logger.error(f"Error closing channel to {host_address}: {e}")
        
        self.grpc_channels.clear()
        
        logger.info("K8sExecutionEngine shutdown complete")
