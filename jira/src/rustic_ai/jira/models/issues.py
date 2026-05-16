"""JIRA issue models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JiraCreateIssueRequest(BaseModel):
    """Request to create a new JIRA issue."""

    project_key: str = Field(..., description="Project key (e.g., 'PROJ')")
    summary: str = Field(..., description="Issue summary/title")
    description: Optional[str] = Field(None, description="Issue description")
    issue_type: str = Field(default="Task", description="Issue type (e.g., 'Bug', 'Task', 'Story')")
    priority: Optional[str] = Field(None, description="Priority (e.g., 'High', 'Medium', 'Low')")
    assignee: Optional[str] = Field(None, description="Assignee username or account ID")
    labels: Optional[List[str]] = Field(None, description="List of labels")
    components: Optional[List[str]] = Field(None, description="List of component names")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom field values")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraUpdateIssueRequest(BaseModel):
    """Request to update an existing JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    summary: Optional[str] = Field(None, description="Updated summary")
    description: Optional[str] = Field(None, description="Updated description")
    priority: Optional[str] = Field(None, description="Updated priority")
    assignee: Optional[str] = Field(None, description="Updated assignee")
    labels: Optional[List[str]] = Field(None, description="Updated labels")
    components: Optional[List[str]] = Field(None, description="Updated components")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Updated custom fields")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraGetIssueRequest(BaseModel):
    """Request to get a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    expand: Optional[List[str]] = Field(
        None, description="List of fields to expand (e.g., ['changelog', 'renderedFields'])"
    )
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraDeleteIssueRequest(BaseModel):
    """Request to delete a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    delete_subtasks: bool = Field(default=False, description="Delete subtasks if they exist")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraSearchIssuesRequest(BaseModel):
    """Request to search for JIRA issues using JQL."""

    jql: str = Field(..., description="JQL query string")
    max_results: int = Field(default=50, description="Maximum number of results")
    start_at: int = Field(default=0, description="Start index for pagination")
    fields: Optional[List[str]] = Field(None, description="List of fields to return")
    expand: Optional[List[str]] = Field(None, description="List of fields to expand")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraTransitionIssueRequest(BaseModel):
    """Request to transition a JIRA issue to a new status."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    transition_name: str = Field(..., description="Transition name (e.g., 'Done', 'In Progress')")
    comment: Optional[str] = Field(None, description="Optional comment to add during transition")
    fields: Optional[Dict[str, Any]] = Field(None, description="Additional fields to update during transition")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraAssignIssueRequest(BaseModel):
    """Request to assign a JIRA issue to a user."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    assignee: Optional[str] = Field(None, description="Assignee username/account ID, None for unassign")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraIssueResponse(BaseModel):
    """Response containing JIRA issue details."""

    key: str = Field(..., description="Issue key")
    id: str = Field(..., description="Issue ID")
    url: str = Field(..., description="Issue URL")
    fields: Dict[str, Any] = Field(..., description="Issue fields")
    expand: Optional[str] = Field(None, description="Expanded fields")


class JiraSearchIssuesResponse(BaseModel):
    """Response containing search results."""

    total: int = Field(..., description="Total number of matching issues")
    max_results: int = Field(..., description="Maximum results per page")
    start_at: int = Field(..., description="Starting index")
    issues: List[Dict[str, Any]] = Field(..., description="List of issues")
