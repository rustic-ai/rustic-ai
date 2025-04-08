#!/bin/bash

# Function to clean up the Uvicorn server process
cleanup() {
    echo "Cleaning up..."
    echo "Running in directory: $(pwd)"
    kill $UVICORN_PID 2>/dev/null || true
    wait $UVICORN_PID 2>/dev/null
    echo "Uvicorn server terminated."
    rm -f -- integration_testing_app.db
}

# Set trap to call cleanup function on script exit, interrupt, or termination
trap cleanup EXIT INT TERM

# Ensure any existing server is killed
pkill -f "uvicorn rustic_ai.api_server.main:app"

# Create a directory to store coverage data
rm -rf coverage
mkdir coverage

echo "Starting Uvicorn server..."
# Start Uvicorn in the background and redirect outputs
export OTEL_TRACES_EXPORTER=console
export OTEL_SERVICE_NAME=GuildCommunicationService
RUSTIC_METASTORE='sqlite:///integration_testing_app.db' opentelemetry-instrument coverage run --context=INTEGRATION --data-file=coverage/coverage-int -m rustic_ai.api_server.main > uvicorn_output.txt 2>&1 &
UVICORN_PID=$!

echo "Uvicorn server started with PID $UVICORN_PID."

# Wait for the server to start
sleep 5

echo "Running tests..."

# Run pytest directly with the desired parameters and pass all script arguments to pytest
PYTHONFAULTHANDLER=true coverage run --context=TESTS --data-file=coverage/coverage-tests -m pytest -vvvv --showlocals

# The trap set earlier ensures that the cleanup function is called when the script exits
