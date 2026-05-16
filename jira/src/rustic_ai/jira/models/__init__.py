"""JIRA models for request and response payloads."""

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

__all__ = [
    # Issues
    "JiraCreateIssueRequest",
    "JiraUpdateIssueRequest",
    "JiraGetIssueRequest",
    "JiraDeleteIssueRequest",
    "JiraSearchIssuesRequest",
    "JiraTransitionIssueRequest",
    "JiraAssignIssueRequest",
    "JiraIssueResponse",
    "JiraSearchIssuesResponse",
    # Projects
    "JiraListProjectsRequest",
    "JiraGetProjectRequest",
    "JiraProjectResponse",
    "JiraProjectsResponse",
    # Comments
    "JiraAddCommentRequest",
    "JiraGetCommentsRequest",
    "JiraUpdateCommentRequest",
    "JiraDeleteCommentRequest",
    "JiraCommentResponse",
    # Users
    "JiraGetUserRequest",
    "JiraSearchUsersRequest",
    "JiraUserResponse",
    "JiraUsersResponse",
    # Attachments
    "JiraAddAttachmentRequest",
    "JiraGetAttachmentRequest",
    "JiraDeleteAttachmentRequest",
    "JiraAttachmentResponse",
]
