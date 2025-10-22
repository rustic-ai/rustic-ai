# K8s Execution Engine - Implementation Guide

## Overview

This guide provides step-by-step instructions for implementing the Kubernetes Execution Engine following Rustic AI's project structure and conventions.

**Reference Documents:**
- Design Specification: `docs/k8s_execution_engine_specification.md`
- Developer Guide: `DEV.md`

---

## Prerequisites

- Python 3.12
- Poetry 1.8+ with `poetry-plugin-mono-repo-deps@0.3.2`
- Docker (for building agent host image)
- Kubernetes cluster (for deployment testing)
- Redis (for location registry)

---

## Project Structure

Rustic AI uses a **monorepo structure** with each module in its own directory:

```
rustic-ai/
├── core/                    # Core framework (AgentProcessManager goes here)
├── ray/                     # Ray execution engine
├── redis/                   # Redis dependencies
├── k8s/                     # NEW: K8s execution engine
├── api/                     # API server
├── cookiecutter-rustic/     # Module template
├── pyproject.toml          # Root project (references all modules)
└── ...
```

**Key Principles:**
1. Each module has its own `pyproject.toml`, `tox.ini`, `tests/`, `src/`
2. Modules depend on `rusticai-core` (core framework)
3. Root `pyproject.toml` references all modules with `develop = true`
4. Use cookiecutter to scaffold new modules
5. Dependencies are managed per-module (NOT in root)

---

## Implementation Tasks

### Phase 1: Project Scaffolding

#### Task 1.1: Create k8s Module

**Use cookiecutter to scaffold the module:**

```bash
cd /home/user/rustic-ai
poetry shell
cookiecutter cookiecutter-rustic/
```

**Cookiecutter prompts:**
```
module_name [custom_module]: k8s
description [module boilerplate]: Kubernetes-native execution engine for Rustic AI
version [0.0.1]: 0.1.0
author_name [Dragonscale Industries Inc.]: Dragonscale Industries Inc.
author_email [dev@dragonscale.ai]: dev@dragonscale.ai
homepage [https://www.rustic.ai/]: https://www.rustic.ai/
repository [https://github.com/dragonscale-ai/rustic-ai]: https://github.com/rustic-ai/rustic-ai
rusticai_location [..]: ..
package_name [rustic_ai]: rustic_ai
```

**This creates:**
```
k8s/
├── pyproject.toml
├── tox.ini
├── README.md
├── src/
│   └── rustic_ai/
│       └── k8s/
│           └── __init__.py
└── tests/
    └── conftest.py
```

**Deliverable:** `k8s/` directory with base structure

---

#### Task 1.2: Update k8s Module Dependencies

**Edit `k8s/pyproject.toml`:**

```toml
[tool.poetry.dependencies]
python = ">=3.12,<3.13"
rusticai-core = { path = "../core", develop = true }
# gRPC dependencies
grpcio = "^1.68.1"
grpcio-tools = "^1.68.1"
# K8s client
kubernetes = "^31.0.0"
# Redis client
redis = "^5.2.1"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3.4"
black = { version = "^24.2.0", extras = ["jupyter"] }
flake8 = "^7.1.2"
tox = "^4.24.1"
isort = "^6.0.0"
mypy = "^1.15.0"
flaky = "^3.8.1"
pytest-asyncio = "^0.26.0"
fakeredis = "^2.27.0"
rusticai-testing = {path = "../testing", develop = true}
```

**Install dependencies:**

```bash
cd k8s
poetry install --with dev --all-extras
```

**Deliverable:** Updated `k8s/pyproject.toml` with dependencies installed

---

#### Task 1.3: Create Module Directory Structure

**Create directories:**

```bash
cd k8s/src/rustic_ai/k8s
mkdir -p execution registry placement agent_host proto
```

**Final structure:**
```
k8s/src/rustic_ai/k8s/
├── __init__.py
├── execution/           # K8sExecutionEngine
│   └── __init__.py
├── registry/            # AgentLocationRegistry
│   └── __init__.py
├── placement/           # AgentPlacementService
│   └── __init__.py
├── agent_host/          # gRPC server and service
│   └── __init__.py
└── proto/               # gRPC protocol definitions
    └── __init__.py
```

**Create test structure:**

