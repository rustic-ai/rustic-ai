# Rustic AI JIRA Connector

A production-ready JIRA data connector for the Rustic AI framework, enabling bidirectional integration with JIRA for issue management, project operations, comments, users, and attachments.

## Features

- **Comprehensive Issue Operations**
  - Create, read, update, and delete issues
  - Search issues using JQL (JIRA Query Language)
  - Transition issues between statuses
  - Assign/unassign issues

- **Project Management**
  - List all accessible projects
  - Get detailed project information

- **Comment Operations**
  - Add, update, and delete comments
  - Retrieve comment history
  - Support for visibility restrictions

- **User Management**
  - Get user information
  - Search for users

- **Attachment Handling**
  - Upload attachments to issues
  - Get attachment metadata
  - Delete attachments

- **Production-Ready Features**
  - Automatic retry with exponential backoff
  - Rate limiting to prevent API throttling
  - Async/await support
  - Comprehensive error handling
  - Logging and monitoring

## Installation

```bash
cd jira
poetry install --with dev --all-extras
```

## Configuration

The JIRA connector requires authentication credentials. You can use either:

### Option 1: Personal Access Token (Recommended)

```bash
export JIRA_TOKEN="your-personal-access-token"
```

### Option 2: Username and Password/API Token

```bash
export JIRA_USERNAME="your-username"
export JIRA_PASSWORD="your-password-or-api-token"
```

## Quick Start

### Using the API Client Directly

```python
import asyncio
from rustic_ai.jira import JiraAPIClient

async def main():
    # Initialize client
    client = JiraAPIClient(
        server="https://your-domain.atlassian.net",
        token="your-token",  # or use username/password
    )
    
    # Create an issue
    issue = await client.create_issue(
        project="PROJ",
        summary="New feature request",
        description="Detailed description here",
        issuetype="Task",
        priority="High",
    )
    print(f"Created issue: {issue['key']}")
    
    # Search for issues
    results = await client.search_issues(
        jql="project = PROJ AND status = Open",
        max_results=10,
    )
    print(f"Found {results['total']} issues")
    
    # Add a comment
    comment = await client.add_comment(
        issue_key="PROJ-123",
        body="This is a comment from Rustic AI",
    )
    print(f"Added comment: {comment['id']}")

asyncio.run(main())
```

### Using the Connector Agent in a Guild

```python
import asyncio
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.jira import (
    JiraConnectorAgent,
    JiraCreateIssueRequest,
    JiraSearchIssuesRequest,
)

async def main():
    # Create JIRA agent spec
    jira_agent = (
        AgentBuilder(JiraConnectorAgent)
        .set_name("JiraAgent")
        .set_description("JIRA connector for issue management")
        .build_spec()
    )
    
    # Create guild with JIRA agent
    guild = (
        GuildBuilder()
        .set_name("jira_guild")
        .add_agent(jira_agent)
        .build()
    )
    
    # Start guild
    async with guild:
        # Create an issue by sending a request
        create_request = JiraCreateIssueRequest(
            project_key="PROJ",
            summary="Issue from Rustic AI Guild",
            description="This issue was created via the guild system",
            issue_type="Task",
            priority="Medium",
            instance_url="https://your-domain.atlassian.net",
        )
        
        # The agent will process this request and create the issue
        # Response will be JiraIssueResponse
        
        # Search for issues
        search_request = JiraSearchIssuesRequest(
            jql="project = PROJ AND created >= -7d",
            max_results=20,
            instance_url="https://your-domain.atlassian.net",
        )
        # Response will be JiraSearchIssuesResponse

asyncio.run(main())
```

## API Reference

### Issue Operations

#### Create Issue
```python
from rustic_ai.jira import JiraCreateIssueRequest

request = JiraCreateIssueRequest(
    project_key="PROJ",
    summary="Issue title",
    description="Detailed description",
    issue_type="Task",  # Bug, Story, Epic, etc.
    priority="High",  # High, Medium, Low
    assignee="username",
    labels=["backend", "urgent"],
    components=["API", "Database"],
    custom_fields={"customfield_10001": "value"},
    instance_url="https://your-domain.atlassian.net",
)
```

#### Update Issue
```python
from rustic_ai.jira import JiraUpdateIssueRequest

request = JiraUpdateIssueRequest(
    issue_key="PROJ-123",
    summary="Updated title",
    description="Updated description",
    priority="Low",
    instance_url="https://your-domain.atlassian.net",
)
```

#### Get Issue
```python
from rustic_ai.jira import JiraGetIssueRequest

request = JiraGetIssueRequest(
    issue_key="PROJ-123",
    expand=["changelog", "renderedFields"],
    instance_url="https://your-domain.atlassian.net",
)
```

#### Search Issues (JQL)
```python
from rustic_ai.jira import JiraSearchIssuesRequest

request = JiraSearchIssuesRequest(
    jql="project = PROJ AND status IN (Open, 'In Progress') AND assignee = currentUser()",
    max_results=50,
    start_at=0,
    fields=["summary", "status", "assignee"],
    instance_url="https://your-domain.atlassian.net",
)
```

#### Transition Issue
```python
from rustic_ai.jira import JiraTransitionIssueRequest

request = JiraTransitionIssueRequest(
    issue_key="PROJ-123",
    transition_name="Done",
    comment="Completed the task",
    instance_url="https://your-domain.atlassian.net",
)
```

