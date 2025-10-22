# Kubernetes Manifests for Rustic AI Execution Engine

This directory contains Kubernetes manifests for deploying the Rustic AI K8s execution engine.

## Components

### 1. Namespace (`namespace.yaml`)
- Creates `rustic-ai` namespace for all components
- Isolates execution engine resources

### 2. Redis (`redis.yaml`)
- **Deployment**: Single replica Redis instance for location tracking
- **Service**: ClusterIP service for internal access
- **ConfigMap**: Redis configuration (256MB max memory, LRU eviction)
- **Resources**:
  - Requests: 100m CPU, 128Mi memory
  - Limits: 500m CPU, 512Mi memory
- **Probes**: Liveness and readiness checks using `redis-cli ping`

### 3. Agent Host (`agent-host.yaml`)
- **ServiceAccount**: For K8s API access (endpoints discovery)
- **Role/RoleBinding**: Permissions to read endpoints and pods
- **Deployment**: 3 replicas running agent processes
- **Service**: Headless ClusterIP service for direct pod access
- **Resources**:
  - Requests: 500m CPU, 1Gi memory
  - Limits: 4000m CPU, 8Gi memory
- **Environment Variables**:
  - `REDIS_URL`: Redis connection URL
  - `GRPC_PORT`: gRPC server port (50051)
  - `MAX_PROCESSES`: Max agent processes per pod (100)
  - `HEARTBEAT_INTERVAL`: Heartbeat interval in seconds (20)
  - `HOSTNAME`: Pod name from metadata
- **Probes**: Health checks using gRPC Health RPC
- **Security**: Non-root user (1000), no privilege escalation

### 4. HorizontalPodAutoscaler (`hpa.yaml`)
- **Min replicas**: 3
- **Max replicas**: 20
- **Metrics**:
  - CPU: 70% utilization
  - Memory: 75% utilization
- **Scale down**: Gradual (5min stabilization, 50% or 2 pods per minute)
- **Scale up**: Aggressive (no stabilization, 100% or 4 pods per minute)

## Deployment

### Prerequisites
- Kubernetes cluster (1.24+)
- kubectl configured
- Metrics server installed (for HPA)

### Option 1: Deploy with kubectl

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Deploy Redis
kubectl apply -f redis.yaml

# Wait for Redis to be ready
kubectl wait --for=condition=ready pod -l app=redis -n rustic-ai --timeout=60s

# Deploy agent host
kubectl apply -f agent-host.yaml

# Wait for agent hosts to be ready
kubectl wait --for=condition=ready pod -l app=agent-host -n rustic-ai --timeout=120s

# Deploy HPA
kubectl apply -f hpa.yaml
```

### Option 2: Deploy with Kustomize

```bash
# Deploy all components
kubectl apply -k .

# Verify deployment
kubectl get all -n rustic-ai
```

## Building the Docker Image

Before deploying, build and push the agent host image:

```bash
# From the repository root
cd k8s

# Build image
docker build -t rustic-ai/agent-host:latest -f Dockerfile ..

# Tag for your registry
docker tag rustic-ai/agent-host:latest your-registry/rustic-ai/agent-host:latest

# Push to registry
docker push your-registry/rustic-ai/agent-host:latest

# Update kustomization.yaml with your registry
sed -i 's|rustic-ai/agent-host|your-registry/rustic-ai/agent-host|g' kustomization.yaml
```

## Verification

```bash
# Check all resources
kubectl get all -n rustic-ai

# Check agent host pods
kubectl get pods -n rustic-ai -l app=agent-host

# Check agent host logs
kubectl logs -n rustic-ai -l app=agent-host --tail=50

# Check Redis
kubectl get pods -n rustic-ai -l app=redis

# Check HPA status
kubectl get hpa -n rustic-ai