```bash
cd k8s/tests
mkdir -p unit integration e2e load
```

**Deliverable:** Complete directory structure

---

### Phase 2: Core Utilities (in rustic_ai/core)

#### Task 2.1: Add AgentProcessManager to Core

**Location:** `core/src/rustic_ai/core/guild/execution/process_manager.py`

**Why in core?** This utility is reusable by both `MultiProcessExecutionEngine` (local) and `K8sExecutionEngine` (distributed).

**File structure:**
```python
"""
Agent Process Manager

Guild-agnostic utility for managing agent processes.
Uses JSON serialization for security (not pickle).
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
import multiprocessing
import json
import time
import os
import signal

@dataclass
class AgentProcessInfo:
    """Information about a running agent process."""
    agent_id: str
    guild_id: str
    pid: int
    is_alive: bool
    created_at: float

class AgentProcessManager:
    """Reusable utility for managing agent processes."""

    def __init__(self, max_processes: int = 100):
        # Implementation per spec
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
        """Spawn a new agent process using JSON serialization."""
        pass

    # ... other methods per spec
```

**Key differences from existing MultiProcessExecutionEngine:**
1. **Guild-agnostic**: Takes `guild_id` in methods, not constructor
2. **JSON serialization**: No pickle (security)
3. **Reusable**: Can be used by multiple execution engines

**Test file:** `core/tests/guild/execution/test_process_manager.py`

**Deliverable:** `core/src/rustic_ai/core/guild/execution/process_manager.py` (~200 LOC)

---

#### Task 2.2: Refactor MultiProcessExecutionEngine

**Location:** `core/src/rustic_ai/core/guild/execution/multiprocess/multiprocess_exec_engine.py`

**Changes:**
1. Import and use `AgentProcessManager`
2. Remove duplicate process management code
3. Keep ExecutionEngine interface implementation

**Before (390 LOC):**
```python
class MultiProcessExecutionEngine(ExecutionEngine):
    def __init__(self, guild_id, organization_id):
        # Process management code here (duplicate!)
        pass

    def run_agent(self, ...):
        # Spawn process directly
        process = multiprocessing.Process(...)
        process.start()
```

**After (~150 LOC):**
```python
from rustic_ai.core.guild.execution.process_manager import AgentProcessManager

class MultiProcessExecutionEngine(ExecutionEngine):
    def __init__(self, guild_id, organization_id):
        self.guild_id = guild_id
        self.organization_id = organization_id
        self.process_manager = AgentProcessManager(max_processes=100)

    def run_agent(self, agent_spec, guild_spec, ...):
        # Delegate to process manager
        agent_id = self.process_manager.spawn_agent_process(
            agent_spec, guild_spec, messaging_config, machine_id, ...
        )
        return None  # No direct agent instance
```

**Testing:** Update existing tests to ensure no regressions

**Deliverable:** Refactored `multiprocess_exec_engine.py` (~150 LOC, down from 390)

---

#### Task 2.3: Update Core Module

**Update core dependencies if needed:**

From root directory:
```bash
cd core
poetry update
cd ..
./scripts/run_on_each.sh poetry update rusticai-core
```

**Deliverable:** Core module with AgentProcessManager utility

---

### Phase 3: gRPC Protocol

#### Task 3.1: Create Protocol Definition

**Location:** `k8s/src/rustic_ai/k8s/proto/agent_host.proto`

**Content:** (see specification Appendix for full definition)

```protobuf
syntax = "proto3";

package rustic_ai.k8s.agent_host;

service AgentHostService {
  rpc CreateAgent(CreateAgentRequest) returns (CreateAgentResponse);
  rpc StopAgent(StopAgentRequest) returns (StopAgentResponse);
  rpc GetAgentInfo(GetAgentInfoRequest) returns (AgentInfo);
  rpc ListAgents(ListAgentsRequest) returns (ListAgentsResponse);
  rpc Health(HealthRequest) returns (HealthResponse);
}

message CreateAgentRequest {
  bytes agent_spec = 1;        // JSON-serialized
  bytes guild_spec = 2;
  bytes messaging_config = 3;
  int32 machine_id = 4;
  string client_type = 5;
  bytes client_properties = 6;
}

// ... other messages
```