#### Assign Issue
```python
from rustic_ai.jira import JiraAssignIssueRequest

request = JiraAssignIssueRequest(
    issue_key="PROJ-123",
    assignee="username",  # or None to unassign
    instance_url="https://your-domain.atlassian.net",
)
```

### Project Operations

#### List Projects
```python
from rustic_ai.jira import JiraListProjectsRequest

request = JiraListProjectsRequest(
    expand=["description", "lead"],
    instance_url="https://your-domain.atlassian.net",
)
```

#### Get Project
```python
from rustic_ai.jira import JiraGetProjectRequest

request = JiraGetProjectRequest(
    project_key="PROJ",
    instance_url="https://your-domain.atlassian.net",
)
```

### Comment Operations

#### Add Comment
```python
from rustic_ai.jira import JiraAddCommentRequest

request = JiraAddCommentRequest(
    issue_key="PROJ-123",
    body="This is a comment",
    visibility={"type": "role", "value": "Administrators"},  # Optional
    instance_url="https://your-domain.atlassian.net",
)
```

#### Get Comments
```python
from rustic_ai.jira import JiraGetCommentsRequest

request = JiraGetCommentsRequest(
    issue_key="PROJ-123",
    start_at=0,
    max_results=50,
    instance_url="https://your-domain.atlassian.net",
)
```

### User Operations

#### Get User
```python
from rustic_ai.jira import JiraGetUserRequest

request = JiraGetUserRequest(
    account_id="557058:12345678-1234-1234-1234-123456789012",  # For Cloud
    # OR
    username="jsmith",  # For Server/Data Center
    instance_url="https://your-domain.atlassian.net",
)
```

#### Search Users
```python
from rustic_ai.jira import JiraSearchUsersRequest

request = JiraSearchUsersRequest(
    query="john",
    max_results=50,
    instance_url="https://your-domain.atlassian.net",
)
```

### Attachment Operations

#### Add Attachment
```python
from rustic_ai.jira import JiraAddAttachmentRequest

with open("document.pdf", "rb") as f:
    content = f.read()

request = JiraAddAttachmentRequest(
    issue_key="PROJ-123",
    filename="document.pdf",
    content=content,
    instance_url="https://your-domain.atlassian.net",
)
```

## Testing

### Running Tests

```bash
poetry run tox
```

### Local JIRA Instance for Testing

The module includes a Docker Compose setup for running a local JIRA instance:

```bash
cd jira
docker-compose up -d
```

See [docker/setup-instructions.md](docker/setup-instructions.md) for detailed setup instructions.

## JQL (JIRA Query Language) Examples

```python
# Issues assigned to current user
jql = "assignee = currentUser()"

# Open bugs in a project
jql = "project = PROJ AND status = Open AND type = Bug"

# Issues created in the last 7 days
jql = "created >= -7d"

# High priority issues due this week
jql = "priority = High AND due >= startOfWeek() AND due <= endOfWeek()"

# Issues with specific labels
jql = "labels IN (backend, critical)"

# Complex query
jql = """
    project = PROJ AND 
    status IN ('In Progress', 'Code Review') AND 
    assignee IN (membersOf('developers')) AND
    created >= -14d
"""
```

## Architecture

The JIRA connector follows Rustic AI patterns:

- **Models** (`models/`): Pydantic models for type-safe request/response payloads
- **Client** (`client/`): API client wrapper with retry logic, rate limiting, and async support
- **Agents** (`agents/`): Connector agent with `@processor` decorators for message handling

### Rate Limiting

The connector includes automatic rate limiting to prevent API throttling:
- Default: 8 requests/second (configurable)
- Automatic backoff on 429 responses
- Per-endpoint rate tracking

### Error Handling

All operations include comprehensive error handling:
- Automatic retry with exponential backoff
- Specific error types for different failures
- Detailed error messages with context
- Logging at appropriate levels

## Best Practices

1. **Use JQL Efficiently**: Limit result sets and use appropriate fields
2. **Batch Operations**: Group related operations when possible
3. **Handle Rate Limits**: Monitor for rate limit errors and adjust request frequency
4. **Secure Credentials**: Use environment variables or secret management
5. **Log Appropriately**: Use INFO for operations, ERROR for failures
6. **Test Locally**: Use the Docker setup for development and testing

## Troubleshooting

### Authentication Errors

- Verify credentials are correctly set in environment variables
- For JIRA Cloud, ensure you're using an API token, not password
- Check user has appropriate permissions

### Rate Limiting

- Reduce `requests_per_second` in JiraAPIClient initialization
- Implement delays between bulk operations
- Use pagination for large result sets

### Connection Issues

- Verify JIRA instance URL is correct
- Check network connectivity
- Ensure JIRA instance is accessible from your environment

## Contributing

When adding new features:

1. Add models to appropriate file in `models/`
2. Implement client methods in `api_client.py`
3. Add processor to `connector_agent.py`
4. Write tests in `tests/`
5. Update this README

## License

Apache-2.0

## Links

- [JIRA REST API Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [JQL Documentation](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [Rustic AI Documentation](https://www.rustic.ai/)
