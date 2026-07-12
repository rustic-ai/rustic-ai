"""
Auto-generated Pydantic models for linear's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.linear.app/mcp"
   },
   "tools": [
     {
       "name": "get_attachment",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetAttachmentInput",
       "description": "Retrieve an attachment's content by ID."
     },
     {
       "name": "prepare_attachment_upload",
       "input_class_name": "rustic_ai.mcp.connectors.linear.PrepareAttachmentUploadInput",
       "description": "Prepare a direct Linear file upload for an existing issue.\n\nWorkflow:\n1. Call this tool with issue, filename, contentType, and size.\n2. Upload raw bytes with PUT to uploadRequest.url outside MCP.\n3. All headers in uploadRequest.headers are part of the signed request, so send them verbatim.\n4. After PUT succeeds, call create_attachment_from_upload with assetUrl to link it to the issue.\n\nDo not base64-encode or transform the file. Use curl --data-binary @path or fetch(url, { method: 'PUT', body: blob }).\nOmitting or modifying any signed header, including casing, will return HTTP 403.\nThe signed URL must be used within 60 seconds or it will expire.\n\nUpload sequencing:\nPrepare, PUT, and finalize one file before calling this tool for another file.\nDo not batch multiple prepare_attachment_upload calls before starting the PUTs because earlier signed URLs can expire while later files are prepared.\n\nExample:\ncurl -X PUT --data-binary @file.png \\\n  -H \"content-type: image/png\" \\\n  -H \"x-goog-content-length-range: N,N\" \\\n  -H \"cache-control: public, max-age=31536000\" \\\n  -H 'Content-Disposition: attachment; filename=\"file.png\"' \\\n  \"<uploadRequest.url>\""
     },
     {
       "name": "create_attachment_from_upload",
       "input_class_name": "rustic_ai.mcp.connectors.linear.CreateAttachmentFromUploadInput",
       "description": "Link an already-uploaded Linear assetUrl to an existing issue as an attachment.\n\nUse this only after:\n1. prepare_attachment_upload returned an assetUrl and uploadRequest.\n2. The client successfully PUT raw file bytes to uploadRequest.url.\n\nThis tool does not upload file content. It only creates the Linear attachment row.\nIf the direct upload failed or the signed URL expired, rerun prepare_attachment_upload and upload again."
     },
     {
       "name": "create_attachment",
       "input_class_name": "rustic_ai.mcp.connectors.linear.CreateAttachmentInput",
       "description": "Deprecated fallback for tiny files only. Accepts base64 file content and uploads it through the MCP worker, which can consume large amounts of agent context. Prefer `prepare_attachment_upload` plus direct PUT plus `create_attachment_from_upload`."
     },
     {
       "name": "delete_attachment",
       "input_class_name": "rustic_ai.mcp.connectors.linear.DeleteAttachmentInput",
       "description": "Delete an attachment by ID"
     },
     {
       "name": "list_comments",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListCommentsInput",
       "description": "List comments on a Linear issue, project, initiative, document, or project milestone. Provide exactly one of `issueId`, `projectId`, `initiativeId`, `documentId`, or `milestoneId`. For issues, projects, and initiatives this returns both top-level discussion threads and inline description comments. Inline (anchored) comments carry a non-null `quotedText` set to the snippet of description text they reference."
     },
     {
       "name": "save_comment",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveCommentInput",
       "description": "Create or update a comment on a Linear issue, project, initiative, document, or project milestone. If `id` is provided, updates the existing comment; otherwise creates a new one. To start a new thread, pass `body` and exactly one of `issueId`, `projectId`, `initiativeId`, `documentId`, or `milestoneId` \u2014 comments on issues/projects/initiatives become top-level discussion threads; comments on documents/milestones become description comments. To reply to an existing thread, pass `parentId` and `body`; the reply inherits the parent's thread type, so no entity reference is needed."
     },
     {
       "name": "delete_comment",
       "input_class_name": "rustic_ai.mcp.connectors.linear.DeleteCommentInput",
       "description": "Delete a Linear comment. Inline description comments (those with non-null `quotedText`) anchor a mark in the editor, so their root cannot be deleted \u2014 delete the replies individually or resolve the thread instead."
     },
     {
       "name": "list_cycles",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListCyclesInput",
       "description": "Retrieve cycles for a specific Linear team"
     },
     {
       "name": "get_document",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetDocumentInput",
       "description": "Retrieve a Linear document by ID or slug"
     },
     {
       "name": "list_documents",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListDocumentsInput",
       "description": "List documents in the user's Linear workspace"
     },
     {
       "name": "save_document",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveDocumentInput",
       "description": "Create or update a Linear document. If `id` is provided, updates the existing document; otherwise creates a new one. When creating, `title` is required and exactly one parent (`project`, `issue`, `initiative`, `cycle`, or `team`) must be specified. On update, passing a parent reparents the document."
     },
     {
       "name": "extract_images",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ExtractImagesInput",
       "description": "Extract and fetch images from markdown content. Use this to view screenshots, diagrams, or other images embedded in Linear issues, comments, or documents. Pass the markdown content (e.g., issue description) and receive the images as viewable data."
     },
     {
       "name": "get_issue",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetIssueInput",
       "description": "Retrieve detailed information about an issue by ID, including attachments and git branch name"
     },
     {
       "name": "list_issues",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListIssuesInput",
       "description": "List issues in the user's Linear workspace. For my issues, use \"me\" as the assignee. Use \"null\" for no assignee."
     },
     {
       "name": "save_issue",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveIssueInput",
       "description": "Create or update a Linear issue. If `id` is provided, updates the existing issue; otherwise creates a new one. When creating, `title` and `team` are required. Note: use `assignee` (not `assigneeId`) to set the assignee \u2014 it accepts a user ID, name, email, or \"me\"."
     },
     {
       "name": "list_issue_statuses",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListIssueStatusesInput",
       "description": "List available issue statuses in a Linear team"
     },
     {
       "name": "get_issue_status",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetIssueStatusInput",
       "description": "Retrieve detailed information about an issue status in Linear by name or ID"
     },
     {
       "name": "list_issue_labels",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListIssueLabelsInput",
       "description": "List available issue labels in a Linear workspace or team"
     },
     {
       "name": "create_issue_label",
       "input_class_name": "rustic_ai.mcp.connectors.linear.CreateIssueLabelInput",
       "description": "Create a new Linear issue label"
     },
     {
       "name": "list_projects",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListProjectsInput",
       "description": "List projects in the user's Linear workspace"
     },
     {
       "name": "get_project",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetProjectInput",
       "description": "Retrieve details of a specific project in Linear"
     },
     {
       "name": "save_project",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveProjectInput",
       "description": "Create or update a Linear project. If `id` is provided, updates the existing project; otherwise creates a new one. When creating, `name` and at least one team (via `addTeams` or `setTeams`) are required."
     },
     {
       "name": "list_project_labels",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListProjectLabelsInput",
       "description": "List available project labels in the Linear workspace"
     },
     {
       "name": "get_diff",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetDiffInput",
       "description": "Exact lookup for a Linear diff. Use with review URLs, GitHub PR URLs, Linear full identifiers, UUIDs, or slugs."
     },
     {
       "name": "list_diffs",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListDiffsInput",
       "description": "List Linear diff pull requests visible to the authenticated user"
     },
     {
       "name": "get_diff_threads",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetDiffThreadsInput",
       "description": "Exact lookup for diff threads. Use with review URLs, GitHub PR URLs, Linear full identifiers, UUIDs, or slugs."
     },
     {
       "name": "list_milestones",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListMilestonesInput",
       "description": "List all milestones in a Linear project"
     },
     {
       "name": "get_milestone",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetMilestoneInput",
       "description": "Retrieve details of a specific milestone by ID or name"
     },
     {
       "name": "save_milestone",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveMilestoneInput",
       "description": "Create or update a milestone in a Linear project. If `id` is provided, updates the existing milestone; otherwise creates a new one. When creating, `name` is required."
     },
     {
       "name": "list_teams",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListTeamsInput",
       "description": "List teams in the user's Linear workspace"
     },
     {
       "name": "get_team",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetTeamInput",
       "description": "Retrieve details of a specific Linear team"
     },
     {
       "name": "list_users",
       "input_class_name": "rustic_ai.mcp.connectors.linear.ListUsersInput",
       "description": "Retrieve users in the Linear workspace"
     },
     {
       "name": "get_user",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetUserInput",
       "description": "Retrieve details of a specific Linear user"
     },
     {
       "name": "search_documentation",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SearchDocumentationInput",
       "description": "Search Linear's documentation to learn about features and usage"
     },
     {
       "name": "get_status_updates",
       "input_class_name": "rustic_ai.mcp.connectors.linear.GetStatusUpdatesInput",
       "description": "List or get project/initiative status updates. Pass `id` to get a specific update, or filter to list."
     },
     {
       "name": "save_status_update",
       "input_class_name": "rustic_ai.mcp.connectors.linear.SaveStatusUpdateInput",
       "description": "Create or update a project/initiative status update. Omit `id` to create, provide `id` to update."
     },
     {
       "name": "delete_status_update",
       "input_class_name": "rustic_ai.mcp.connectors.linear.DeleteStatusUpdateInput",
       "description": "Delete (archive) a project or initiative status update."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Optional

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class GetAttachmentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Attachment ID")]


class PrepareAttachmentUploadInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    issue: Annotated[str, Field(description="Issue ID or identifier (e.g., LIN-123)")]
    filename: Annotated[str, Field(description="Filename for the upload, e.g. screenshot.png")]
    contentType: Annotated[str, Field(description="MIME type, e.g. image/png or application/pdf")]
    size: Annotated[
        int, Field(description="Exact file size in bytes. Must be smaller than 2 GB.", gt=0, le=9007199254740991)
    ]
    title: Annotated[Optional[str], Field(description="Suggested attachment title for the finalize step")] = None
    subtitle: Annotated[Optional[str], Field(description="Suggested attachment subtitle for the finalize step")] = None


class CreateAttachmentFromUploadInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    issue: Annotated[str, Field(description="Issue ID or identifier (e.g., LIN-123)")]
    assetUrl: Annotated[AnyUrl, Field(description="Linear upload assetUrl returned by prepare_attachment_upload")]
    title: Annotated[Optional[str], Field(description="Attachment title. Defaults to filename or asset URL")] = None
    subtitle: Annotated[Optional[str], Field(description="Optional attachment subtitle")] = None


class CreateAttachmentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    issue: Annotated[str, Field(description="Issue ID or identifier (e.g., LIN-123)")]
    base64Content: Annotated[str, Field(description="Deprecated base64-encoded file content to upload")]
    filename: Annotated[str, Field(description="Filename for the upload (e.g., 'screenshot.png')")]
    contentType: Annotated[str, Field(description="MIME type for the upload (e.g., 'image/png', 'application/pdf')")]
    title: Annotated[Optional[str], Field(description="Optional title for the attachment")] = None
    subtitle: Annotated[Optional[str], Field(description="Optional subtitle for the attachment")] = None


class DeleteAttachmentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Attachment ID")]


class OrderBy(Enum):
    """
    Sort: createdAt | updatedAt
    """

    CREATED_AT = "createdAt"
    UPDATED_AT = "updatedAt"


class ListCommentsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    issueId: Annotated[
        Optional[str], Field(description="Issue ID or identifier (e.g., LIN-123) (provide exactly one parent)")
    ] = None
    projectId: Annotated[Optional[str], Field(description="Project name, ID, or slug (provide exactly one parent)")] = (
        None
    )
    initiativeId: Annotated[Optional[str], Field(description="Initiative name or ID (provide exactly one parent)")] = (
        None
    )
    documentId: Annotated[Optional[str], Field(description="Document ID or slug (provide exactly one parent)")] = None
    milestoneId: Annotated[
        Optional[str],
        Field(
            description=(
                "Milestone UUID (provide exactly one parent). Resolve milestone names via `list_milestones` first."
            )
        ),
    ] = None


class SaveCommentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Optional[str], Field(description="Comment ID. If provided, updates the existing comment")] = None
    issueId: Annotated[
        Optional[str], Field(description="Issue ID or identifier (e.g., LIN-123) (provide exactly one parent)")
    ] = None
    projectId: Annotated[Optional[str], Field(description="Project name, ID, or slug (provide exactly one parent)")] = (
        None
    )
    initiativeId: Annotated[Optional[str], Field(description="Initiative name or ID (provide exactly one parent)")] = (
        None
    )
    documentId: Annotated[Optional[str], Field(description="Document ID or slug (provide exactly one parent)")] = None
    milestoneId: Annotated[
        Optional[str],
        Field(
            description=(
                "Milestone UUID (provide exactly one parent). Resolve milestone names via `list_milestones` first."
            )
        ),
    ] = None
    parentId: Annotated[Optional[str], Field(description="Parent comment ID (for replies, only when creating)")] = None
    body: Annotated[
        str,
        Field(
            description=(
                "Content as Markdown. Do not escape the string — use literal newlines and special characters, not"
                " escape sequences. To mention a user, use @displayName (e.g., @johndoe)"
            )
        ),
    ]


class DeleteCommentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Comment ID")]


class Type(Enum):
    """
    Filter: current, previous, next, or all
    """

    CURRENT = "current"
    PREVIOUS = "previous"
    NEXT = "next"


class ListCyclesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    teamId: Annotated[str, Field(description="Team ID")]
    type: Annotated[Optional[Type], Field(description="Filter: current, previous, next, or all")] = None


class GetDocumentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Document ID or slug")]


class ListDocumentsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Search query")] = None
    projectId: Annotated[Optional[str], Field(description="Filter by project ID")] = None
    initiativeId: Annotated[Optional[str], Field(description="Filter by initiative ID")] = None
    teamId: Annotated[Optional[str], Field(description="Filter by team ID")] = None
    creatorId: Annotated[Optional[str], Field(description="Filter by creator ID")] = None
    createdAt: Annotated[Optional[str], Field(description="Created after: ISO-8601 date/duration (e.g., -P1D)")] = None
    updatedAt: Annotated[Optional[str], Field(description="Updated after: ISO-8601 date/duration (e.g., -P1D)")] = None
    includeArchived: Annotated[Optional[bool], Field(description="Include archived items")] = False


class SaveDocumentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Optional[str], Field(description="Document ID or slug to update. Omit to create a new document.")] = (
        None
    )
    title: Annotated[Optional[str], Field(description="Document title (required when creating)")] = None
    content: Annotated[
        Optional[str],
        Field(
            description=(
                "Content as Markdown. Do not escape the string — use literal newlines and special characters, not"
                " escape sequences. To mention a user, use @displayName (e.g., @johndoe)"
            )
        ),
    ] = None
    project: Annotated[Optional[str], Field(description="Project name, ID, or slug")] = None
    issue: Annotated[Optional[str], Field(description="Issue ID or identifier (e.g., LIN-123)")] = None
    initiative: Annotated[Optional[str], Field(description="Initiative name or ID")] = None
    cycle: Annotated[
        Optional[str],
        Field(
            description="Cycle name, number, or ID. When passing a name or number, also pass `team` to disambiguate."
        ),
    ] = None
    team: Annotated[
        Optional[str],
        Field(
            description=(
                "Team name or ID. Attaches the document to the team, unless `cycle` is also passed, in which case it"
                " disambiguates the cycle."
            )
        ),
    ] = None
    icon: Annotated[
        Optional[str],
        Field(description='Icon name or emoji code (e.g. "Rocket" or ":eagle:"), not a raw Unicode emoji'),
    ] = None
    color: Annotated[Optional[str], Field(description="Hex color")] = None


class ExtractImagesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    markdown: Annotated[
        str, Field(description="Markdown content containing image references (e.g., issue description, comment body)")
    ]


class GetIssueInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Issue ID or identifier (e.g., LIN-123)")]
    includeRelations: Annotated[Optional[bool], Field(description="Include blocking/related/duplicate relations")] = (
        False
    )
    includeCustomerNeeds: Annotated[Optional[bool], Field(description="Include associated customer needs")] = False
    includeReleases: Annotated[Optional[bool], Field(description="Include associated releases")] = False


class ListIssuesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Search issue title or description")] = None
    team: Annotated[Optional[str], Field(description="Team name or ID")] = None
    state: Annotated[Optional[str], Field(description="State type, name, or ID")] = None
    cycle: Annotated[Optional[str], Field(description="Cycle name, number, or ID")] = None
    label: Annotated[Optional[str], Field(description="Label name or ID")] = None
    assignee: Annotated[Optional[str], Field(description='User ID, name, email, or "me"')] = None
    delegate: Annotated[
        Optional[str],
        Field(
            description=(
                'Agent name or ID. When the user asks to delegate to "Linear" or "the Linear agent", this refers to the'
                ' "Linear" app user specifically'
            )
        ),
    ] = None
    project: Annotated[Optional[str], Field(description="Project name, ID, or slug")] = None
    priority: Annotated[Optional[float], Field(description="0=None, 1=Urgent, 2=High, 3=Medium, 4=Low")] = None
    parentId: Annotated[Optional[str], Field(description="Parent issue ID or identifier (e.g., LIN-123)")] = None
    createdAt: Annotated[Optional[str], Field(description="Created after: ISO-8601 date/duration (e.g., -P1D)")] = None
    updatedAt: Annotated[Optional[str], Field(description="Updated after: ISO-8601 date/duration (e.g., -P1D)")] = None
    includeArchived: Annotated[Optional[bool], Field(description="Include archived items")] = True


class Link(BaseModel):
    url: AnyUrl
    title: Annotated[str, Field(min_length=1)]


class SaveIssueInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        Optional[str],
        Field(
            description=(
                "Only for updating an existing issue. Pass the issue ID or identifier (e.g., LIN-123). Do NOT pass this"
                " parameter when creating a new issue."
            )
        ),
    ] = None
    title: Annotated[Optional[str], Field(description="Issue title (required when creating)")] = None
    description: Annotated[
        Optional[str],
        Field(
            description=(
                "Content as Markdown. Do not escape the string — use literal newlines and special characters, not"
                " escape sequences. To mention a user, use @displayName (e.g., @johndoe)"
            )
        ),
    ] = None
    team: Annotated[Optional[str], Field(description="Team name or ID (required when creating)")] = None
    cycle: Annotated[Optional[str], Field(description="Cycle name, number, or ID. Null to remove")] = None
    milestone: Annotated[Optional[str], Field(description="Milestone name or ID")] = None
    priority: Annotated[Optional[float], Field(description="0=None, 1=Urgent, 2=High, 3=Medium, 4=Low")] = None
    project: Annotated[Optional[str], Field(description="Project name, ID, or slug")] = None
    state: Annotated[Optional[str], Field(description="State type, name, or ID")] = None
    assignee: Annotated[Optional[str], Field(description='User ID, name, email, or "me". Null to remove')] = None
    delegate: Annotated[
        Optional[str],
        Field(
            description=(
                'Agent name or ID. When the user asks to delegate to "Linear" or "the Linear agent", this refers to the'
                ' "Linear" app user specifically. Null to remove'
            )
        ),
    ] = None
    labels: Annotated[Optional[list[str]], Field(description="Label names or IDs")] = None
    dueDate: Annotated[Optional[str], Field(description="Due date (ISO format)")] = None
    parentId: Annotated[
        Optional[str], Field(description="Parent issue ID or identifier (e.g., LIN-123). Null to remove")
    ] = None
    estimate: Annotated[
        Optional[float],
        Field(
            description=(
                "Issue estimate value. On create, pass null or omit for no estimate. On update, pass null to clear the"
                " estimate; omitting leaves it unchanged. 0 is a real estimate only on teams that allow zero estimates."
            )
        ),
    ] = None
    links: Annotated[
        Optional[list[Link]],
        Field(description="Link attachments to add [{url, title}]. Append-only; existing links are never removed"),
    ] = None
    blocks: Annotated[
        Optional[list[str]],
        Field(description="Issue IDs/identifiers this blocks. Append-only; existing relations are never removed"),
    ] = None
    blockedBy: Annotated[
        Optional[list[str]],
        Field(description="Issue IDs/identifiers blocking this. Append-only; existing relations are never removed"),
    ] = None
    relatedTo: Annotated[
        Optional[list[str]],
        Field(description="Related issue IDs/identifiers. Append-only; existing relations are never removed"),
    ] = None
    duplicateOf: Annotated[Optional[str], Field(description="Duplicate of issue ID/identifier. Null to remove")] = None
    removeBlocks: Annotated[Optional[list[str]], Field(description="Issue IDs/identifiers to stop blocking")] = None
    removeBlockedBy: Annotated[
        Optional[list[str]], Field(description="Issue IDs/identifiers to remove as blockers of this issue")
    ] = None
    removeRelatedTo: Annotated[Optional[list[str]], Field(description="Related issue IDs/identifiers to remove")] = None


class ListIssueStatusesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    team: Annotated[str, Field(description="Team name or ID")]


class GetIssueStatusInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Status ID")]
    name: Annotated[str, Field(description="Status name")]
    team: Annotated[str, Field(description="Team name or ID")]


class ListIssueLabelsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    name: Annotated[Optional[str], Field(description="Filter by name")] = None
    team: Annotated[Optional[str], Field(description="Team name or ID")] = None


class CreateIssueLabelInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(description="Label name")]
    description: Annotated[Optional[str], Field(description="Label description")] = None
    color: Annotated[Optional[str], Field(description="Hex color code")] = None
    teamId: Annotated[Optional[str], Field(description="Team UUID (omit for workspace label)")] = None
    parent: Annotated[Optional[str], Field(description="Parent label group name")] = None
    isGroup: Annotated[Optional[bool], Field(description="Is label group (not directly applicable)")] = False


class ListProjectsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 50)", le=50.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Search project name")] = None
    state: Annotated[Optional[str], Field(description="State type, name, or ID")] = None
    initiative: Annotated[Optional[str], Field(description="Initiative name or ID")] = None
    team: Annotated[Optional[str], Field(description="Team name or ID")] = None
    member: Annotated[Optional[str], Field(description='User ID, name, email, or "me"')] = None
    label: Annotated[Optional[str], Field(description="Label name or ID")] = None
    createdAt: Annotated[Optional[str], Field(description="Created after: ISO-8601 date/duration (e.g., -P1D)")] = None
    updatedAt: Annotated[Optional[str], Field(description="Updated after: ISO-8601 date/duration (e.g., -P1D)")] = None
    includeMilestones: Annotated[Optional[bool], Field(description="Include milestones")] = False
    includeMembers: Annotated[Optional[bool], Field(description="Include project members")] = False
    includeArchived: Annotated[Optional[bool], Field(description="Include archived items")] = False


class GetProjectInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Project name, ID, or slug")]
    includeMilestones: Annotated[Optional[bool], Field(description="Include milestones")] = False
    includeMembers: Annotated[Optional[bool], Field(description="Include project members")] = False
    includeResources: Annotated[
        Optional[bool], Field(description="Include resources (documents, links, attachments)")
    ] = False


class StartDateResolution(Enum):
    """
    Start date resolution
    """

    HALF_YEAR = "halfYear"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class TargetDateResolution(Enum):
    """
    Target date resolution
    """

    HALF_YEAR = "halfYear"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class SaveProjectInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Optional[str], Field(description="Project ID. If provided, updates the existing project")] = None
    name: Annotated[Optional[str], Field(description="Project name (required when creating)")] = None
    icon: Annotated[
        Optional[str],
        Field(description='Icon name or emoji code (e.g. "Rocket" or ":eagle:"), not a raw Unicode emoji'),
    ] = None
    color: Annotated[Optional[str], Field(description="Hex color")] = None
    summary: Annotated[Optional[str], Field(description="Short summary (max 255 chars)")] = None
    description: Annotated[
        Optional[str],
        Field(
            description=(
                "Content as Markdown. Do not escape the string — use literal newlines and special characters, not"
                " escape sequences. To mention a user, use @displayName (e.g., @johndoe)"
            )
        ),
    ] = None
    state: Annotated[Optional[str], Field(description="Project state")] = None
    startDate: Annotated[
        Optional[str],
        Field(
            description=(
                "Start date (ISO format). Pair with startDateResolution to indicate precision (e.g. month, quarter)"
            )
        ),
    ] = None
    startDateResolution: Annotated[Optional[StartDateResolution], Field(description="Start date resolution")] = None
    targetDate: Annotated[
        Optional[str],
        Field(
            description=(
                "Target date (ISO format). Pair with targetDateResolution to indicate precision (e.g. month, quarter)"
            )
        ),
    ] = None
    targetDateResolution: Annotated[Optional[TargetDateResolution], Field(description="Target date resolution")] = None
    priority: Annotated[Optional[int], Field(description="0=None, 1=Urgent, 2=High, 3=Medium, 4=Low", ge=0, le=4)] = (
        None
    )
    addTeams: Annotated[Optional[list[str]], Field(description="Team name or ID to add")] = None
    removeTeams: Annotated[Optional[list[str]], Field(description="Team name or ID to remove")] = None
    setTeams: Annotated[
        Optional[list[str]], Field(description="Replace all teams with these. Cannot combine with addTeams/removeTeams")
    ] = None
    labels: Annotated[Optional[list[str]], Field(description="Label names or IDs")] = None
    lead: Annotated[Optional[str], Field(description='User ID, name, email, or "me". Null to remove')] = None
    addInitiatives: Annotated[Optional[list[str]], Field(description="Initiative names/IDs to add")] = None
    removeInitiatives: Annotated[Optional[list[str]], Field(description="Initiative names/IDs to remove")] = None
    setInitiatives: Annotated[
        Optional[list[str]],
        Field(description="Replace all initiatives with these. Cannot combine with addInitiatives/removeInitiatives"),
    ] = None


class ListProjectLabelsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    name: Annotated[Optional[str], Field(description="Filter by name")] = None


class GetDiffInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    urlOrId: Annotated[
        str,
        Field(
            description="Linear review URL, diff slug, pull request ID, Linear full identifier, or GitHub PR URL",
            min_length=1,
        ),
    ]


class ListDiffsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Broad search by title, branch, PR number, or bare slug")] = None
    owner: Annotated[Optional[str], Field(description="Filter returned diffs by repository owner")] = None
    repo: Annotated[Optional[str], Field(description="Filter returned diffs by repository name")] = None
    status: Annotated[Optional[str], Field(description="Filter returned diffs by pull request status")] = None


class GetDiffThreadsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    urlOrId: Annotated[
        str,
        Field(
            description="Linear review URL, diff slug, pull request ID, Linear full identifier, or GitHub PR URL",
            min_length=1,
        ),
    ]
    threadId: Annotated[Optional[str], Field(description="Optional top-level thread/comment ID to return")] = None
    resolved: Annotated[Optional[bool], Field(description="Filter returned threads by resolved state")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT


class ListMilestonesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    project: Annotated[str, Field(description="Project name, ID, or slug")]


class GetMilestoneInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    project: Annotated[str, Field(description="Project name, ID, or slug")]
    query: Annotated[str, Field(description="Milestone name or ID")]


class SaveMilestoneInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    project: Annotated[str, Field(description="Project name, ID, or slug")]
    id: Annotated[Optional[str], Field(description="Milestone name or ID")] = None
    name: Annotated[Optional[str], Field(description="Milestone name (required when creating)")] = None
    description: Annotated[Optional[str], Field(description="Milestone description")] = None
    targetDate: Annotated[Optional[str], Field(description="Target completion date (ISO format, null to remove)")] = (
        None
    )


class ListTeamsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Search query")] = None
    includeArchived: Annotated[Optional[bool], Field(description="Include archived items")] = False
    createdAt: Annotated[Optional[str], Field(description="Created after: ISO-8601 date/duration (e.g., -P1D)")] = None
    updatedAt: Annotated[Optional[str], Field(description="Updated after: ISO-8601 date/duration (e.g., -P1D)")] = None


class GetTeamInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Team UUID, key, or name")]


class ListUsersInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    query: Annotated[Optional[str], Field(description="Filter by name or email")] = None
    team: Annotated[Optional[str], Field(description="Team name or ID")] = None


class GetUserInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description='User ID, name, email, or "me"')]


class SearchDocumentationInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Search query")]
    page: Annotated[Optional[float], Field(description="Page number")] = 0


class Type1(Enum):
    """
    Type of status update
    """

    PROJECT = "project"
    INITIATIVE = "initiative"


class GetStatusUpdatesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[Optional[float], Field(description="Max results (default 50, max 250)", le=250.0)] = 50
    cursor: Annotated[Optional[str], Field(description="Next page cursor")] = None
    orderBy: Annotated[Optional[OrderBy], Field(description="Sort: createdAt | updatedAt")] = OrderBy.UPDATED_AT
    type: Annotated[Type1, Field(description="Type of status update")]
    id: Annotated[Optional[str], Field(description="Status update ID - if provided, returns this specific update")] = (
        None
    )
    project: Annotated[Optional[str], Field(description="Project name, ID, or slug")] = None
    initiative: Annotated[Optional[str], Field(description="Initiative name or ID")] = None
    user: Annotated[Optional[str], Field(description='User ID, name, email, or "me"')] = None
    createdAt: Annotated[Optional[str], Field(description="Created after: ISO-8601 date/duration (e.g., -P1D)")] = None
    updatedAt: Annotated[Optional[str], Field(description="Updated after: ISO-8601 date/duration (e.g., -P1D)")] = None
    includeArchived: Annotated[Optional[bool], Field(description="Include archived items")] = False


class Health(Enum):
    """
    onTrack | atRisk | offTrack
    """

    ON_TRACK = "onTrack"
    AT_RISK = "atRisk"
    OFF_TRACK = "offTrack"


class SaveStatusUpdateInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Annotated[Type1, Field(description="Type of status update")]
    id: Annotated[Optional[str], Field(description="Status update ID - if provided, updates this existing update")] = (
        None
    )
    project: Annotated[Optional[str], Field(description="Project name, ID, or slug")] = None
    initiative: Annotated[Optional[str], Field(description="Initiative name or ID")] = None
    body: Annotated[
        Optional[str],
        Field(
            description=(
                "Content as Markdown. Do not escape the string — use literal newlines and special characters, not"
                " escape sequences. To mention a user, use @displayName (e.g., @johndoe)"
            )
        ),
    ] = None
    health: Annotated[Optional[Health], Field(description="onTrack | atRisk | offTrack")] = None
    isDiffHidden: Annotated[Optional[bool], Field(description="Deprecated. Hide diff with previous update")] = None


class DeleteStatusUpdateInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Annotated[Type1, Field(description="Type of status update")]
    id: Annotated[str, Field(description="Status update ID")]