**Deliverable:** `agent_host.proto` (~50 LOC)

---

#### Task 3.2: Generate gRPC Stubs

**Add build script:** `k8s/scripts/generate_protos.sh`

```bash
#!/bin/bash
set -e

PROTO_DIR="src/rustic_ai/k8s/proto"
OUT_DIR="src/rustic_ai/k8s/proto"

python -m grpc_tools.protoc \
  -I. \
  --python_out=$OUT_DIR \
  --grpc_python_out=$OUT_DIR \
  --pyi_out=$OUT_DIR \
  $PROTO_DIR/agent_host.proto

echo "Generated gRPC stubs in $OUT_DIR"
```

**Make executable and run:**

```bash
chmod +x k8s/scripts/generate_protos.sh
cd k8s
./scripts/generate_protos.sh
```

**Generated files:**
- `agent_host_pb2.py` - Message classes
- `agent_host_pb2_grpc.py` - Service stubs
- `agent_host_pb2.pyi` - Type hints

**Update `.gitignore`:**
```
# Generated gRPC files
*_pb2.py
*_pb2_grpc.py
*_pb2.pyi
```

**Add to build process in pyproject.toml:**

```toml
[tool.poetry.build]
script = "scripts/generate_protos.sh"
```

**Deliverable:** Generated gRPC Python stubs

---

### Phase 4: K8s Module Implementation

#### Task 4.1: Implement AgentLocationRegistry

**Location:** `k8s/src/rustic_ai/k8s/registry/location_registry.py`

**Content:** (see specification Section 5.3)

```python
"""Redis-based agent location registry."""

import redis
from typing import Optional, Dict, List

class AgentLocationRegistry:
    """
    Tracks runtime agent locations and liveness.

    Redis Schema:
      agent_location:{agent_id} → "hostname:port" (TTL: 60s)
      host_agents:{hostname} → SET of agent_ids
    """

    TTL_SECONDS = 60

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def register(self, agent_id: str, host_address: str) -> None:
        """Register agent location with TTL."""
        # SET agent_location:{agent_id} "{host_address}" EX 60
        # SADD host_agents:{hostname} {agent_id}
        pass

    # ... other methods per spec
```

**Test file:** `k8s/tests/unit/test_location_registry.py`

```python
import pytest
import fakeredis
from rustic_ai.k8s.registry.location_registry import AgentLocationRegistry

@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()

@pytest.fixture
def registry(redis_client):
    return AgentLocationRegistry(redis_client)

def test_register_and_lookup(registry):
    registry.register("agent-1", "host-1:50051")
    location = registry.get_location("agent-1")
    assert location == "host-1:50051"

def test_ttl_expiration(registry):
    # Test TTL cleanup
    pass

def test_heartbeat_refresh(registry):
    # Test heartbeat extends TTL
    pass
```

**Deliverable:** `location_registry.py` (~60 LOC) + tests

---

#### Task 4.2: Implement AgentPlacementService

**Location:** `k8s/src/rustic_ai/k8s/placement/placement_service.py`

**Content:**

```python
"""Agent placement service for K8s pods."""

from typing import List
import redis
from kubernetes import client, config

class AgentPlacementService:
    """
    Decides which agent host pod to create agents on.

    Initial implementation: Round-robin
    Future: Resource-aware placement
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        k8s_namespace: str = "default",
        service_name: str = "agent-host"
    ):
        self.redis = redis_client
        self.k8s_namespace = k8s_namespace
        self.service_name = service_name

        # Initialize K8s client
        try:
            config.load_incluster_config()  # Running in cluster
        except:
            config.load_kube_config()  # Local development

        self.k8s_api = client.CoreV1Api()

    def select_host(self, agent_spec: AgentSpec) -> str:
        """
        Select optimal host for agent placement.

        Returns:
            Host address (hostname:port)
        """
        hosts = self._list_available_hosts()

        if not hosts:
            raise RuntimeError("No agent host pods available")

        # Round-robin placement
        counter = self.redis.incr("placement:counter")
        selected = hosts[counter % len(hosts)]

        return selected

    def _list_available_hosts(self) -> List[str]:
        """Query K8s for available agent host pods."""
        # Get endpoints for agent-host service
        endpoints = self.k8s_api.read_namespaced_endpoints(
            name=self.service_name,
            namespace=self.k8s_namespace
        )

        hosts = []
        if endpoints.subsets:
            for subset in endpoints.subsets:
                for address in subset.addresses:
                    hostname = address.target_ref.name  # Pod name
                    hosts.append(f"{hostname}:50051")

        return hosts
```

