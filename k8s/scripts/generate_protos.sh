#!/bin/bash
set -e

# Generate gRPC Python stubs from protocol buffer definitions

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PROTO_DIR="$PROJECT_ROOT/src/rustic_ai/k8s/proto"
OUT_DIR="$PROJECT_ROOT/src/rustic_ai/k8s/proto"

echo "Generating gRPC stubs from protocol buffers..."
echo "Proto directory: $PROTO_DIR"
echo "Output directory: $OUT_DIR"

cd "$PROJECT_ROOT"

python -m grpc_tools.protoc \
  -I. \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  --pyi_out="$OUT_DIR" \
  "$PROTO_DIR/agent_host.proto"

echo "✓ Generated gRPC stubs successfully"
echo "  - ${OUT_DIR}/agent_host_pb2.py"
echo "  - ${OUT_DIR}/agent_host_pb2_grpc.py"
echo "  - ${OUT_DIR}/agent_host_pb2.pyi"
