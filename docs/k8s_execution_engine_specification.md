# Kubernetes Execution Engine Specification

## Executive Summary

This document specifies the design and implementation of a Kubernetes-native execution engine for Rustic AI as an alternative to the Ray-based execution engine. The K8s execution engine will provide similar multi-agent orchestration capabilities while eliminating the dependency on Ray and reducing operational complexity.

**Key Design Principles:**
- **Agent Host Pods**: Long-lived K8s pods that run multiple agent processes (similar to Ray workers)
- **Process Isolation**: Each agent runs in its own process for fault isolation and GIL escape
- **Minimal Runtime State**: Redis-based location registry tracking only runtime data (agent location, liveness)
- **gRPC Communication**: High-performance protocol between execution engine and agent host pods
- **Code Reuse**: Extract `AgentProcessManager` utility used by both local and K8s engines

**Architecture at a Glance:**
```
┌─────────────────────┐
│ Guild Manager       │
│ (ExecutionEngine)   │
└──────────┬──────────┘
           │ gRPC
           ▼
┌─────────────────────┐      ┌─────────────────────┐
│ Agent Host Pod 1    │      │ Agent Host Pod 2    │
│ ┌─────┐ ┌─────┐    │      │ ┌─────┐ ┌─────┐    │
│ │Agent│ │Agent│    │      │ │Agent│ │Agent│    │
│ │ 1   │ │ 2   │... │      │ │ N   │ │ N+1│... │
│ └─────┘ └─────┘    │      │ └─────┘ └─────┘    │
└─────────────────────┘      └─────────────────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
                ┌─────────────┐
                │ Redis       │
                │ (Location   │
                │  Registry)  │
                └─────────────┘
```

**Total Estimated Lines of Code:** ~1160 (excluding tests)

---

## 1. Background and Motivation

### 1.1 Current State

Rustic AI currently supports multiple execution engines:
- **SyncExecutionEngine**: Single-threaded, sequential execution
- **MultiThreadedEngine**: Thread-based concurrency (GIL-limited)
- **MultiProcessExecutionEngine**: Process-based parallelism
- **RayExecutionEngine**: Distributed actors on Ray cluster

Ray is already optional in the framework and provides:
- Process isolation via actors
- Fractional GPU sharing (0.5 GPU per actor)
- Named actor discovery
- Auto-restart (max 3 times)

However, analysis shows Ray usage is minimal (11 of 680+ APIs, ~1.6% utilization) and adds operational complexity when running on Kubernetes.

### 1.2 Problem Statement

Running Ray on Kubernetes creates two layers of orchestration:
- **Kubernetes**: Pod scheduling, resource allocation, networking
- **Ray**: Actor placement, process management, distributed state

This adds complexity without significant benefit unless fractional GPU sharing is required.

### 1.3 Solution Overview

Implement a Kubernetes-native execution engine that:
1. Eliminates Ray dependency for non-GPU workloads
2. Uses Agent Host pods running multiple agent processes
3. Provides gRPC-based communication for performance
4. Tracks agent location/liveness in Redis
5. Reuses existing multiprocess patterns via `AgentProcessManager` utility

---

## 2. Requirements

### 2.1 Functional Requirements

**FR1: Agent Lifecycle Management**
- Create agent processes on agent host pods
- Stop agent processes gracefully (10s timeout, then force terminate)
- Track agent process status (running, stopped, crashed)
- Support graceful shutdown of all agents

**FR2: Agent Discovery and Routing**
- Locate which agent host pod runs a specific agent
- Route requests to the correct agent host pod
- Support guild-scoped and name-based agent queries

**FR3: Agent Placement**
- Distribute agents across available agent host pods
- Support basic load balancing (round-robin initially)
- Respect K8s pod capacity limits

**FR4: Liveness Tracking**
- Detect when agent processes crash or become unresponsive
- Automatic cleanup of stale agent location entries (60s TTL)
- Heartbeat mechanism (refresh every 20s)

**FR5: ExecutionEngine Interface Compliance**
- Implement all abstract methods from `ExecutionEngine` base class
- Maintain API compatibility with existing engines
- Support same initialization patterns as Ray engine

### 2.2 Non-Functional Requirements