**Test file:** `k8s/tests/unit/test_placement_service.py`

**Deliverable:** `placement_service.py` (~100 LOC) + tests

---

#### Task 4.3: Implement AgentHostServicer (gRPC Server)

**Location:** `k8s/src/rustic_ai/k8s/agent_host/grpc_service.py`

**Content:**

```python
"""gRPC server for agent host pod."""

import grpc
from concurrent import futures
import threading
import time
import os

from rustic_ai.k8s.proto import agent_host_pb2, agent_host_pb2_grpc
from rustic_ai.core.guild.execution.process_manager import AgentProcessManager
from rustic_ai.k8s.registry.location_registry import AgentLocationRegistry

class AgentHostServicer(agent_host_pb2_grpc.AgentHostServiceServicer):
    """gRPC service implementation for agent host."""

    def __init__(
        self,
        redis_client,
        max_processes: int = 100,
        heartbeat_interval: int = 20
    ):
        self.process_manager = AgentProcessManager(max_processes)
        self.location_registry = AgentLocationRegistry(redis_client)
        self.my_address = f"{os.getenv('HOSTNAME', 'localhost')}:50051"
        self.heartbeat_interval = heartbeat_interval

        # Start heartbeat worker
        self._start_heartbeat_worker()

    def CreateAgent(self, request, context):
        """Create a new agent process."""
        try:
            # Deserialize specs
            agent_spec = json.loads(request.agent_spec)
            guild_spec = json.loads(request.guild_spec)
            messaging_config = json.loads(request.messaging_config)

            # Spawn process
            agent_id = self.process_manager.spawn_agent_process(
                agent_spec=agent_spec,
                guild_spec=guild_spec,
                messaging_config=messaging_config,
                machine_id=request.machine_id,
                client_type_name=request.client_type,
                client_properties=json.loads(request.client_properties)
            )

            # Register location
            self.location_registry.register(agent_id, self.my_address)

            # Get PID
            process_info = self.process_manager.get_process_info(agent_id)

            return agent_host_pb2.CreateAgentResponse(
                agent_id=agent_id,
                pid=process_info.pid,
                success=True,
                error=""
            )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return agent_host_pb2.CreateAgentResponse(
                agent_id="",
                pid=0,
                success=False,
                error=str(e)
            )

    def StopAgent(self, request, context):
        """Stop an agent process."""
        # Implementation per spec
        pass

    # ... other RPC methods

    def _start_heartbeat_worker(self):
        """Start background thread for heartbeats."""
        def heartbeat_loop():
            while True:
                time.sleep(self.heartbeat_interval)
                self._send_heartbeats()

        thread = threading.Thread(target=heartbeat_loop, daemon=True)
        thread.start()

    def _send_heartbeats(self):
        """Refresh TTL for all local agents."""
        processes = self.process_manager.list_processes()
        for agent_id, info in processes.items():
            if info.is_alive:
                self.location_registry.heartbeat(agent_id)
            else:
                self.location_registry.deregister(agent_id)
```

**Test file:** `k8s/tests/integration/test_grpc_service.py`

**Deliverable:** `grpc_service.py` (~250 LOC) + integration tests

---

#### Task 4.4: Implement Agent Host Server

**Location:** `k8s/src/rustic_ai/k8s/agent_host/server.py`

**Content:**

```python
"""Entry point for agent host pod."""

import grpc
from concurrent import futures
import redis
import signal
import sys
import os
import logging

from rustic_ai.k8s.agent_host.grpc_service import AgentHostServicer
from rustic_ai.k8s.proto import agent_host_pb2_grpc

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger(__name__)

def serve():
    """Start the gRPC server."""
    # Redis connection
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.from_url(redis_url)

    # Configuration
    max_processes = int(os.getenv("MAX_PROCESSES", "100"))
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))

    # Create server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add servicer
    servicer = AgentHostServicer(
        redis_client=redis_client,
        max_processes=max_processes
    )
    agent_host_pb2_grpc.add_AgentHostServiceServicer_to_server(servicer, server)

    # Start server
    server.add_insecure_port(f'[::]:{grpc_port}')
    server.start()

    logger.info(f"Agent host gRPC server started on port {grpc_port}")
    logger.info(f"Max processes: {max_processes}")

    # Graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutting down gracefully...")
        servicer.process_manager.shutdown()
        server.stop(grace=10)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for termination
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
```

