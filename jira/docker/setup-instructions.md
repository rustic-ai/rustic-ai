# Local JIRA Setup for Testing

This guide will help you set up a local JIRA instance using Docker for testing the JIRA connector.

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB of free RAM
- Port 8080 available on your machine

## Quick Start

1. **Start JIRA and PostgreSQL:**

```bash
cd jira/
docker-compose up -d
```

2. **Wait for JIRA to start:**

The first startup takes 3-5 minutes. Monitor the logs:

```bash
docker-compose logs -f jira
```

Wait until you see: `Server startup in [xxxxx] milliseconds`

3. **Access JIRA:**

Open your browser and go to: http://localhost:8080

## Initial Setup

### 1. Choose Setup Type

On first access, you'll see the JIRA setup wizard:

1. Select **"I'll set it up myself"**
2. Click **"Continue to MyAtlassian"** or skip if you don't have an Atlassian account

### 2. Database Configuration

1. Select **"My Own Database"**
2. Choose **"PostgreSQL"** as the database type
3. Enter the following connection details:
   - **Database Type:** PostgreSQL
   - **Hostname:** `postgres` (this is the container name)
   - **Port:** `5432`
   - **Database:** `jiradb`
   - **Username:** `jira`
   - **Password:** `jira`
4. Click **"Test Connection"** to verify
5. Click **"Next"**

### 3. Application Properties

1. **Application Title:** Enter any name (e.g., "Rustic AI Test")
2. **Mode:** Choose "Private"
3. **Base URL:** Use `http://localhost:8080`
4. Click **"Next"**

### 4. License

For testing purposes, you have two options:

**Option A: Generate a Trial License (Recommended)**
1. Click **"Generate a Jira trial license"**
2. Sign up/log in with an Atlassian account
3. The license will be automatically applied

**Option B: Use Existing License**
1. If you have a JIRA license, paste it here

### 5. Administrator Account

Create an admin account:
- **Full Name:** Admin User
- **Email:** admin@example.com
- **Username:** admin
- **Password:** admin123 (use a strong password in production!)

### 6. Email Notifications

You can skip this for local testing:
- Click **"Finish"**

### 7. Initial Project Setup

1. Choose a project template (e.g., "Scrum" or "Kanban")
2. Enter project details:
   - **Name:** Test Project
   - **Key:** TEST (this will be used in issue keys like TEST-1)
3. Click **"Submit"**

## Creating an API Token

To use the JIRA connector, you need either:

### Option 1: Personal Access Token (Recommended for JIRA Server/Data Center)

1. Log in as the admin user
2. Go to **Profile** (top right) → **Personal Access Tokens**
3. Click **"Create token"**
4. Enter a label (e.g., "Rustic AI Connector")
5. Copy the token and save it securely

Set the environment variable:
```bash
export JIRA_TOKEN="your-token-here"
```

### Option 2: Username + Password/API Token

For basic authentication:

```bash
export JIRA_USERNAME="admin"
export JIRA_PASSWORD="admin123"
```

## Testing the Connection

### Using Python

```python
import asyncio
from rustic_ai.jira import JiraAPIClient

async def test_connection():
    client = JiraAPIClient(
        server="http://localhost:8080",
        username="admin",
        password="admin123",
    )
    
    # List projects
    projects = await client.list_projects()
    print(f"Found {len(projects)} projects")
    
    # Create a test issue
    issue = await client.create_issue(
        project="TEST",
        summary="Test issue from Rustic AI",
        description="This is a test issue created via the JIRA connector",
        issuetype="Task",
    )
    print(f"Created issue: {issue['key']}")

asyncio.run(test_connection())
```

### Using the Connector Agent

```python
import asyncio
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.jira import JiraConnectorAgent, JiraCreateIssueRequest

async def test_agent():
    # Create agent spec
    agent_spec = (
        AgentBuilder(JiraConnectorAgent)
        .set_name("JiraAgent")
        .set_description("JIRA connector")
        .build_spec()
    )
    
    # Create guild
    guild = (
        GuildBuilder()
        .set_name("test_guild")
        .add_agent(agent_spec)
        .build()
    )
    
    # Start guild
    async with guild:
        # Create issue
        request = JiraCreateIssueRequest(
            project_key="TEST",
            summary="Issue from agent",
            description="Created via JiraConnectorAgent",
            issue_type="Task",
            instance_url="http://localhost:8080",
        )
        
        # Send request to agent
        # (Implementation depends on your guild setup)
        print("Request sent to agent")

asyncio.run(test_agent())
```

## Useful Docker Commands

### Stop JIRA
```bash
docker-compose down
```

### Stop and remove all data (fresh start)
```bash
docker-compose down -v
```

### View logs
```bash
docker-compose logs -f jira
docker-compose logs -f postgres
```

### Restart JIRA
```bash
docker-compose restart jira
```

## Troubleshooting

### JIRA won't start
- Check Docker has enough memory allocated (4GB minimum)
- Check logs: `docker-compose logs jira`
- Wait longer - first startup can take 5-10 minutes

### Database connection fails
- Ensure PostgreSQL container is running: `docker ps`
- Use `postgres` as hostname, not `localhost`
- Verify credentials match docker-compose.yml

### Port 8080 already in use
Edit `docker-compose.yml` and change:
```yaml
ports:
  - "8081:8080"  # Use port 8081 instead
```

Then update your JIRA URL to `http://localhost:8081`

### Out of memory errors
Increase JVM memory in `docker-compose.yml`:
```yaml
environment:
  - JVM_MINIMUM_MEMORY=4096m
  - JVM_MAXIMUM_MEMORY=8192m
```

## Accessing JIRA UI

- **URL:** http://localhost:8080
- **Username:** admin (or whatever you set)
- **Password:** admin123 (or whatever you set)

## Next Steps

1. Create test issues in the JIRA UI
2. Try the JIRA connector with various operations
3. Test JQL queries
4. Experiment with custom fields
5. Test attachments and comments

## Cleaning Up

When you're done testing:

```bash
# Stop containers
docker-compose down

# Remove all data (optional)
docker-compose down -v

# Remove images (optional)
docker rmi atlassian/jira-software:9.12
docker rmi postgres:14-alpine
```
