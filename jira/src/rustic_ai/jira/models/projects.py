"""JIRA project models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JiraListProjectsRequest(BaseModel):
    """Request to list all JIRA projects."""

    expand: Optional[List[str]] = Field(
        None, description="List of fields to expand (e.g., ['description', 'lead', 'issueTypes'])"
    )
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraGetProjectRequest(BaseModel):
    """Request to get a specific JIRA project."""

    project_key: str = Field(..., description="Project key (e.g., 'PROJ')")
    expand: Optional[List[str]] = Field(None, description="List of fields to expand")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraProjectResponse(BaseModel):
    """Response containing JIRA project details."""

    key: str = Field(..., description="Project key")
    id: str = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    lead: Optional[Dict[str, Any]] = Field(None, description="Project lead information")
    url: str = Field(..., description="Project URL")
    project_type_key: Optional[str] = Field(None, description="Project type")


class JiraProjectsResponse(BaseModel):
    """Response containing list of JIRA projects."""

    projects: List[Dict[str, Any]] = Field(..., description="List of projects")
    total: int = Field(..., description="Total number of projects")