**Entry point:** Add to `k8s/pyproject.toml`

```toml
[tool.poetry.scripts]
rustic-agent-host = "rustic_ai.k8s.agent_host.server:serve"
```

**Deliverable:** `server.py` (~100 LOC)

---

#### Task 4.5: Implement K8sExecutionEngine

**Location:** `k8s/src/rustic_ai/k8s/execution/k8s_exec_engine.py`

**Content:**

```python
"""Kubernetes-native execution engine."""

import grpc
from typing import Dict, Optional, Type, Any, List

from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.guild.guild_spec import GuildSpec, AgentSpec
from rustic_ai.core.messaging import MessagingConfig, Client, MessageTrackingClient
from rustic_ai.core.agent import Agent

from rustic_ai.k8s.registry.location_registry import AgentLocationRegistry
from rustic_ai.k8s.placement.placement_service import AgentPlacementService
from rustic_ai.k8s.proto import agent_host_pb2, agent_host_pb2_grpc

class K8sExecutionEngine(ExecutionEngine):
    """
    Kubernetes-native execution engine.

    Creates agents on long-lived agent host pods via gRPC.
    """

    def __init__(
        self,
        guild_id: str,
        organization_id: str,
        redis_url: str,
        agent_host_service_name: str = "agent-host",
        k8s_namespace: str = "default"
    ):
        super().__init__(guild_id, organization_id)

        # Redis client
        import redis
        self.redis_client = redis.from_url(redis_url)

        # Services
        self.location_registry = AgentLocationRegistry(self.redis_client)
        self.placement_service = AgentPlacementService(
            redis_client=self.redis_client,
            k8s_namespace=k8s_namespace,
            service_name=agent_host_service_name
        )

        # gRPC channel pool
        self.channels: Dict[str, grpc.Channel] = {}

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
        """Create an agent on agent host pod via gRPC."""

        # Select host
        host_address = self.placement_service.select_host(agent_spec)

        # Get/create gRPC channel
        channel = self._get_channel(host_address)
        stub = agent_host_pb2_grpc.AgentHostServiceStub(channel)

        # Prepare request
        import json
        request = agent_host_pb2.CreateAgentRequest(
            agent_spec=json.dumps(agent_spec.to_dict()).encode(),
            guild_spec=json.dumps(guild_spec.to_dict()).encode(),
            messaging_config=json.dumps(messaging_config.to_dict()).encode(),
            machine_id=machine_id,
            client_type=client_type.__name__,
            client_properties=json.dumps(client_properties).encode()
        )

        # Call gRPC
        try:
            response = stub.CreateAgent(request, timeout=30)
            if not response.success:
                raise RuntimeError(f"Agent creation failed: {response.error}")

            return None  # No direct agent instance in distributed mode

        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC error: {e.details()}")

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """Stop agent via gRPC."""
        # Look up location
        host_address = self.location_registry.get_location(agent_id)
        if not host_address:
            return  # Already stopped

        # Send stop request
        channel = self._get_channel(host_address)
        stub = agent_host_pb2_grpc.AgentHostServiceStub(channel)

        request = agent_host_pb2.StopAgentRequest(
            agent_id=agent_id,
            timeout=10
        )

        try:
            stub.StopAgent(request, timeout=15)
        except grpc.RpcError:
            pass  # Best effort

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """Check if agent is running via registry lookup."""
        location = self.location_registry.get_location(agent_id)
        return location is not None

    def _get_channel(self, host_address: str) -> grpc.Channel:
        """Get or create gRPC channel to host."""
        if host_address not in self.channels:
            self.channels[host_address] = grpc.insecure_channel(host_address)
        return self.channels[host_address]

    # ... other methods per ExecutionEngine interface
```

**Test file:** `k8s/tests/e2e/test_k8s_exec_engine.py`