**NFR1: Performance**
- Agent creation: < 2s (vs Ray's 50-200ms, acceptable for long-lived agents)
- Agent lookup: < 1ms (Redis GET)
- gRPC communication latency: < 2ms

**NFR2: Scalability**
- Support 100+ agents per agent host pod
- Support 1000+ agents across multiple pods
- Scale out via Kubernetes HPA

**NFR3: Fault Tolerance**
- Process isolation (crash doesn't affect other agents)
- Automatic cleanup of dead processes
- Graceful degradation on agent host pod failure

**NFR4: Observability**
- Prometheus metrics for agent count, process health
- Structured logging (JSON)
- Distributed tracing (OpenTelemetry compatible)

**NFR5: Security**
- No pickle deserialization (use JSON)
- gRPC TLS support
- Redis authentication

---

## 3. Architecture

### 3.1 Component Overview

```
┌────────────────────────────────────────────────────────────┐
│                     Guild Manager Process                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           K8sExecutionEngine                          │  │
│  │  ┌────────────────┐    ┌──────────────────────┐     │  │
│  │  │ Placement      │    │ Location Registry    │     │  │
│  │  │ Service        │    │ (Redis Client)       │     │  │
│  │  └────────────────┘    └──────────────────────┘     │  │
│  │                                                        │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │ gRPC Channel Pool (connections to hosts)       │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
                             │
                             │ gRPC (CreateAgent, StopAgent, etc.)
                             ▼
┌────────────────────────────────────────────────────────────┐
│                  Agent Host Pod (Deployment)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         AgentHostServicer (gRPC Server)              │  │
│  │  ┌────────────────┐    ┌──────────────────────┐     │  │
│  │  │ Process        │    │ Location Registry    │     │  │
│  │  │ Manager        │    │ (Redis Client)       │     │  │
│  │  └────────────────┘    └──────────────────────┘     │  │
│  │                                                        │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │ Heartbeat Worker (background thread)          │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐              │
│  │ Agent     │  │ Agent     │  │ Agent     │              │
│  │ Process 1 │  │ Process 2 │  │ Process N │  ...         │
│  └───────────┘  └───────────┘  └───────────┘              │
└────────────────────────────────────────────────────────────┘
                             │
                             │ Redis Protocol
                             ▼
┌────────────────────────────────────────────────────────────┐
│              Redis (StatefulSet)                            │
│  agent_location:{agent_id} → "hostname:port" (TTL: 60s)    │
│  host_agents:{hostname} → SET of agent_ids                 │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Component Descriptions

**K8sExecutionEngine** (`rustic_ai/k8s/execution/k8s_exec_engine.py`)
- Implements `ExecutionEngine` interface
- Creates agents via gRPC calls to agent host pods
- Manages gRPC channel pool for connections to hosts
- Delegates placement decisions to `AgentPlacementService`
- Uses `AgentLocationRegistry` for agent lookup

**AgentHostServicer** (`rustic_ai/k8s/agent_host/grpc_service.py`)
- gRPC server running on each agent host pod (port 50051)
- Uses `AgentProcessManager` for process lifecycle
- Registers agents in Redis location registry
- Runs heartbeat worker thread (every 20s)
- Exposes metrics endpoint (Prometheus format)

**AgentProcessManager** (`rustic_ai/core/execution/process_manager.py`)
- Reusable utility for managing agent processes
- Guild-agnostic (takes guild_id per method, not in constructor)
- JSON serialization (not pickle) for security
- Used by both `MultiProcessExecutionEngine` and `AgentHostServicer`

**AgentLocationRegistry** (`rustic_ai/k8s/registry/location_registry.py`)
- Redis-based runtime location tracking
- Minimal schema: agent location + host agent sets
- TTL-based liveness (60s, refreshed by heartbeat)

**AgentPlacementService** (`rustic_ai/k8s/placement/placement_service.py`)
- Decides which agent host pod to create agents on
- Round-robin initial implementation
- Can be extended with resource-aware placement

### 3.3 Data Flow

**Agent Creation Flow:**
```
1. GuildManager calls k8s_exec_engine.run_agent()
2. K8sExecutionEngine asks PlacementService: which host?
3. PlacementService returns host address (e.g., "agent-host-2:50051")
4. K8sExecutionEngine gets gRPC channel from pool
5. K8sExecutionEngine sends CreateAgent RPC
6. AgentHostServicer receives request
7. AgentHostServicer calls process_manager.spawn_agent_process()
8. Process spawned, AgentHostServicer registers in Redis:
   - agent_location:{agent_id} → "agent-host-2:50051"
   - host_agents:agent-host-2 → add agent_id to SET
9. AgentHostServicer returns CreateAgentResponse
10. K8sExecutionEngine returns (no agent instance available)
```

**Agent Lookup Flow:**
```
1. Code calls k8s_exec_engine.is_agent_running(guild_id, agent_id)
2. K8sExecutionEngine calls location_registry.get_location(agent_id)
3. Redis GET agent_location:{agent_id}
4. Returns "hostname:port" or None
5. K8sExecutionEngine returns bool
```

**Agent Stop Flow:**
```
1. Code calls k8s_exec_engine.stop_agent(guild_id, agent_id)
2. K8sExecutionEngine looks up agent location in Redis
3. K8sExecutionEngine sends StopAgent RPC to agent host
4. AgentHostServicer calls process_manager.stop_agent_process()
5. Process stopped (SIGTERM, wait 10s, SIGKILL if needed)
6. AgentHostServicer deregisters from Redis:
   - DEL agent_location:{agent_id}
   - SREM host_agents:{hostname} agent_id
7. AgentHostServicer returns StopAgentResponse
```

**Heartbeat Flow:**
```
1. Heartbeat worker thread wakes every 20s
2. For each local agent process:
   - Check if process is alive
   - If alive: location_registry.heartbeat(agent_id) → EXPIRE reset to 60s
   - If dead: location_registry.deregister(agent_id)
```

---

## 4. Data Models

### 4.1 Redis Schema

**Agent Location Registry:**

```
Key: agent_location:{agent_id}
Type: STRING
Value: "{hostname}:{port}"
TTL: 60 seconds
Example: agent_location:abc123 → "agent-host-2:50051"
```

**Host Agent Set:**

```
Key: host_agents:{hostname}
Type: SET
Members: agent_id1, agent_id2, ...
TTL: None (updated atomically with agent registration)
Example: host_agents:agent-host-2 → {"abc123", "def456", "ghi789"}
```

**Placement Counter:**

```
Key: placement:counter
Type: INTEGER
Value: Incrementing counter for round-robin placement
TTL: None
```

### 4.2 gRPC Messages

See Section 5 for complete protobuf definitions.

### 4.3 Configuration Models

**MessagingConfig** (existing):
```python
@dataclass
class MessagingConfig:
    backend_type: str  # "embedded", "redis", etc.
    connection_params: Dict[str, Any]
```

**AgentSpec** (existing):
```python
@dataclass
class AgentSpec:
    id: str
    name: str
    agent_class_name: str  # Fully qualified class name
    dependencies: Dict[str, DependencySpec]
    organization_id: str
    guild_id: str
```

**GuildSpec** (existing):
```python
@dataclass
class GuildSpec:
    id: str
    name: str
    organization_id: str
    agents: List[AgentSpec]
```

---

## 5. API Specifications

### 5.1 gRPC Protocol Definition

**File:** `rustic_ai/k8s/proto/agent_host.proto`

```protobuf
syntax = "proto3";

package rustic_ai.k8s.agent_host;

// Service for managing agents on an agent host pod
service AgentHostService {
  // Create and start a new agent process
  rpc CreateAgent(CreateAgentRequest) returns (CreateAgentResponse);

  // Stop a running agent process
  rpc StopAgent(StopAgentRequest) returns (StopAgentResponse);

  // Get information about a specific agent
  rpc GetAgentInfo(GetAgentInfoRequest) returns (AgentInfo);

  // List all agents running on this host
  rpc ListAgents(ListAgentsRequest) returns (ListAgentsResponse);

  // Health check
  rpc Health(HealthRequest) returns (HealthResponse);
}

message CreateAgentRequest {
  // JSON-serialized AgentSpec
  bytes agent_spec = 1;

  // JSON-serialized GuildSpec
  bytes guild_spec = 2;

  // JSON-serialized MessagingConfig
  bytes messaging_config = 3;

  // Machine ID for ID generation
  int32 machine_id = 4;

  // Client type name (e.g., "MessageTrackingClient")
  string client_type = 5;

  // JSON-serialized client properties
  bytes client_properties = 6;
}

message CreateAgentResponse {
  // ID of the created agent
  string agent_id = 1;

  // Process ID (for debugging)
  int32 pid = 2;

  // Success status
  bool success = 3;

  // Error message if not successful
  string error = 4;
}

message StopAgentRequest {
  // ID of the agent to stop
  string agent_id = 1;

  // Timeout in seconds (default: 10)
  int32 timeout = 2;
}

message StopAgentResponse {
  // Success status
  bool success = 1;

  // Error message if not successful
  string error = 2;
}

message GetAgentInfoRequest {
  // ID of the agent
  string agent_id = 1;
}

message AgentInfo {
  // Agent ID
  string agent_id = 1;

  // Guild ID
  string guild_id = 2;

  // Agent name
  string agent_name = 3;

  // Process ID
  int32 pid = 4;

  // Is process alive
  bool is_alive = 5;

  // Created timestamp (Unix epoch)
  int64 created_at = 6;
}

message ListAgentsRequest {
  // Optional guild_id filter
  string guild_id = 1;
}

message ListAgentsResponse {
  // List of agent information
  repeated AgentInfo agents = 1;
}

message HealthRequest {
}

message HealthResponse {
  // Overall health status
  bool healthy = 1;

  // Number of running agents
  int32 agent_count = 2;

  // Hostname
  string hostname = 3;
}
```

### 5.2 AgentProcessManager Interface

**File:** `rustic_ai/core/execution/process_manager.py`

```python
from typing import Dict, Optional, List
from dataclasses import dataclass
import multiprocessing

@dataclass
class AgentProcessInfo:
    """Information about a running agent process."""
    agent_id: str
    guild_id: str
    pid: int
    is_alive: bool
    created_at: float

class AgentProcessManager:
    """
    Reusable utility for managing agent processes.

    This utility is guild-agnostic and uses JSON serialization
    for security. It can be used by both local execution engines
    and the K8s agent host.
    """

    def __init__(self, max_processes: int = 100):
        """
        Initialize the process manager.

        Args:
            max_processes: Maximum number of processes to allow
        """
        pass

    def spawn_agent_process(
        self,
        agent_spec: AgentSpec,
        guild_spec: GuildSpec,
        messaging_config: MessagingConfig,
        machine_id: int = 0,
        client_type_name: str = "MessageTrackingClient",
        client_properties: Dict[str, Any] = None
    ) -> str:
        """
        Spawn a new agent process.

        Args:
            agent_spec: The agent specification
            guild_spec: The guild specification
            messaging_config: Configuration for messaging
            machine_id: Unique machine identifier
            client_type_name: Name of the client class
            client_properties: Properties for client initialization

        Returns:
            agent_id: The ID of the spawned agent

        Raises:
            RuntimeError: If max processes reached or spawn fails
        """
        pass

    def stop_agent_process(
        self,
        agent_id: str,
        timeout: int = 10
    ) -> bool:
        """
        Stop an agent process gracefully.

        Args:
            agent_id: The ID of the agent to stop
            timeout: Seconds to wait before force termination

        Returns:
            True if stopped successfully, False otherwise
        """
        pass

    def is_process_alive(self, agent_id: str) -> bool:
        """
        Check if an agent process is alive.

        Args:
            agent_id: The ID of the agent

        Returns:
            True if process is alive, False otherwise
        """
        pass

    def get_process_info(self, agent_id: str) -> Optional[AgentProcessInfo]:
        """
        Get information about an agent process.

        Args:
            agent_id: The ID of the agent

        Returns:
            AgentProcessInfo if found, None otherwise
        """
        pass

    def list_processes(
        self,
        guild_id: Optional[str] = None
    ) -> Dict[str, AgentProcessInfo]:
        """
        List all managed processes.

        Args:
            guild_id: Optional filter by guild_id

        Returns:
            Dictionary mapping agent_id to AgentProcessInfo
        """
        pass

    def cleanup_dead_processes(self) -> List[str]:
        """
        Clean up any dead processes.

        Returns:
            List of agent_ids that were cleaned up
        """
        pass

    def shutdown(self) -> None:
        """
        Shutdown all managed processes.
        """
        pass
```

### 5.3 AgentLocationRegistry Interface

**File:** `rustic_ai/k8s/registry/location_registry.py`

```python
from typing import Optional, Dict
import redis

class AgentLocationRegistry:
    """
    Redis-based registry for agent runtime location tracking.

    This registry stores only runtime data:
    - Agent location (hostname:port)
    - Host agent sets (for load balancing)

    Configuration data (guild specs, agent specs) is managed
    separately in the metastore.
    """

    TTL_SECONDS = 60

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize the location registry.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client

    def register(self, agent_id: str, host_address: str) -> None:
        """
        Register an agent's location.

        Args:
            agent_id: The agent ID
            host_address: The host address (hostname:port)
        """
        # SET agent_location:{agent_id} "{host_address}" EX 60
        # SADD host_agents:{hostname} {agent_id}
        pass

    def heartbeat(self, agent_id: str) -> bool:
        """
        Refresh the TTL for an agent (heartbeat).

        Args:
            agent_id: The agent ID

        Returns:
            True if TTL was refreshed, False if key doesn't exist
        """
        # EXPIRE agent_location:{agent_id} 60
        pass

    def get_location(self, agent_id: str) -> Optional[str]:
        """
        Get the location of an agent.

        Args:
            agent_id: The agent ID

        Returns:
            Host address (hostname:port) or None if not found
        """
        # GET agent_location:{agent_id}
        pass

    def deregister(self, agent_id: str) -> None:
        """
        Deregister an agent.

        Args:
            agent_id: The agent ID
        """
        # Get location to extract hostname
        # DEL agent_location:{agent_id}
        # SREM host_agents:{hostname} {agent_id}
        pass

    def get_host_load(self) -> Dict[str, int]:
        """
        Get the number of agents on each host (for placement).

        Returns:
            Dictionary mapping hostname to agent count
        """
        # SCAN for host_agents:* keys
        # SCARD for each key
        pass

    def get_host_agents(self, hostname: str) -> List[str]:
        """
        Get all agent IDs on a specific host.

        Args:
            hostname: The hostname

        Returns:
            List of agent IDs
        """
        # SMEMBERS host_agents:{hostname}
        pass
```

### 5.4 K8sExecutionEngine Interface

**File:** `rustic_ai/k8s/execution/k8s_exec_engine.py`

```python
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine

class K8sExecutionEngine(ExecutionEngine):
    """
    Kubernetes-native execution engine.

    This engine creates agents on long-lived agent host pods
    via gRPC, eliminating the need for Ray.
    """

    def __init__(
        self,
        guild_id: str,
        organization_id: str,
        redis_url: str,
        agent_host_service_name: str = "agent-host"
    ):
        """
        Initialize the K8s execution engine.

        Args:
            guild_id: The ID of the guild
            organization_id: The organization ID
            redis_url: Redis connection URL for location registry
            agent_host_service_name: K8s service name for agent hosts
        """
        super().__init__(guild_id, organization_id)
        # Initialize location registry, placement service, gRPC channels
        pass

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
        Create an agent on an agent host pod via gRPC.

        Implementation:
        1. Select host using placement service
        2. Get/create gRPC channel to host
        3. Send CreateAgent RPC with serialized specs
        4. Return None (no direct agent instance access)
        """
        pass

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stop an agent via gRPC.

        Implementation:
        1. Look up agent location in registry
        2. Send StopAgent RPC to host
        3. Registry cleanup handled by host
        """
        pass

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Check if an agent is running.

        Implementation:
        1. Look up agent in location registry
        2. Return True if location exists (TTL-based liveness)
        """
        pass

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Get all agents in a guild.

        Implementation:
        1. Query all agent hosts via gRPC
        2. Aggregate results
        3. Filter by guild_id
        """
        pass

    def find_agents_by_name(
        self,
        guild_id: str,
        agent_name: str
    ) -> List[AgentSpec]:
        """
        Find agents by name in a guild.

        Implementation:
        1. Get all agents in guild
        2. Filter by agent_name
        """
        pass

    def shutdown(self) -> None:
        """
        Shutdown the execution engine.

        Implementation:
        1. Close all gRPC channels
        2. Optionally stop all agents (or leave running for detached mode)
        """
        pass
```

---

## 6. Deployment Architecture

### 6.1 Kubernetes Resources

**Redis StatefulSet:**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: rustic-redis
spec:
  serviceName: rustic-redis
  replicas: 1
  selector:
    matchLabels:
      app: rustic-redis
  template:
    metadata:
      labels:
        app: rustic-redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        volumeMounts:
        - name: data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: rustic-redis
spec:
  ports:
  - port: 6379
  clusterIP: None
  selector:
    app: rustic-redis
```

**Agent Host Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-host
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-host
  template:
    metadata:
      labels:
        app: agent-host
    spec:
      containers:
      - name: agent-host
        image: rustic-ai/agent-host:latest
        ports:
        - containerPort: 50051
          name: grpc
        - containerPort: 8080
          name: metrics
        env:
        - name: REDIS_URL
          value: "redis://rustic-redis:6379/0"
        - name: MAX_PROCESSES
          value: "100"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            cpu: 4000m
            memory: 8Gi
          limits:
            cpu: 4000m
            memory: 8Gi
        livenessProbe:
          grpc:
            port: 50051
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          grpc:
            port: 50051
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: agent-host
spec:
  type: ClusterIP
  ports:
  - port: 50051
    name: grpc
  - port: 8080
    name: metrics
  selector:
    app: agent-host
```

**Horizontal Pod Autoscaler:**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-host-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-host
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 6.2 Docker Configuration

**Dockerfile for Agent Host:**
```dockerfile
FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY core/requirements.txt k8s/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY core/src/rustic_ai/core ./rustic_ai/core
COPY k8s/src/rustic_ai/k8s ./rustic_ai/k8s

# Generate gRPC stubs
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    rustic_ai/k8s/proto/agent_host.proto

# Expose ports
EXPOSE 50051 8080

# Run the agent host service
CMD ["python", "-m", "rustic_ai.k8s.agent_host.server"]
```

### 6.3 Scaling Considerations

**Agent Capacity per Pod:**
- Resource per agent: ~100m CPU, 200Mi memory
- Pod resources: 4 CPU, 8Gi memory
- Max agents per pod: ~40 (with headroom)

**Cluster Scaling:**
- For 1000 agents: ~25 pods required
- HPA scales based on CPU/memory utilization
- Can add custom metric: `agent_count / max_processes`

**Performance Benchmarks:**
- Agent creation: 1-2s per agent
- Agent lookup: <1ms (Redis)
- gRPC call overhead: 0.5-2ms

---

## 7. Security Considerations

### 7.1 Serialization Security

**Problem:** Current `MultiProcessExecutionEngine` uses pickle, which is vulnerable to arbitrary code execution.

**Solution:** Use JSON serialization for all inter-process communication:
- AgentSpec, GuildSpec, MessagingConfig serialized as JSON
- Transmitted as bytes over gRPC
- Deserialized safely in target process

### 7.2 gRPC Security

**TLS Configuration:**
```python
# Server-side
server_credentials = grpc.ssl_server_credentials(
    ((private_key, certificate_chain),)
)
server.add_secure_port('[::]:50051', server_credentials)

# Client-side
channel_credentials = grpc.ssl_channel_credentials(root_certificates)
channel = grpc.secure_channel('agent-host:50051', channel_credentials)
```

### 7.3 Redis Security

**Authentication:**
```python
redis_client = redis.Redis(
    host='rustic-redis',
    port=6379,
    password=os.environ.get('REDIS_PASSWORD'),
    ssl=True,
    ssl_cert_reqs='required',
    ssl_ca_certs='/path/to/ca.crt'
)
```

**Network Policies:**
- Restrict Redis access to agent host pods only
- Use Kubernetes NetworkPolicies

---

## 8. Testing Strategy

### 8.1 Unit Tests

**AgentProcessManager Tests:**
```python
def test_spawn_agent_process():
    """Test spawning a single agent process."""
    manager = AgentProcessManager(max_processes=10)
    agent_id = manager.spawn_agent_process(agent_spec, guild_spec, ...)
    assert manager.is_process_alive(agent_id)

def test_stop_agent_process():
    """Test graceful process termination."""
    manager = AgentProcessManager()
    agent_id = manager.spawn_agent_process(...)
    success = manager.stop_agent_process(agent_id, timeout=5)
    assert success
    assert not manager.is_process_alive(agent_id)

def test_max_processes_limit():
    """Test that max_processes limit is enforced."""
    manager = AgentProcessManager(max_processes=2)
    manager.spawn_agent_process(...)  # OK
    manager.spawn_agent_process(...)  # OK
    with pytest.raises(RuntimeError):
        manager.spawn_agent_process(...)  # Fails
```

**AgentLocationRegistry Tests:**
```python
def test_register_and_lookup():
    """Test agent registration and lookup."""
    registry = AgentLocationRegistry(redis_client)
    registry.register("agent-1", "host-1:50051")
    location = registry.get_location("agent-1")
    assert location == "host-1:50051"

def test_ttl_expiration():
    """Test that TTL causes automatic expiration."""
    registry = AgentLocationRegistry(redis_client)
    registry.TTL_SECONDS = 1  # Override for testing
    registry.register("agent-1", "host-1:50051")
    time.sleep(2)
    location = registry.get_location("agent-1")
    assert location is None

def test_heartbeat_refresh():
    """Test that heartbeat refreshes TTL."""
    registry = AgentLocationRegistry(redis_client)
    registry.TTL_SECONDS = 2
    registry.register("agent-1", "host-1:50051")
    time.sleep(1)
    success = registry.heartbeat("agent-1")
    assert success
    time.sleep(1.5)  # Total 2.5s, but heartbeat at 1s
    location = registry.get_location("agent-1")
    assert location == "host-1:50051"  # Still alive
```

### 8.2 Integration Tests

**gRPC Service Tests:**
```python
def test_create_agent_via_grpc():
    """Test creating an agent via gRPC."""
    channel = grpc.insecure_channel('localhost:50051')
    stub = agent_host_pb2_grpc.AgentHostServiceStub(channel)

    request = agent_host_pb2.CreateAgentRequest(
        agent_spec=json.dumps(agent_spec_dict).encode(),
        guild_spec=json.dumps(guild_spec_dict).encode(),
        ...
    )

    response = stub.CreateAgent(request)
    assert response.success
    assert response.agent_id

def test_stop_agent_via_grpc():
    """Test stopping an agent via gRPC."""
    # Create agent first
    response1 = stub.CreateAgent(...)
    agent_id = response1.agent_id

    # Stop agent
    request = agent_host_pb2.StopAgentRequest(agent_id=agent_id)
    response2 = stub.StopAgent(request)
    assert response2.success
```

**K8sExecutionEngine Tests:**
```python
def test_run_agent_e2e():
    """End-to-end test of running an agent."""
    engine = K8sExecutionEngine(
        guild_id="test-guild",
        organization_id="test-org",
        redis_url="redis://localhost:6379/0"
    )

    engine.run_agent(guild_spec, agent_spec, messaging_config, ...)

    # Verify agent is running
    assert engine.is_agent_running("test-guild", agent_spec.id)

    # Stop agent
    engine.stop_agent("test-guild", agent_spec.id)

    # Verify agent is stopped
    assert not engine.is_agent_running("test-guild", agent_spec.id)
```

### 8.3 Load Tests

```python
def test_100_agents():
    """Test creating 100 agents across multiple hosts."""
    engine = K8sExecutionEngine(...)

    agent_ids = []
    for i in range(100):
        agent_spec = create_test_agent_spec(f"agent-{i}")
        engine.run_agent(guild_spec, agent_spec, ...)
        agent_ids.append(agent_spec.id)

    # Verify all running
    for agent_id in agent_ids:
        assert engine.is_agent_running("test-guild", agent_id)

    # Cleanup
    for agent_id in agent_ids:
        engine.stop_agent("test-guild", agent_id)
```

### 8.4 Fault Tolerance Tests

```python
def test_process_crash_cleanup():
    """Test that crashed processes are cleaned up."""
    manager = AgentProcessManager()
    agent_id = manager.spawn_agent_process(...)

    # Kill process forcefully
    process_info = manager.get_process_info(agent_id)
    os.kill(process_info.pid, signal.SIGKILL)

    # Wait for cleanup
    time.sleep(2)
    dead_agents = manager.cleanup_dead_processes()
    assert agent_id in dead_agents

def test_ttl_cleanup():
    """Test that missed heartbeats cause automatic cleanup."""
    registry = AgentLocationRegistry(redis_client)
    registry.TTL_SECONDS = 2
    registry.register("agent-1", "host-1:50051")

    # Don't send heartbeat
    time.sleep(3)

    # Verify automatically cleaned up
    location = registry.get_location("agent-1")
    assert location is None
```

---

## 9. Implementation Tasks

### Core Utilities

**Create AgentProcessManager**
- Implement process lifecycle management (spawn, stop, track)
- Use JSON serialization instead of pickle for security
- Support guild-agnostic operation (takes guild_id per method)
- Add process monitoring and cleanup methods
- Write comprehensive unit tests with pytest
- **Deliverable:** `rustic_ai/core/execution/process_manager.py` (~200 LOC)

**Update MultiProcessExecutionEngine**
- Refactor to use new `AgentProcessManager` utility
- Remove duplicate process management code
- Maintain backward compatibility with existing API
- Update tests to verify refactored implementation
- **Deliverable:** Updated `multiprocess_exec_engine.py` (~150 LOC, down from 390)

### Registry and Location Services

**Create AgentLocationRegistry**
- Implement Redis-based location tracking
- Use minimal schema (agent_location, host_agents)
- Add TTL-based liveness with 60s expiration
- Implement heartbeat refresh mechanism
- Write unit tests with fakeredis
- **Deliverable:** `rustic_ai/k8s/registry/location_registry.py` (~60 LOC)

**Create AgentPlacementService**
- Implement round-robin placement algorithm
- Support K8s service discovery for agent host pods
- Add method to query pod availability via K8s API
- Provide extensible interface for custom placement strategies
- Write unit tests with mocked K8s client
- **Deliverable:** `rustic_ai/k8s/placement/placement_service.py` (~100 LOC)

### gRPC Protocol and Agent Host

**Define gRPC Protocol**
- Write protocol buffer definition with 5 RPCs (CreateAgent, StopAgent, GetAgentInfo, ListAgents, Health)
- Define message types for requests and responses
- Generate Python stubs using grpc_tools
- Document all message fields and RPC semantics
- **Deliverable:** `rustic_ai/k8s/proto/agent_host.proto` (~50 LOC)

**Implement AgentHostServicer**
- Create gRPC server implementation for all 5 RPCs
- Integrate `AgentProcessManager` for process lifecycle
- Integrate `AgentLocationRegistry` for registration
- Implement heartbeat worker thread (runs every 20s)
- Add structured logging (JSON format)
- Expose Prometheus metrics endpoint
- Write integration tests using grpc.insecure_channel
- **Deliverable:** `rustic_ai/k8s/agent_host/grpc_service.py` (~250 LOC)

**Create Agent Host Server**
- Implement main entry point for agent host pod
- Configure gRPC server with health checks
- Set up signal handling for graceful shutdown
- Initialize logging and telemetry
- Add command-line argument parsing
- **Deliverable:** `rustic_ai/k8s/agent_host/server.py` (~100 LOC)

### Execution Engine

**Implement K8sExecutionEngine**
- Implement all `ExecutionEngine` abstract methods
- Create gRPC channel pool for connections to agent hosts
- Integrate `AgentPlacementService` for host selection
- Integrate `AgentLocationRegistry` for agent lookup
- Add error handling and retry logic for gRPC calls
- Write unit tests with mocked gRPC stubs
- **Deliverable:** `rustic_ai/k8s/execution/k8s_exec_engine.py` (~200 LOC)

### Deployment and Infrastructure

**Create Dockerfile**
- Write multi-stage Dockerfile for agent host image
- Install Python dependencies (core + k8s packages)
- Copy source code and generate gRPC stubs
- Configure entry point and expose ports (50051, 8080)
- Optimize for minimal image size
- **Deliverable:** `rustic_ai/k8s/docker/Dockerfile` (~30 LOC)

**Write Kubernetes Manifests**
- Create Redis StatefulSet with persistent volume
- Create Redis Service (ClusterIP)
- Create Agent Host Deployment with resource limits
- Create Agent Host Service (ClusterIP, ports 50051, 8080)
- Create HorizontalPodAutoscaler with CPU/memory metrics
- Add ConfigMap for environment configuration
- Add Secret for Redis password
- **Deliverable:** `rustic_ai/k8s/deploy/*.yaml` (~200 LOC total)

**Create Helm Chart** (Optional but recommended)
- Package K8s manifests as Helm chart
- Add configurable values (replicas, resources, Redis config)
- Include templates for all resources
- Write values.yaml with sensible defaults
- **Deliverable:** `rustic_ai/k8s/helm/rustic-k8s/` (~300 LOC)

### Testing

**Write End-to-End Tests**
- Test complete flow: create agent → verify running → stop agent
- Test multi-agent scenarios (10+ agents)
- Test agent discovery and lookup operations
- Test graceful shutdown of execution engine
- Use pytest fixtures for setup/teardown
- **Deliverable:** `rustic_ai/k8s/tests/e2e/test_k8s_engine.py` (~200 LOC)

**Write Load Tests**
- Test 100+ agent creation across multiple pods
- Measure agent creation latency
- Measure agent lookup latency
- Test HPA scaling under load
- Use pytest-benchmark or locust
- **Deliverable:** `rustic_ai/k8s/tests/load/test_load.py` (~150 LOC)

**Write Fault Tolerance Tests**
- Test process crash recovery
- Test TTL-based cleanup (missed heartbeats)
- Test agent host pod failure scenarios
- Test Redis connection loss and recovery
- Test gRPC connection failures and retries
- **Deliverable:** `rustic_ai/k8s/tests/fault/test_fault_tolerance.py` (~150 LOC)

### Documentation

**Write API Documentation**
- Document all gRPC APIs with examples
- Document `AgentProcessManager` interface
- Document `AgentLocationRegistry` interface
- Document `K8sExecutionEngine` configuration
- Include code examples for common use cases
- **Deliverable:** `docs/k8s/api_reference.md` (~500 LOC)

**Write Deployment Guide**
- Step-by-step deployment instructions
- Prerequisites (K8s cluster, kubectl, helm)
- Configuration options (Redis, resource limits)
- Monitoring and observability setup
- Troubleshooting common issues
- **Deliverable:** `docs/k8s/deployment_guide.md` (~400 LOC)

**Write Migration Guide**
- Compare Ray vs K8s execution engines
- Decision criteria (when to use K8s vs Ray)
- Migration steps from Ray to K8s
- Code changes required (ExecutionEngine initialization)
- Rollback procedures
- **Deliverable:** `docs/k8s/migration_guide.md` (~300 LOC)

**Write Architecture Documentation**
- Update core architecture docs with K8s engine
- Diagram component interactions
- Explain design decisions
- Performance characteristics
- Future enhancements
- **Deliverable:** `docs/core/execution.md` (update existing, +200 LOC)

### Code Quality and CI/CD

**Add CI/CD Pipeline**
- GitHub Actions workflow for K8s module
- Run unit tests on every commit
- Run integration tests on PR
- Build and push Docker image on merge to main
- Add code coverage reporting
- **Deliverable:** `.github/workflows/k8s.yml` (~100 LOC)

**Add Pre-commit Hooks**
- Run black formatter
- Run flake8 linter
- Run mypy type checker
- Run pytest for quick tests
- **Deliverable:** `.pre-commit-config.yaml` (update existing)

### Summary

**Total Estimated Lines of Code:**
- Core Utilities: ~350 LOC
- Registry and Location: ~160 LOC
- gRPC Protocol and Agent Host: ~400 LOC
- Execution Engine: ~200 LOC
- Deployment: ~530 LOC (including Helm)
- Tests: ~500 LOC
- Documentation: ~1400 LOC
- CI/CD: ~100 LOC

**Grand Total: ~3640 LOC** (including tests and docs)

**Core Implementation (excluding tests/docs): ~1160 LOC**

---

## 10. Migration from Ray

### 10.1 Decision Criteria

**Use K8s Execution Engine when:**
- NOT using fractional GPU sharing
- Want simpler operational model (one orchestrator)
- Agent creation latency of 1-2s is acceptable
- Running on Kubernetes already

**Use Ray Execution Engine when:**
- Need fractional GPU sharing (0.5 GPU per agent)
- Need very fast agent creation (<200ms)
- Using other Ray features (distributed data, Ray Serve, etc.)
- Already have Ray expertise/infrastructure

### 10.2 Migration Steps

**Step 1: Install K8s Execution Engine**
```bash
pip install rustic-ai-k8s
```

**Step 2: Deploy Infrastructure**
```bash
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/agent-host.yaml
kubectl apply -f k8s/hpa.yaml
```

**Step 3: Update Guild Configuration**
```python
# Before (Ray)
from rustic_ai.ray.execution import RayExecutionEngine

guild_manager = GuildManager(
    guild_spec=guild_spec,
    organization_id="my-org",
    execution_engine_class=RayExecutionEngine,
    execution_engine_kwargs={
        "guild_id": guild_spec.id,
        "organization_id": "my-org"
    }
)

# After (K8s)
from rustic_ai.k8s.execution import K8sExecutionEngine

guild_manager = GuildManager(
    guild_spec=guild_spec,
    organization_id="my-org",
    execution_engine_class=K8sExecutionEngine,
    execution_engine_kwargs={
        "guild_id": guild_spec.id,
        "organization_id": "my-org",
        "redis_url": "redis://rustic-redis:6379/0",
        "agent_host_service_name": "agent-host"
    }
)
```

**Step 4: Test Migration**
```python
# Create test agent
guild_manager.create_agent(agent_spec, messaging_config)

# Verify running
assert guild_manager.is_agent_running(agent_spec.id)

# Stop agent
guild_manager.stop_agent(agent_spec.id)
```

**Step 5: Monitor Performance**
- Check agent creation latency (should be 1-2s)
- Check agent lookup latency (should be <1ms)
- Monitor resource usage (CPU, memory)
- Check HPA scaling behavior

### 10.3 Rollback Procedure

If issues are encountered:

```bash
# Revert to Ray
kubectl delete -f k8s/agent-host.yaml
kubectl delete -f k8s/hpa.yaml

# Redeploy Ray cluster
kubectl apply -f ray/ray-cluster.yaml

# Update code to use RayExecutionEngine
# (revert Step 3 changes)
```

---

## 11. Operational Considerations

### 11.1 Monitoring

**Prometheus Metrics:**
```
# Agent metrics
rustic_agents_total{guild_id, host}
rustic_agents_running{guild_id, host}
rustic_agent_creation_duration_seconds{guild_id, host}
rustic_agent_creation_errors_total{guild_id, host}

# Process metrics
rustic_process_cpu_usage{agent_id, host}
rustic_process_memory_usage{agent_id, host}

# gRPC metrics
grpc_server_handled_total{grpc_method, grpc_code}
grpc_server_handling_seconds{grpc_method}

# Registry metrics
rustic_registry_lookups_total{result}
rustic_registry_lookup_duration_seconds
```

**Grafana Dashboards:**
- Agent count per guild
- Agent creation rate and latency
- Process resource usage
- gRPC request rate and latency
- Redis connection pool usage

### 11.2 Logging

**Structured Logging Format:**
```json
{
  "timestamp": "2025-10-21T10:30:00Z",
  "level": "INFO",
  "message": "Agent created successfully",
  "agent_id": "abc123",
  "guild_id": "guild-1",
  "host": "agent-host-2",
  "pid": 12345,
  "duration_ms": 1234
}
```

**Log Aggregation:**
- Use fluentd/fluent-bit to collect logs
- Send to Elasticsearch or Loki
- Create alerts for ERROR/CRITICAL logs

### 11.3 Alerting

**Critical Alerts:**
- Agent host pod down
- Redis connection failure
- High agent creation error rate (>5%)
- High gRPC error rate (>5%)

**Warning Alerts:**
- Agent creation latency >3s
- Agent host CPU >80%
- Agent host memory >90%
- Redis connection pool exhausted

### 11.4 Backup and Recovery

**Redis Backup:**
- Enable Redis persistence (AOF or RDB)
- Schedule periodic backups to S3/GCS
- Test restore procedures regularly

**Agent State:**
- Agent state stored in metastore (PostgreSQL)
- Metastore already has backup/recovery procedures
- Location registry is ephemeral (rebuilds on restart)

---

## 12. Future Enhancements

### 12.1 Resource-Aware Placement

Enhance `AgentPlacementService` to consider:
- CPU/memory availability per host
- Agent resource requirements
- Affinity/anti-affinity rules
- GPU availability (if added)

### 12.2 Agent Migration

Support live agent migration between hosts:
- Snapshot agent state
- Start agent on new host
- Redirect traffic
- Stop old agent

### 12.3 Multi-Region Support

Extend to multi-region deployments:
- Region-aware placement
- Cross-region agent discovery
- Geo-distributed Redis (Redis Cluster)

### 12.4 Custom Metrics Autoscaling

Add custom HPA metrics:
```yaml
- type: Pods
  pods:
    metric:
      name: rustic_agent_density
    target:
      type: AverageValue
      averageValue: "80"  # 80% of max_processes
```

### 12.5 Agent Health Checks

Add application-level health checks:
- Agents expose health endpoint
- Agent host polls periodically
- Restart unhealthy agents
- Report to monitoring system

---

## Appendix A: Comparison with Ray

| Feature | Ray | K8s Engine |
|---------|-----|------------|
| Process Isolation | ✅ Yes | ✅ Yes |
| Fractional GPU | ✅ Yes (0.5 GPU) | ❌ No |
| Agent Creation Latency | 50-200ms | 1-2s |
| Agent Lookup Latency | 0.1-0.5ms | <1ms |
| Operational Complexity | High (2 orchestrators) | Low (1 orchestrator) |
| Auto-restart | ✅ Yes (max 3) | ⚠️ Via K8s pod restart |
| Named Actors | ✅ Yes | ✅ Yes (via registry) |
| Distributed State | ✅ Ray GCS | ✅ Redis |
| Observability | Ray Dashboard | Prometheus + Grafana |
| Multi-region | ✅ Yes | ⚠️ Requires setup |

---

## Appendix B: Lines of Code Breakdown

| Component | LOC |
|-----------|-----|
| **Core Utilities** | |
| AgentProcessManager | 200 |
| MultiProcessExecutionEngine (refactored) | 150 |
| **Registry and Location** | |
| AgentLocationRegistry | 60 |
| AgentPlacementService | 100 |
| **gRPC Protocol** | |
| agent_host.proto | 50 |
| AgentHostServicer | 250 |
| Agent Host Server | 100 |
| **Execution Engine** | |
| K8sExecutionEngine | 200 |
| **Deployment** | |
| Dockerfile | 30 |
| K8s Manifests | 200 |
| Helm Chart | 300 |
| **Total Core Implementation** | **1160** |
| **Tests** | 500 |
| **Documentation** | 1400 |
| **CI/CD** | 100 |
| **Grand Total** | **3640** |

---

## Appendix C: Redis Schema Reference

```
# Agent location (TTL: 60s)
Key: agent_location:{agent_id}
Type: STRING
Value: "{hostname}:{port}"
Example: agent_location:abc123 → "agent-host-2:50051"

# Host agent set (no TTL, updated atomically)
Key: host_agents:{hostname}
Type: SET
Members: {agent_id1, agent_id2, ...}
Example: host_agents:agent-host-2 → {"abc123", "def456"}

# Placement counter (no TTL)
Key: placement:counter
Type: INTEGER
Value: Incrementing counter
Example: placement:counter → 42
```

---

## Appendix D: gRPC Error Codes

| Code | Meaning | Handling |
|------|---------|----------|
| OK | Success | Return normally |
| INVALID_ARGUMENT | Malformed request | Return error to caller |
| RESOURCE_EXHAUSTED | Max processes reached | Retry on different host |
| UNAVAILABLE | Host unreachable | Retry with backoff |
| DEADLINE_EXCEEDED | Operation timeout | Retry or fail |
| INTERNAL | Internal error | Log and return error |
| NOT_FOUND | Agent not found | Return None/False |

---

## Appendix E: Environment Variables

**Agent Host:**
```bash
REDIS_URL="redis://rustic-redis:6379/0"
MAX_PROCESSES=100
LOG_LEVEL=INFO
GRPC_PORT=50051
METRICS_PORT=8080
HEARTBEAT_INTERVAL=20  # seconds
```

**Execution Engine:**
```bash
AGENT_HOST_SERVICE_NAME=agent-host
GRPC_TIMEOUT=30  # seconds
GRPC_MAX_RETRIES=3
```

---

## Conclusion

This specification provides a complete design for a Kubernetes-native execution engine that eliminates the Ray dependency while maintaining the core capabilities needed for multi-agent orchestration. The implementation focuses on simplicity, performance, and operational excellence.

**Key Takeaways:**
- **Simpler Operations**: One orchestrator (K8s) instead of two (K8s + Ray)
- **Process Isolation**: Same model as Ray (process per agent)
- **Minimal State**: Redis tracks only runtime location data
- **High Performance**: gRPC communication, <1ms lookups
- **Code Reuse**: AgentProcessManager utility shared across engines
- **Production Ready**: Monitoring, logging, autoscaling, fault tolerance

The total implementation effort is approximately ~1160 lines of core code, with comprehensive tests, documentation, and deployment automation included.
