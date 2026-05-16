"""Main JIRA connector agent for all JIRA API operations."""

import logging
import os
from typing import Dict

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.jira.client.api_client import JiraAPIClient
from rustic_ai.jira.models.attachments import (
    JiraAddAttachmentRequest,
    JiraAttachmentResponse,
    JiraDeleteAttachmentRequest,
    JiraGetAttachmentRequest,
)
from rustic_ai.jira.models.comments import (
    JiraAddCommentRequest,
    JiraCommentResponse,
    JiraDeleteCommentRequest,
    JiraGetCommentsRequest,
    JiraUpdateCommentRequest,
)
from rustic_ai.jira.models.issues import (
    JiraAssignIssueRequest,
    JiraCreateIssueRequest,
    JiraDeleteIssueRequest,
    JiraGetIssueRequest,
    JiraIssueResponse,
    JiraSearchIssuesRequest,
    JiraSearchIssuesResponse,
    JiraTransitionIssueRequest,
    JiraUpdateIssueRequest,
)
from rustic_ai.jira.models.projects import (
    JiraGetProjectRequest,
    JiraListProjectsRequest,
    JiraProjectResponse,
    JiraProjectsResponse,
)
from rustic_ai.jira.models.users import (
    JiraGetUserRequest,
    JiraSearchUsersRequest,
    JiraUserResponse,
    JiraUsersResponse,
)