**Deliverable:** `k8s_exec_engine.py` (~200 LOC) + E2E tests

---

### Phase 5: Deployment

#### Task 5.1: Create Dockerfile

**Location:** `k8s/docker/Dockerfile`

**Content:**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY k8s/pyproject.toml k8s/poetry.lock ./k8s/
COPY core/ ./core/

RUN pip install --no-cache-dir poetry && \
    cd k8s && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-ansi

# Copy source code
COPY k8s/src ./k8s/src
COPY k8s/scripts ./k8s/scripts

# Generate gRPC stubs
RUN cd k8s && ./scripts/generate_protos.sh

# Expose ports
EXPOSE 50051 8080

# Run agent host server
CMD ["python", "-m", "rustic_ai.k8s.agent_host.server"]
```

**Build script:** `k8s/scripts/build_docker.sh`

```bash
#!/bin/bash
set -e

IMAGE_NAME=${1:-"rusticai-agent-host"}
IMAGE_TAG=${2:-"latest"}

docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -f k8s/docker/Dockerfile .

echo "Built image: ${IMAGE_NAME}:${IMAGE_TAG}"
```

**Deliverable:** Dockerfile + build script

---

#### Task 5.2: Create Kubernetes Manifests

**Location:** `k8s/deploy/`

**Files:**
- `redis.yaml` - Redis StatefulSet
- `agent-host.yaml` - Agent Host Deployment + Service
- `hpa.yaml` - HorizontalPodAutoscaler
- `kustomization.yaml` - Kustomize config

**See specification Section 6.1 for complete YAML manifests**

**Deliverable:** Complete K8s manifests (~200 LOC total)

---

### Phase 6: Testing

#### Task 6.1: Unit Tests

**Run tests:**
```bash
cd k8s
poetry run pytest tests/unit -vvv
```

**Coverage:**
- `test_location_registry.py` - Redis operations
- `test_placement_service.py` - Placement logic
- `test_process_manager.py` - Process lifecycle (in core/tests)

**Deliverable:** Comprehensive unit test suite

---

#### Task 6.2: Integration Tests

**Setup:** Start Redis for integration tests

```bash
docker compose -f scripts/redis/docker-compose.yml up -d
```

**Run tests:**
```bash
cd k8s
poetry run pytest tests/integration -vvv
```

**Deliverable:** gRPC service integration tests

---

#### Task 6.3: End-to-End Tests

**Setup:** Deploy to K8s (minikube/kind for local)

```bash
kubectl apply -f k8s/deploy/
```

**Run tests:**
```bash
cd k8s
poetry run pytest tests/e2e -vvv
```

**Deliverable:** Full E2E test suite

---

### Phase 7: Integration with Root Project

#### Task 7.1: Add k8s to Root pyproject.toml

**Edit `/home/user/rustic-ai/pyproject.toml`:**

```toml
[tool.poetry.dependencies]
# ... existing dependencies
rusticai-k8s = { path = "./k8s", develop = true }
```

**Update dependencies:**

```bash
cd /home/user/rustic-ai
poetry update rusticai-k8s
```

**Deliverable:** k8s module integrated into root project

---

#### Task 7.2: Update Core Module in Dependent Modules

**After modifying core (AgentProcessManager):**

```bash
cd /home/user/rustic-ai
./scripts/run_on_each.sh poetry update rusticai-core
```

**This updates all modules that depend on core**

**Deliverable:** All modules updated with new core version

---

#### Task 7.3: Run Full Test Suite

**From root:**

```bash
cd /home/user/rustic-ai
poetry run tox
```

**This runs tests for ALL modules**

**Deliverable:** All tests passing

---

### Phase 8: Documentation

#### Task 8.1: Update Module README

**Edit `k8s/README.md`:**

```markdown
# Rustic AI - Kubernetes Execution Engine

Kubernetes-native execution engine for Rustic AI multi-agent framework.

## Features

- Process isolation (one process per agent)
- gRPC-based communication
- Redis location registry
- K8s-native scaling (HPA)
- Competitive performance with Ray

## Installation