# Test agent host health
kubectl exec -n rustic-ai -it deployment/agent-host -- python -c "
import grpc
from rustic_ai.k8s.proto import agent_host_pb2, agent_host_pb2_grpc
channel = grpc.insecure_channel('localhost:50051')
stub = agent_host_pb2_grpc.AgentHostServiceStub(channel)
request = agent_host_pb2.HealthRequest()
response = stub.Health(request)
print(f'Healthy: {response.healthy}, Agents: {response.agent_count}, Host: {response.hostname}')
"
```

## Scaling

### Manual Scaling
```bash
# Scale agent host deployment
kubectl scale deployment agent-host -n rustic-ai --replicas=5
```

### Autoscaling
The HPA will automatically scale based on CPU/memory utilization:
- Scale up quickly when load increases
- Scale down gradually to avoid thrashing

## Monitoring

### Metrics
```bash
# HPA metrics
kubectl get hpa agent-host -n rustic-ai --watch

# Pod resource usage
kubectl top pods -n rustic-ai
```

### Logs
```bash
# Follow agent host logs
kubectl logs -n rustic-ai -l app=agent-host --follow

# Follow Redis logs
kubectl logs -n rustic-ai -l app=redis --follow
```

## Cleanup

```bash
# Delete all resources
kubectl delete -k .

# Or delete namespace (cascading delete)
kubectl delete namespace rustic-ai
```

## Configuration

### Redis
Modify `redis.yaml` ConfigMap to change Redis configuration:
- `maxmemory`: Maximum memory usage
- `maxmemory-policy`: Eviction policy
- `save`: Persistence settings

### Agent Host
Modify `agent-host.yaml` Deployment environment variables:
- `MAX_PROCESSES`: Increase/decrease max agents per pod
- `HEARTBEAT_INTERVAL`: Adjust heartbeat frequency
- Resources: Adjust CPU/memory requests/limits

### HPA
Modify `hpa.yaml` to change autoscaling behavior:
- `minReplicas`/`maxReplicas`: Scale range
- `averageUtilization`: CPU/memory thresholds
- `behavior`: Scale up/down policies

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Kubernetes Cluster                 │
│                                                      │
│  ┌────────────┐                                     │
│  │   Redis    │                                     │
│  │ (location  │                                     │
│  │  registry) │                                     │
│  └─────┬──────┘                                     │
│        │                                            │
│  ┌─────┴──────────────────────────────────────┐    │
│  │         Agent Host Deployment              │    │
│  │                                             │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │    │
│  │  │ Pod 1    │  │ Pod 2    │  │ Pod 3    │ │    │
│  │  │ (3-20x)  │  │          │  │          │ │    │
│  │  │          │  │          │  │          │ │    │
│  │  │ Agent    │  │ Agent    │  │ Agent    │ │    │
│  │  │ Host     │  │ Host     │  │ Host     │ │    │
│  │  │ Server   │  │ Server   │  │ Server   │ │    │
│  │  │          │  │          │  │          │ │    │
│  │  │ (gRPC)   │  │ (gRPC)   │  │ (gRPC)   │ │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘ │    │
│  │       │             │             │        │    │
│  │  ┌────┴─────────────┴─────────────┴─────┐ │    │
│  │  │    Headless Service (agent-host)     │ │    │
│  │  └──────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │     HorizontalPodAutoscaler (HPA)          │   │
│  │  - Min: 3, Max: 20                         │   │
│  │  - CPU: 70%, Memory: 75%                   │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Security

- **Non-root user**: Agent host runs as user 1000
- **No privilege escalation**: Security context enforced
- **RBAC**: Minimal permissions (read endpoints/pods only)
- **Network policies**: (TODO) Add network policies to restrict traffic
- **Secrets**: (TODO) Use K8s secrets for sensitive configuration

## Troubleshooting

### Agent host pods not starting
```bash
# Check pod events
kubectl describe pod -n rustic-ai -l app=agent-host

# Check image pull
kubectl get pods -n rustic-ai -l app=agent-host -o jsonpath='{.items[0].status.containerStatuses[0].state}'

# Check logs
kubectl logs -n rustic-ai -l app=agent-host
```

### Redis connection issues
```bash
# Test Redis connectivity from agent host
kubectl exec -n rustic-ai deployment/agent-host -- redis-cli -h redis ping

# Check Redis logs
kubectl logs -n rustic-ai -l app=redis
```

### HPA not scaling
```bash
# Check metrics server
kubectl get apiservice v1beta1.metrics.k8s.io -o yaml

# Check HPA status
kubectl describe hpa agent-host -n rustic-ai

# Check pod metrics
kubectl top pods -n rustic-ai
```
