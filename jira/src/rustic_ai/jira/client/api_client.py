"""JIRA API client wrapper."""

import asyncio
import io
import logging
from typing import Any, Dict, List, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jira import JIRA
from jira.exceptions import JIRAError
from rustic_ai.jira.client.rate_limiter import JiraRateLimiter


class JiraAPIClient:
    """
    Wrapper around jira-python library with rate limiting, retry logic, and async support.

    Provides production-ready error handling, automatic retries, and rate limiting
    to prevent API throttling.
    """

    def __init__(
        self,
        server: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        requests_per_second: float = 8.0,
        max_retries: int = 3,
    ):
        """
        Initialize JIRA API client.

        Args:
            server: JIRA server URL (e.g., 'https://your-domain.atlassian.net')
            username: Username for basic auth (optional)
            password: Password/API token for basic auth (optional)
            token: Personal access token (alternative to username/password)
            requests_per_second: Rate limit (default 8 to stay under typical 10/sec limit)
            max_retries: Maximum retry attempts for failed requests
        """
        self.server = server
        self.max_retries = max_retries
        self.rate_limiter = JiraRateLimiter(requests_per_second=requests_per_second)

        # Initialize JIRA client
        auth_options = {"server": server}

        if token:
            auth_options["token_auth"] = token
        elif username and password:
            auth_options["basic_auth"] = (username, password)
        else:
            raise ValueError("Either token or username/password must be provided")

        try:
            self.client = JIRA(**auth_options)
            logging.info(f"Connected to JIRA at {server}")
        except JIRAError as e:
            logging.error(f"Failed to connect to JIRA: {e}")
            raise

    @retry(
        retry=retry_if_exception_type(JIRAError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _make_request(self, func, *args, **kwargs) -> Any:
        """
        Make rate-limited API request with retry logic.

        Args:
            func: JIRA client method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Result from the JIRA API call
        """
        await self.rate_limiter.acquire("jira_api")

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            return result
        except JIRAError as e:
            if e.status_code == 429:  # Rate limited
                retry_after = int(e.response.headers.get("Retry-After", 60))
                self.rate_limiter.handle_rate_limit_error("jira_api", retry_after)
                await asyncio.sleep(retry_after)
                raise
            logging.error(f"JIRA API error: {e.status_code} - {e.text}")
            raise

    # Issue Operations

    async def create_issue(
        self,
        project: str,
        summary: str,
        description: Optional[str] = None,
        issuetype: str = "Task",
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
        **custom_fields,
    ) -> Dict[str, Any]:
        """Create a new JIRA issue."""
        fields: Dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issuetype},
        }

        if description:
            fields["description"] = description
        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            fields["assignee"] = {"name": assignee}
        if labels:
            fields["labels"] = labels
        if components:
            fields["components"] = [{"name": comp} for comp in components]

        # Add custom fields
        fields.update(custom_fields)

        issue = await self._make_request(self.client.create_issue, fields=fields)
        return self._issue_to_dict(issue)

    async def update_issue(
        self,
        issue_key: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
        **custom_fields,
    ) -> Dict[str, Any]:
        """Update an existing JIRA issue."""
        issue = await self._make_request(self.client.issue, issue_key)

        fields: Dict[str, Any] = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = description
        if priority:
            fields["priority"] = {"name": priority}
        if assignee:
            fields["assignee"] = {"name": assignee}
        if labels is not None:
            fields["labels"] = labels
        if components is not None:
            fields["components"] = [{"name": comp} for comp in components]

        fields.update(custom_fields)

        await self._make_request(issue.update, fields=fields)
        updated_issue = await self._make_request(self.client.issue, issue_key)
        return self._issue_to_dict(updated_issue)

    async def get_issue(self, issue_key: str, expand: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get a JIRA issue by key."""
        expand_str = ",".join(expand) if expand else None
        issue = await self._make_request(self.client.issue, issue_key, expand=expand_str)
        return self._issue_to_dict(issue)

    async def delete_issue(self, issue_key: str, delete_subtasks: bool = False) -> None:
        """Delete a JIRA issue."""
        await self._make_request(self.client.delete_issue, issue_key, deleteSubtasks=delete_subtasks)

    async def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: Optional[List[str]] = None,
        expand: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Search for issues using JQL."""
        fields_str = ",".join(fields) if fields else None
        expand_str = ",".join(expand) if expand else None

        results = await self._make_request(
            self.client.search_issues,
            jql,
            maxResults=max_results,
            startAt=start_at,
            fields=fields_str,
            expand=expand_str,
        )

        return {
            "total": results.total,
            "max_results": results.maxResults,
            "start_at": results.startAt,
            "issues": [self._issue_to_dict(issue) for issue in results],
        }

    async def transition_issue(
        self,
        issue_key: str,
        transition_name: str,
        comment: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Transition an issue to a new status."""
        issue = await self._make_request(self.client.issue, issue_key)
        transitions = await self._make_request(self.client.transitions, issue)

        transition_id = None
        for t in transitions:
            if t["name"].lower() == transition_name.lower():
                transition_id = t["id"]
                break

        if not transition_id:
            available = [t["name"] for t in transitions]
            raise ValueError(f"Transition '{transition_name}' not found. Available: {available}")

        transition_fields = fields or {}
        if comment:
            transition_fields["comment"] = [{"add": {"body": comment}}]

        await self._make_request(self.client.transition_issue, issue, transition_id, fields=transition_fields)

    async def assign_issue(self, issue_key: str, assignee: Optional[str]) -> None:
        """Assign an issue to a user (None to unassign)."""
        issue = await self._make_request(self.client.issue, issue_key)
        await self._make_request(self.client.assign_issue, issue, assignee)

    # Project Operations

    async def list_projects(self, expand: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """List all accessible projects."""
        expand_str = ",".join(expand) if expand else None
        projects = await self._make_request(self.client.projects, expand=expand_str)
        return [self._project_to_dict(proj) for proj in projects]

    async def get_project(self, project_key: str, expand: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get project details."""
        expand_str = ",".join(expand) if expand else None
        project = await self._make_request(self.client.project, project_key, expand=expand_str)
        return self._project_to_dict(project)

    # Comment Operations

    async def add_comment(
        self, issue_key: str, body: str, visibility: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Add a comment to an issue."""
        issue = await self._make_request(self.client.issue, issue_key)
        comment = await self._make_request(self.client.add_comment, issue, body, visibility=visibility)
        return self._comment_to_dict(comment)

    async def get_comments(self, issue_key: str, start_at: int = 0, max_results: int = 50) -> List[Dict[str, Any]]:
        """Get comments for an issue."""
        issue = await self._make_request(self.client.issue, issue_key)
        comments = await self._make_request(self.client.comments, issue, startAt=start_at, maxResults=max_results)
        return [self._comment_to_dict(c) for c in comments]

    async def update_comment(
        self, issue_key: str, comment_id: str, body: str, visibility: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Update a comment."""
        comment = await self._make_request(self.client.comment, issue_key, comment_id)
        comment.update(body=body, visibility=visibility)
        return self._comment_to_dict(comment)

    async def delete_comment(self, issue_key: str, comment_id: str) -> None:
        """Delete a comment."""
        comment = await self._make_request(self.client.comment, issue_key, comment_id)
        await self._make_request(comment.delete)

    # User Operations

    async def get_user(self, username: Optional[str] = None, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Get user information."""
        if account_id:
            user = await self._make_request(self.client.user, account_id)
        elif username:
            user = await self._make_request(self.client.user, username)
        else:
            raise ValueError("Either username or account_id must be provided")

        return self._user_to_dict(user)

    async def search_users(self, query: str, max_results: int = 50, start_at: int = 0) -> List[Dict[str, Any]]:
        """Search for users."""
        users = await self._make_request(self.client.search_users, query, maxResults=max_results, startAt=start_at)
        return [self._user_to_dict(u) for u in users]

    # Attachment Operations

    async def add_attachment(self, issue_key: str, filename: str, content: bytes) -> Dict[str, Any]:
        """Add an attachment to an issue."""
        issue = await self._make_request(self.client.issue, issue_key)
        file_obj = io.BytesIO(content)
        attachment = await self._make_request(self.client.add_attachment, issue, attachment=file_obj, filename=filename)

        if isinstance(attachment, list) and len(attachment) > 0:
            return self._attachment_to_dict(attachment[0])
        return self._attachment_to_dict(attachment)

    async def get_attachment(self, attachment_id: str) -> Dict[str, Any]:
        """Get attachment metadata."""
        attachment = await self._make_request(self.client.attachment, attachment_id)
        return self._attachment_to_dict(attachment)

    async def delete_attachment(self, attachment_id: str) -> None:
        """Delete an attachment."""
        attachment = await self._make_request(self.client.attachment, attachment_id)
        await self._make_request(attachment.delete)

    # Helper methods to convert JIRA objects to dicts

    def _issue_to_dict(self, issue) -> Dict[str, Any]:
        """Convert JIRA issue object to dictionary."""
        return {
            "key": issue.key,
            "id": issue.id,
            "url": f"{self.server}/browse/{issue.key}",
            "fields": issue.raw.get("fields", {}),
            "expand": issue.raw.get("expand"),
        }

    def _project_to_dict(self, project) -> Dict[str, Any]:
        """Convert JIRA project object to dictionary."""
        return {
            "key": project.key,
            "id": project.id,
            "name": project.name,
            "description": getattr(project, "description", None),
            "lead": getattr(project, "lead", None),
            "url": f"{self.server}/browse/{project.key}",
            "project_type_key": getattr(project, "projectTypeKey", None),
        }

    def _comment_to_dict(self, comment) -> Dict[str, Any]:
        """Convert JIRA comment object to dictionary."""
        return {
            "id": comment.id,
            "body": comment.body,
            "author": comment.author.raw if hasattr(comment, "author") else {},
            "created": comment.created,
            "updated": comment.updated,
        }

    def _user_to_dict(self, user) -> Dict[str, Any]:
        """Convert JIRA user object to dictionary."""
        return {
            "account_id": getattr(user, "accountId", None),
            "display_name": user.displayName,
            "email_address": getattr(user, "emailAddress", None),
            "active": user.active,
            "avatar_urls": getattr(user, "avatarUrls", {}),
        }

    def _attachment_to_dict(self, attachment) -> Dict[str, Any]:
        """Convert JIRA attachment object to dictionary."""
        return {
            "id": attachment.id,
            "filename": attachment.filename,
            "author": attachment.author.raw if hasattr(attachment, "author") else {},
            "created": attachment.created,
            "size": attachment.size,
            "mime_type": attachment.mimeType,
            "content_url": attachment.content,
        }
