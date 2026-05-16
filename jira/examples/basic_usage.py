"""Basic usage examples for the JIRA connector."""

import asyncio
import os

from rustic_ai.jira import JiraAPIClient


async def example_basic_operations():
    """Example of basic JIRA operations using the API client."""
    client = JiraAPIClient(
        server=os.getenv("JIRA_INSTANCE_URL", "http://localhost:8080"),
        username=os.getenv("JIRA_USERNAME"),
        password=os.getenv("JIRA_PASSWORD"),
        token=os.getenv("JIRA_TOKEN"),
    )

    print("=== JIRA Connector Basic Usage ===\n")

    # List all projects
    print("1. Listing all projects...")
    projects = await client.list_projects()
    for project in projects:
        print(f"   - {project['key']}: {project['name']}")

    if not projects:
        print("   No projects found. Please create a project in JIRA first.")
        return

    # Use the first project for examples
    project_key = projects[0]["key"]
    print(f"\n2. Using project: {project_key}")

    # Create an issue
    print(f"\n3. Creating a new issue in {project_key}...")
    issue = await client.create_issue(
        project=project_key,
        summary="Test issue from Rustic AI",
        description="This is a test issue created using the JIRA connector",
        issuetype="Task",
        priority="Medium",
    )
    print(f"   Created issue: {issue['key']}")
    print(f"   URL: {issue['url']}")
    issue_key = issue["key"]

    # Get the issue
    print(f"\n4. Retrieving issue {issue_key}...")
    retrieved_issue = await client.get_issue(issue_key)
    print(f"   Summary: {retrieved_issue['fields'].get('summary')}")
    print(f"   Status: {retrieved_issue['fields'].get('status', {}).get('name')}")

    # Update the issue
    print(f"\n5. Updating issue {issue_key}...")
    updated_issue = await client.update_issue(
        issue_key=issue_key,
        description="Updated description via Rustic AI JIRA connector",
        priority="High",
    )
    print(f"   Updated priority to: {updated_issue['fields'].get('priority', {}).get('name')}")

    # Add a comment
    print(f"\n6. Adding a comment to {issue_key}...")
    comment = await client.add_comment(
        issue_key=issue_key,
        body="This comment was added programmatically via the JIRA connector!",
    )
    print(f"   Comment ID: {comment['id']}")

    # Get all comments
    print(f"\n7. Retrieving all comments for {issue_key}...")
    comments = await client.get_comments(issue_key)
    print(f"   Total comments: {len(comments)}")
    for c in comments:
        print(f"   - {c['author'].get('displayName', 'Unknown')}: {c['body'][:50]}...")

    # Search for issues
    print(f"\n8. Searching for issues in {project_key}...")
    search_results = await client.search_issues(
        jql=f"project = {project_key} AND created >= -7d",
        max_results=10,
    )
    print(f"   Found {search_results['total']} issues created in the last 7 days")
    for issue_data in search_results["issues"]:
        print(f"   - {issue_data['key']}: {issue_data['fields'].get('summary')}")

    # Search for users
    print("\n9. Searching for users...")
    users = await client.search_users(query="admin", max_results=5)
    print(f"   Found {len(users)} users")
    for user in users:
        print(f"   - {user['display_name']} ({user.get('email_address', 'no email')})")

    print("\n=== All operations completed successfully! ===")


async def example_issue_transitions():
    """Example of transitioning an issue through different statuses."""
    client = JiraAPIClient(
        server=os.getenv("JIRA_INSTANCE_URL", "http://localhost:8080"),
        username=os.getenv("JIRA_USERNAME"),
        password=os.getenv("JIRA_PASSWORD"),
        token=os.getenv("JIRA_TOKEN"),
    )

    print("\n=== Issue Transition Example ===\n")

    # Get the first project
    projects = await client.list_projects()
    if not projects:
        print("No projects found.")
        return

    project_key = projects[0]["key"]

    # Create an issue
    issue = await client.create_issue(
        project=project_key,
        summary="Issue for transition testing",
        description="This issue will be transitioned through different statuses",
        issuetype="Task",
    )
    issue_key = issue["key"]
    print(f"Created issue: {issue_key}")

    # Get current status
    current_issue = await client.get_issue(issue_key)
    current_status = current_issue["fields"]["status"]["name"]
    print(f"Current status: {current_status}")

    # Note: Transition names depend on your workflow
    # Common transitions: "To Do", "In Progress", "Done"
    # Uncomment and modify based on your JIRA workflow:

    # try:
    #     print("\nTransitioning to 'In Progress'...")
    #     await client.transition_issue(
    #         issue_key=issue_key,
    #         transition_name="In Progress",
    #         comment="Starting work on this issue",
    #     )
    #     print("Transitioned successfully!")
    # except Exception as e:
    #     print(f"Transition failed: {e}")
    #     print("Check your workflow and available transitions in JIRA")


async def example_attachments():
    """Example of working with attachments."""
    client = JiraAPIClient(
        server=os.getenv("JIRA_INSTANCE_URL", "http://localhost:8080"),
        username=os.getenv("JIRA_USERNAME"),
        password=os.getenv("JIRA_PASSWORD"),
        token=os.getenv("JIRA_TOKEN"),
    )

    print("\n=== Attachment Example ===\n")

    # Get the first project
    projects = await client.list_projects()
    if not projects:
        print("No projects found.")
        return

    project_key = projects[0]["key"]

    # Create an issue
    issue = await client.create_issue(
        project=project_key,
        summary="Issue with attachment",
        description="This issue will have an attachment",
        issuetype="Task",
    )
    issue_key = issue["key"]
    print(f"Created issue: {issue_key}")

    # Create a simple text file to attach
    file_content = b"This is a test file created by the JIRA connector.\n\nIt demonstrates attachment functionality."

    print("\nAdding attachment...")
    attachment = await client.add_attachment(
        issue_key=issue_key,
        filename="test_file.txt",
        content=file_content,
    )
    print(f"Attachment added: {attachment['filename']}")
    print(f"Size: {attachment['size']} bytes")
    print(f"Download URL: {attachment['content_url']}")


if __name__ == "__main__":
    # Run the basic operations example
    asyncio.run(example_basic_operations())

    # Uncomment to run other examples:
    # asyncio.run(example_issue_transitions())
    # asyncio.run(example_attachments())