\`\`\`bash
pip install rusticai-k8s
\`\`\`

## Usage

\`\`\`python
from rustic_ai.k8s.execution import K8sExecutionEngine

engine = K8sExecutionEngine(
    guild_id="my-guild",
    organization_id="my-org",
    redis_url="redis://rustic-redis:6379/0"
)
\`\`\`

## Deployment

See `docs/k8s_execution_engine_specification.md` for full deployment guide.
```

**Deliverable:** Complete README

---

#### Task 8.2: Add API Documentation

**Use mkdocs (existing in root):**

Create `docs/k8s/` directory with:
- `index.md` - Overview
- `api_reference.md` - API documentation
- `deployment_guide.md` - Deployment instructions
- `migration_guide.md` - Migration from Ray

**Deliverable:** Complete API docs

---

### Phase 9: CI/CD

#### Task 9.1: Add GitHub Actions Workflow

**Location:** `.github/workflows/k8s.yml`

```yaml
name: K8s Module Tests

on:
  push:
    paths:
      - 'k8s/**'
      - 'core/**'
  pull_request:
    paths:
      - 'k8s/**'
      - 'core/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install Poetry
        run: |
          pip install poetry
          poetry self add poetry-plugin-mono-repo-deps@0.3.2

      - name: Install dependencies
        run: |
          cd k8s
          poetry install --with dev --all-extras

      - name: Run tests
        run: |
          cd k8s
          poetry run tox

      - name: Build Docker image
        run: |
          docker build -t rusticai-agent-host:test -f k8s/docker/Dockerfile .
```

**Deliverable:** CI/CD pipeline

---

## Summary Checklist

### Module Setup
- [ ] Created k8s module with cookiecutter
- [ ] Updated k8s/pyproject.toml with dependencies
- [ ] Created directory structure
- [ ] Added k8s to root pyproject.toml

### Core Utilities
- [ ] Implemented AgentProcessManager in core
- [ ] Refactored MultiProcessExecutionEngine
- [ ] Updated core module dependencies

### gRPC Protocol
- [ ] Created agent_host.proto
- [ ] Generated Python gRPC stubs
- [ ] Added proto generation to build process

### K8s Module Implementation
- [ ] Implemented AgentLocationRegistry
- [ ] Implemented AgentPlacementService
- [ ] Implemented AgentHostServicer
- [ ] Implemented Agent Host server
- [ ] Implemented K8sExecutionEngine

### Deployment
- [ ] Created Dockerfile
- [ ] Created Kubernetes manifests
- [ ] Created build/deploy scripts

### Testing
- [ ] Unit tests (all passing)
- [ ] Integration tests (all passing)
- [ ] End-to-end tests (all passing)
- [ ] Root project tests (all passing)

### Documentation
- [ ] Updated k8s/README.md
- [ ] Created API documentation
- [ ] Created deployment guide
- [ ] Created migration guide

### CI/CD
- [ ] Added GitHub Actions workflow
- [ ] Configured automated testing
- [ ] Configured Docker image builds

---

## Development Commands Reference

```bash
# Module setup
cookiecutter cookiecutter-rustic/
cd k8s && poetry install --with dev --all-extras

# Generate gRPC stubs
cd k8s && ./scripts/generate_protos.sh

# Run tests (k8s module only)
cd k8s && poetry run pytest tests/unit -vvv
cd k8s && poetry run tox

# Run tests (all modules)
cd /home/user/rustic-ai && poetry run tox

# Update dependencies after core changes
./scripts/run_on_each.sh poetry update rusticai-core

# Build Docker image
cd k8s && ./scripts/build_docker.sh rusticai-agent-host latest

# Deploy to K8s
kubectl apply -f k8s/deploy/

# Check deployment
kubectl get pods -l app=agent-host
kubectl logs -l app=agent-host

# Format code
cd k8s && poetry run black src tests
cd k8s && poetry run isort src tests

# Lint code
cd k8s && poetry run flake8 src tests
cd k8s && poetry run mypy src tests
```

---

## Next Steps

1. Start with **Phase 1: Project Scaffolding**
2. Implement **Phase 2: Core Utilities** (AgentProcessManager)
3. Continue through phases sequentially
4. Run tests after each phase
5. Commit with conventional commit messages (e.g., `feat: add AgentProcessManager utility`)

**Estimated Timeline:** ~2-3 weeks for core implementation + testing + documentation