class JiraConnectorAgent(Agent):
    """
    Main JIRA connector agent for bidirectional JIRA communication.

    Handles:
    - Issue management (create, update, get, delete, search, transition, assign)
    - Project operations (list, get)
    - Comment operations (add, get, update, delete)
    - User operations (get, search)
    - Attachment operations (add, get, delete)

    Configuration:
    - JIRA_USERNAME: Username for authentication (optional if using token)
    - JIRA_PASSWORD: Password/API token for authentication (optional if using token)
    - JIRA_TOKEN: Personal access token (alternative to username/password)
    """

    def __init__(self):
        self._clients: Dict[str, JiraAPIClient] = {}

    async def _get_client(self, instance_url: str) -> JiraAPIClient:
        """Get or create API client for JIRA instance."""
        if instance_url in self._clients:
            return self._clients[instance_url]

        logging.info(f"Creating JIRA API client for: {instance_url}")

        # Get credentials from environment
        token = os.getenv("JIRA_TOKEN")
        username = os.getenv("JIRA_USERNAME")
        password = os.getenv("JIRA_PASSWORD")

        if not token and not (username and password):
            raise ValueError(
                "JIRA credentials not found. Set either JIRA_TOKEN or both JIRA_USERNAME and JIRA_PASSWORD environment variables."
            )

        # Create API client
        client = JiraAPIClient(
            server=instance_url,
            username=username,
            password=password,
            token=token,
            requests_per_second=8.0,
            max_retries=3,
        )

        self._clients[instance_url] = client
        return client

    # Issue Operations

    @processor(clz=JiraCreateIssueRequest)
    async def create_issue(self, ctx: ProcessContext[JiraCreateIssueRequest]):
        """Create a new JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(
                f"Creating JIRA issue: project={request.project_key}, "
                f"type={request.issue_type}, summary={request.summary[:50]}..."
            )

            issue = await client.create_issue(
                project=request.project_key,
                summary=request.summary,
                description=request.description,
                issuetype=request.issue_type,
                priority=request.priority,
                assignee=request.assignee,
                labels=request.labels,
                components=request.components,
                **(request.custom_fields or {}),
            )

            ctx.send(
                JiraIssueResponse(
                    key=issue["key"],
                    id=issue["id"],
                    url=issue["url"],
                    fields=issue["fields"],
                    expand=issue.get("expand"),
                )
            )

        except ValueError as e:
            logging.error(f"Configuration error creating issue: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_CONFIGURATION_ERROR",
                    error_message=f"Configuration error: {str(e)}",
                )
            )
        except Exception as e:
            logging.error(f"Error creating issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_CREATE_ISSUE_ERROR",
                    error_message=f"Failed to create issue: {str(e)}",
                )
            )

    @processor(clz=JiraUpdateIssueRequest)
    async def update_issue(self, ctx: ProcessContext[JiraUpdateIssueRequest]):
        """Update an existing JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Updating JIRA issue: {request.issue_key}")

            issue = await client.update_issue(
                issue_key=request.issue_key,
                summary=request.summary,
                description=request.description,
                priority=request.priority,
                assignee=request.assignee,
                labels=request.labels,
                components=request.components,
                **(request.custom_fields or {}),
            )

            ctx.send(
                JiraIssueResponse(
                    key=issue["key"],
                    id=issue["id"],
                    url=issue["url"],
                    fields=issue["fields"],
                    expand=issue.get("expand"),
                )
            )

        except Exception as e:
            logging.error(f"Error updating issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_UPDATE_ISSUE_ERROR",
                    error_message=f"Failed to update issue: {str(e)}",
                )
            )

    @processor(clz=JiraGetIssueRequest)
    async def get_issue(self, ctx: ProcessContext[JiraGetIssueRequest]):
        """Get a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Getting JIRA issue: {request.issue_key}")

            issue = await client.get_issue(issue_key=request.issue_key, expand=request.expand)

            ctx.send(
                JiraIssueResponse(
                    key=issue["key"],
                    id=issue["id"],
                    url=issue["url"],
                    fields=issue["fields"],
                    expand=issue.get("expand"),
                )
            )

        except Exception as e:
            logging.error(f"Error getting issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_GET_ISSUE_ERROR",
                    error_message=f"Failed to get issue: {str(e)}",
                )
            )

    @processor(clz=JiraDeleteIssueRequest)
    async def delete_issue(self, ctx: ProcessContext[JiraDeleteIssueRequest]):
        """Delete a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Deleting JIRA issue: {request.issue_key}")

            await client.delete_issue(issue_key=request.issue_key, delete_subtasks=request.delete_subtasks)

            ctx.send({"success": True, "issue_key": request.issue_key})

        except Exception as e:
            logging.error(f"Error deleting issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_DELETE_ISSUE_ERROR",
                    error_message=f"Failed to delete issue: {str(e)}",
                )
            )

    @processor(clz=JiraSearchIssuesRequest)
    async def search_issues(self, ctx: ProcessContext[JiraSearchIssuesRequest]):
        """Search for JIRA issues using JQL."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Searching JIRA issues: {request.jql[:100]}...")

            results = await client.search_issues(
                jql=request.jql,
                max_results=request.max_results,
                start_at=request.start_at,
                fields=request.fields,
                expand=request.expand,
            )

            ctx.send(
                JiraSearchIssuesResponse(
                    total=results["total"],
                    max_results=results["max_results"],
                    start_at=results["start_at"],
                    issues=results["issues"],
                )
            )

        except Exception as e:
            logging.error(f"Error searching issues: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_SEARCH_ISSUES_ERROR",
                    error_message=f"Failed to search issues: {str(e)}",
                )
            )

    @processor(clz=JiraTransitionIssueRequest)
    async def transition_issue(self, ctx: ProcessContext[JiraTransitionIssueRequest]):
        """Transition a JIRA issue to a new status."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Transitioning JIRA issue {request.issue_key} to {request.transition_name}")

            await client.transition_issue(
                issue_key=request.issue_key,
                transition_name=request.transition_name,
                comment=request.comment,
                fields=request.fields,
            )

            ctx.send({"success": True, "issue_key": request.issue_key, "transition": request.transition_name})

        except Exception as e:
            logging.error(f"Error transitioning issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_TRANSITION_ISSUE_ERROR",
                    error_message=f"Failed to transition issue: {str(e)}",
                )
            )

    @processor(clz=JiraAssignIssueRequest)
    async def assign_issue(self, ctx: ProcessContext[JiraAssignIssueRequest]):
        """Assign a JIRA issue to a user."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Assigning JIRA issue {request.issue_key} to {request.assignee}")

            await client.assign_issue(issue_key=request.issue_key, assignee=request.assignee)

            ctx.send({"success": True, "issue_key": request.issue_key, "assignee": request.assignee})

        except Exception as e:
            logging.error(f"Error assigning issue: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_ASSIGN_ISSUE_ERROR",
                    error_message=f"Failed to assign issue: {str(e)}",
                )
            )

    # Project Operations

    @processor(clz=JiraListProjectsRequest)
    async def list_projects(self, ctx: ProcessContext[JiraListProjectsRequest]):
        """List all JIRA projects."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info("Listing JIRA projects")

            projects = await client.list_projects(expand=request.expand)

            ctx.send(JiraProjectsResponse(projects=projects, total=len(projects)))

        except ValueError as e:
            logging.error(f"Configuration error listing projects: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_CONFIGURATION_ERROR",
                    error_message=f"Configuration error: {str(e)}",
                )
            )
        except Exception as e:
            logging.error(f"Error listing projects: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_LIST_PROJECTS_ERROR",
                    error_message=f"Failed to list projects: {str(e)}",
                )
            )

    @processor(clz=JiraGetProjectRequest)
    async def get_project(self, ctx: ProcessContext[JiraGetProjectRequest]):
        """Get a JIRA project."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Getting JIRA project: {request.project_key}")

            project = await client.get_project(project_key=request.project_key, expand=request.expand)

            ctx.send(
                JiraProjectResponse(
                    key=project["key"],
                    id=project["id"],
                    name=project["name"],
                    description=project.get("description"),
                    lead=project.get("lead"),
                    url=project["url"],
                    project_type_key=project.get("project_type_key"),
                )
            )

        except Exception as e:
            logging.error(f"Error getting project: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_GET_PROJECT_ERROR",
                    error_message=f"Failed to get project: {str(e)}",
                )
            )

    # Comment Operations

    @processor(clz=JiraAddCommentRequest)
    async def add_comment(self, ctx: ProcessContext[JiraAddCommentRequest]):
        """Add a comment to a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Adding comment to JIRA issue: {request.issue_key}")

            comment = await client.add_comment(
                issue_key=request.issue_key, body=request.body, visibility=request.visibility
            )

            ctx.send(
                JiraCommentResponse(
                    id=comment["id"],
                    body=comment["body"],
                    author=comment["author"],
                    created=comment["created"],
                    updated=comment["updated"],
                )
            )

        except Exception as e:
            logging.error(f"Error adding comment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_ADD_COMMENT_ERROR",
                    error_message=f"Failed to add comment: {str(e)}",
                )
            )

    @processor(clz=JiraGetCommentsRequest)
    async def get_comments(self, ctx: ProcessContext[JiraGetCommentsRequest]):
        """Get comments for a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Getting comments for JIRA issue: {request.issue_key}")

            comments = await client.get_comments(
                issue_key=request.issue_key, start_at=request.start_at, max_results=request.max_results
            )

            ctx.send(JiraCommentResponse(comments=comments))

        except Exception as e:
            logging.error(f"Error getting comments: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_GET_COMMENTS_ERROR",
                    error_message=f"Failed to get comments: {str(e)}",
                )
            )

    @processor(clz=JiraUpdateCommentRequest)
    async def update_comment(self, ctx: ProcessContext[JiraUpdateCommentRequest]):
        """Update a comment on a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Updating comment {request.comment_id} on issue {request.issue_key}")

            comment = await client.update_comment(
                issue_key=request.issue_key,
                comment_id=request.comment_id,
                body=request.body,
                visibility=request.visibility,
            )

            ctx.send(
                JiraCommentResponse(
                    id=comment["id"],
                    body=comment["body"],
                    author=comment["author"],
                    created=comment["created"],
                    updated=comment["updated"],
                )
            )

        except Exception as e:
            logging.error(f"Error updating comment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_UPDATE_COMMENT_ERROR",
                    error_message=f"Failed to update comment: {str(e)}",
                )
            )

    @processor(clz=JiraDeleteCommentRequest)
    async def delete_comment(self, ctx: ProcessContext[JiraDeleteCommentRequest]):
        """Delete a comment from a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Deleting comment {request.comment_id} from issue {request.issue_key}")

            await client.delete_comment(issue_key=request.issue_key, comment_id=request.comment_id)

            ctx.send({"success": True, "comment_id": request.comment_id})

        except Exception as e:
            logging.error(f"Error deleting comment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_DELETE_COMMENT_ERROR",
                    error_message=f"Failed to delete comment: {str(e)}",
                )
            )

    # User Operations

    @processor(clz=JiraGetUserRequest)
    async def get_user(self, ctx: ProcessContext[JiraGetUserRequest]):
        """Get a JIRA user."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Getting JIRA user: username={request.username}, account_id={request.account_id}")

            user = await client.get_user(username=request.username, account_id=request.account_id)

            ctx.send(
                JiraUserResponse(
                    account_id=user.get("account_id"),
                    display_name=user["display_name"],
                    email_address=user.get("email_address"),
                    active=user["active"],
                    avatar_urls=user.get("avatar_urls"),
                )
            )

        except Exception as e:
            logging.error(f"Error getting user: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_GET_USER_ERROR",
                    error_message=f"Failed to get user: {str(e)}",
                )
            )

    @processor(clz=JiraSearchUsersRequest)
    async def search_users(self, ctx: ProcessContext[JiraSearchUsersRequest]):
        """Search for JIRA users."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Searching JIRA users: {request.query}")

            users = await client.search_users(
                query=request.query, max_results=request.max_results, start_at=request.start_at
            )

            ctx.send(JiraUsersResponse(users=users, total=len(users)))

        except Exception as e:
            logging.error(f"Error searching users: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_SEARCH_USERS_ERROR",
                    error_message=f"Failed to search users: {str(e)}",
                )
            )

    # Attachment Operations

    @processor(clz=JiraAddAttachmentRequest)
    async def add_attachment(self, ctx: ProcessContext[JiraAddAttachmentRequest]):
        """Add an attachment to a JIRA issue."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Adding attachment to JIRA issue: {request.issue_key}")

            attachment = await client.add_attachment(
                issue_key=request.issue_key, filename=request.filename, content=request.content
            )

            ctx.send(
                JiraAttachmentResponse(
                    id=attachment["id"],
                    filename=attachment["filename"],
                    author=attachment["author"],
                    created=attachment["created"],
                    size=attachment["size"],
                    mime_type=attachment["mime_type"],
                    content_url=attachment["content_url"],
                )
            )

        except Exception as e:
            logging.error(f"Error adding attachment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_ADD_ATTACHMENT_ERROR",
                    error_message=f"Failed to add attachment: {str(e)}",
                )
            )

    @processor(clz=JiraGetAttachmentRequest)
    async def get_attachment(self, ctx: ProcessContext[JiraGetAttachmentRequest]):
        """Get attachment metadata."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Getting attachment: {request.attachment_id}")

            attachment = await client.get_attachment(attachment_id=request.attachment_id)

            ctx.send(
                JiraAttachmentResponse(
                    id=attachment["id"],
                    filename=attachment["filename"],
                    author=attachment["author"],
                    created=attachment["created"],
                    size=attachment["size"],
                    mime_type=attachment["mime_type"],
                    content_url=attachment["content_url"],
                )
            )

        except Exception as e:
            logging.error(f"Error getting attachment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_GET_ATTACHMENT_ERROR",
                    error_message=f"Failed to get attachment: {str(e)}",
                )
            )

    @processor(clz=JiraDeleteAttachmentRequest)
    async def delete_attachment(self, ctx: ProcessContext[JiraDeleteAttachmentRequest]):
        """Delete an attachment."""
        try:
            request = ctx.payload
            client = await self._get_client(request.instance_url)

            logging.info(f"Deleting attachment: {request.attachment_id}")

            await client.delete_attachment(attachment_id=request.attachment_id)

            ctx.send({"success": True, "attachment_id": request.attachment_id})

        except Exception as e:
            logging.error(f"Error deleting attachment: {e}", exc_info=True)
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="JIRA_DELETE_ATTACHMENT_ERROR",
                    error_message=f"Failed to delete attachment: {str(e)}",
                )
            )
