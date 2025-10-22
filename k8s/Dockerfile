# Multi-stage Dockerfile for Rustic AI Agent Host
# This container runs on K8s pods to host agent processes

# Stage 1: Build gRPC stubs
FROM python:3.12-slim AS grpc-builder

WORKDIR /build

# Install grpcio-tools for stub generation
RUN pip install --no-cache-dir grpcio-tools==1.68.1

# Copy proto files
COPY k8s/src/rustic_ai/k8s/proto /build/proto
COPY k8s/scripts/generate_protos.sh /build/

# Generate gRPC stubs
RUN chmod +x /build/generate_protos.sh && \
    cd /build && \
    ./generate_protos.sh

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy generated gRPC stubs from builder
COPY --from=grpc-builder /build/proto /app/k8s/src/rustic_ai/k8s/proto

# Copy source code
COPY core /app/core
COPY k8s /app/k8s
COPY pyproject.toml /app/

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.5

# Configure Poetry to not create virtual environment (already in container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN cd /app && \
    poetry install --no-dev --no-root && \
    cd /app/core && \
    poetry install --no-dev && \
    cd /app/k8s && \
    poetry install --no-dev

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/core/src:/app/k8s/src \
    REDIS_URL=redis://redis:6379/0 \
    GRPC_PORT=50051 \
    MAX_PROCESSES=100 \
    HEARTBEAT_INTERVAL=20

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import grpc; \
        from rustic_ai.k8s.proto import agent_host_pb2, agent_host_pb2_grpc; \
        channel = grpc.insecure_channel('localhost:${GRPC_PORT}'); \
        stub = agent_host_pb2_grpc.AgentHostServiceStub(channel); \
        request = agent_host_pb2.HealthRequest(); \
        response = stub.Health(request, timeout=2); \
        exit(0 if response.healthy else 1)"

# Run as non-root user
RUN useradd -m -u 1000 rustic && \
    chown -R rustic:rustic /app

USER rustic

# Entry point
CMD ["python", "-m", "rustic_ai.k8s.agent_host.server"]
