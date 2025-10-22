# Rustic AI - Kubernetes Execution Engine

Kubernetes-native execution engine for Rustic AI multi-agent framework.

## Overview

The K8s execution engine provides a Kubernetes-native alternative to the Ray-based execution engine, eliminating the complexity of running two orchestration layers (K8s + Ray) while maintaining similar multi-agent orchestration capabilities.

## Features

- **Process Isolation**: One dedicated process per agent (same as Ray actors)
- **gRPC Communication**: High-performance protocol between execution engine and agent host pods
- **Redis Location Registry**: Runtime agent location tracking with TTL-based liveness
- **K8s-Native Scaling**: Horizontal Pod Autoscaler (HPA) for automatic scaling
- **Competitive Performance**: ~1-2s agent creation (comparable to Ray's real-world ~1s)
- **Operational Simplicity**: Single orchestrator (K8s) instead of two (K8s + Ray)

## Architecture

```
Guild Manager → gRPC → Agent Host Pods (running agent processes) → Redis (location registry)
```

## When to Use

**Choose K8s Engine when:**
- NOT using fractional GPU sharing
- Want simpler operations (one orchestrator)
- Agents are long-lived (hours/days)
- Already running on Kubernetes

**Choose Ray Engine when:**
- Need fractional GPU sharing (0.5 GPU per agent)
- Very dynamic workloads (frequent creation/deletion)
- Already using other Ray features

## Installation

```bash
pip install rusticai-k8s
```

## Usage

```python
from rustic_ai.k8s.execution import K8sExecutionEngine
from rustic_ai.core.guild import GuildManager

# Create execution engine
engine = K8sExecutionEngine(
    guild_id="my-guild",
    organization_id="my-org",
    redis_url="redis://rustic-redis:6379/0",
    agent_host_service_name="agent-host",
    k8s_namespace="default"
)

# Use with GuildManager
guild_manager = GuildManager(
    guild_spec=guild_spec,
    organization_id="my-org",
    execution_engine_class=K8sExecutionEngine,
    execution_engine_kwargs={
        "guild_id": guild_spec.id,
        "organization_id": "my-org",
        "redis_url": "redis://rustic-redis:6379/0"
    }
)
```

## Deployment

See [K8s Execution Engine Specification](../docs/k8s_execution_engine_specification.md) for complete deployment guide.

### Quick Deploy

```bash
# Deploy Redis
kubectl apply -f deploy/redis.yaml

# Deploy Agent Host pods
kubectl apply -f deploy/agent-host.yaml

# Deploy HPA
kubectl apply -f deploy/hpa.yaml
```

## Development

```bash
# Install dependencies
cd k8s
poetry install --with dev --all-extras

# Run tests
poetry run pytest

# Format code
poetry run tox -e format

# Lint code
poetry run tox -e lint

# Run all tests
poetry run tox
```

## Documentation

- [Specification](../docs/k8s_execution_engine_specification.md) - Complete design specification
- [Implementation Guide](../docs/k8s_implementation_guide.md) - Step-by-step implementation guide
- [Migration Guide](../docs/k8s_execution_engine_specification.md#10-migration-from-ray) - Migrating from Ray

## License

Apache-2.0
