#!/bin/bash

# Quick Start Script for JIRA Connector Testing

set -e

echo "====================================="
echo "JIRA Connector Quick Start"
echo "====================================="
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker first."
    exit 1
fi

# Start JIRA and PostgreSQL
echo "Step 1: Starting JIRA and PostgreSQL containers..."
docker compose up -d

echo
echo "Containers started! Waiting for JIRA to initialize..."
echo "This may take 3-5 minutes on first startup..."
echo

# Wait for JIRA to be ready
echo "Monitoring JIRA startup (press Ctrl+C to skip monitoring)..."
docker compose logs -f jira &
LOGS_PID=$!

# Wait for up to 10 minutes
for i in {1..60}; do
    if docker compose logs jira 2>&1 | grep -q "Server startup in"; then
        echo
        echo "✅ JIRA is ready!"
        kill $LOGS_PID 2>/dev/null || true
        break
    fi
    sleep 10
    if [ $i -eq 60 ]; then
        echo
        echo "⚠️  JIRA startup taking longer than expected."
        echo "Check logs with: docker-compose logs -f jira"
        kill $LOGS_PID 2>/dev/null || true
    fi
done

echo
echo "====================================="
echo "Next Steps:"
echo "====================================="
echo
echo "1. Open your browser and go to:"
echo "   http://localhost:8080"
echo
echo "2. Follow the setup wizard:"
echo "   - Choose 'I'll set it up myself'"
echo "   - Select PostgreSQL database with these settings:"
echo "     Hostname: postgres"
echo "     Port: 5432"
echo "     Database: jiradb"
echo "     Username: jira"
echo "     Password: jira"
echo
echo "3. Create an admin account (remember these credentials!)"
echo
echo "4. Set up environment variables:"
echo "   export JIRA_USERNAME='admin'"
echo "   export JIRA_PASSWORD='your-password'"
echo "   export JIRA_INSTANCE_URL='http://localhost:8080'"
echo
echo "5. Create a test project with key 'TEST'"
echo
echo "6. Run the example:"
echo "   poetry run python examples/basic_usage.py"
echo
echo "====================================="
echo "Useful Commands:"
echo "====================================="
echo "  Stop JIRA:           docker-compose down"
echo "  View logs:           docker-compose logs -f jira"
echo "  Fresh restart:       docker-compose down -v && docker-compose up -d"
echo "  JIRA UI:             http://localhost:8080"
echo "====================================="
echo
echo "For detailed setup instructions, see:"
echo "  docker/setup-instructions.md"
echo
