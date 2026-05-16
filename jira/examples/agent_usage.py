"""Example of using the JIRA connector agent in a guild."""

import asyncio
import os

from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.jira import (
    JiraConnectorAgent,
    JiraCreateIssueRequest,
    JiraGetIssueRequest,
    JiraSearchIssuesRequest,
)


async def example_agent_usage():
    """Example of using JiraConnectorAgent in a guild."""
    print("=== JIRA Connector Agent Example ===\n")

    # Create JIRA agent spec
    jira_agent_spec = (
        AgentBuilder(JiraConnectorAgent)
        .set_name("JiraAgent")
        .set_description("JIRA connector for issue management")
        .build_spec()
    )

    # Create guild with JIRA agent
    guild = GuildBuilder().set_name("jira_guild").add_agent(jira_agent_spec).build()

    instance_url = os.getenv("JIRA_INSTANCE_URL", "http://localhost:8080")

    print("Starting guild...")
    async with guild:
        print("Guild started successfully!\n")

        # Example 1: Create an issue
        print("1. Creating a JIRA issue via agent...")
        create_request = JiraCreateIssueRequest(
            project_key="TEST",  # Change to your project key
            summary="Issue created by JiraConnectorAgent",
            description="This issue was created through the Rustic AI guild system",
            issue_type="Task",
            priority="Medium",
            labels=["automated", "rustic-ai"],
            instance_url=instance_url,
        )

        # In a real guild setup, you would send this message to the agent
        # and listen for the response. Here's the conceptual flow:
        # guild.send_message(create_request)
        # response = await guild.wait_for_response(JiraIssueResponse)
        # print(f"   Created issue: {response.key}")

        print("   (Request prepared - in full guild, this would be sent and processed)")

        # Example 2: Search for issues
        print("\n2. Searching for issues via agent...")
        search_request = JiraSearchIssuesRequest(
            jql="project = TEST AND created >= -7d",
            max_results=10,
            instance_url=instance_url,
        )
        print("   (Search request prepared)")

        # Example 3: Get specific issue
        print("\n3. Getting specific issue via agent...")
        get_request = JiraGetIssueRequest(
            issue_key="TEST-1",  # Change to an existing issue key
            expand=["changelog"],
            instance_url=instance_url,
        )
        print("   (Get request prepared)")

        print("\n=== Agent example completed ===")
        print("\nNote: In a full guild implementation, these requests would be")
        print("sent to the agent via the messaging system and responses would")
        print("be received asynchronously through the guild's message bus.")


if __name__ == "__main__":
    asyncio.run(example_agent_usage())
