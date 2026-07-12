"""
Auto-generated Pydantic models for github's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://api.githubcopilot.com/mcp/x/all"
   },
   "tools": [
     {
       "name": "actions_get",
       "input_class_name": "rustic_ai.mcp.connectors.github.ActionsGetInput",
       "description": "Get details about specific GitHub Actions resources.\nUse this tool to get details about individual workflows, workflow runs, jobs, and artifacts by their unique IDs.\n"
     },
     {
       "name": "actions_list",
       "input_class_name": "rustic_ai.mcp.connectors.github.ActionsListInput",
       "description": "Tools for listing GitHub Actions resources.\nUse this tool to list workflows in a repository, or list workflow runs, jobs, and artifacts for a specific workflow or workflow run.\n"
     },
     {
       "name": "actions_run_trigger",
       "input_class_name": "rustic_ai.mcp.connectors.github.ActionsRunTriggerInput",
       "description": "Trigger GitHub Actions workflow operations, including running, re-running, cancelling workflow runs, and deleting workflow run logs."
     },
     {
       "name": "add_comment_to_pending_review",
       "input_class_name": "rustic_ai.mcp.connectors.github.AddCommentToPendingReviewInput",
       "description": "Add review comment to the requester's latest pending pull request review. A pending review needs to already exist to call this (check with the user if not sure)."
     },
     {
       "name": "add_issue_comment",
       "input_class_name": "rustic_ai.mcp.connectors.github.AddIssueCommentInput",
       "description": "Add a comment to a specific issue in a GitHub repository. Use this tool to add comments to pull requests as well (in this case pass pull request number as issue_number), but only if user is not asking specifically to add review comments."
     },
     {
       "name": "add_reply_to_pull_request_comment",
       "input_class_name": "rustic_ai.mcp.connectors.github.AddReplyToPullRequestCommentInput",
       "description": "Add a reply to an existing pull request comment. This creates a new comment that is linked as a reply to the specified comment."
     },
     {
       "name": "check_dependency_vulnerabilities",
       "input_class_name": "rustic_ai.mcp.connectors.github.CheckDependencyVulnerabilitiesInput",
       "description": "Check a list of dependencies for known vulnerabilities using the GitHub Security Advisory Database.\nThis tool queries the GitHub Advisory Database to find known security vulnerabilities affecting the specified packages.\n\nUse this tool when:\n- You want to check if project dependencies have known vulnerabilities\n- You are adding a new dependency to a project and should check it is safe before adding to the project\n\nThe tool accepts owner, repo, and a list of dependencies with their ecosystems and versions, then returns any matching security advisories with upgrade recommendations where available."
     },
     {
       "name": "create_branch",
       "input_class_name": "rustic_ai.mcp.connectors.github.CreateBranchInput",
       "description": "Create a new branch in a GitHub repository"
     },
     {
       "name": "create_gist",
       "input_class_name": "rustic_ai.mcp.connectors.github.CreateGistInput",
       "description": "Create a new gist"
     },
     {
       "name": "create_or_update_file",
       "input_class_name": "rustic_ai.mcp.connectors.github.CreateOrUpdateFileInput",
       "description": "Create or update a single file in a GitHub repository. \nIf updating, you should provide the SHA of the file you want to update. Use this tool to create or update a file in a GitHub repository remotely; do not use it for local file operations.\n\nIn order to obtain the SHA of original file version before updating, use the following git command:\ngit rev-parse <branch>:<path to file>\n\nSHA MUST be provided for existing file updates.\n"
     },
     {
       "name": "create_pull_request",
       "input_class_name": "rustic_ai.mcp.connectors.github.CreatePullRequestInput",
       "description": "Create a new pull request in a GitHub repository."
     },
     {
       "name": "create_repository",
       "input_class_name": "rustic_ai.mcp.connectors.github.CreateRepositoryInput",
       "description": "Create a new GitHub repository in your account or specified organization"
     },
     {
       "name": "delete_file",
       "input_class_name": "rustic_ai.mcp.connectors.github.DeleteFileInput",
       "description": "Delete a file from a GitHub repository"
     },
     {
       "name": "discussion_comment_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.DiscussionCommentWriteInput",
       "description": "Write operations for discussion comments.\nSupports adding top-level comments, replying to existing comments, updating comment content, deleting comments, and marking or unmarking comments as the answer."
     },
     {
       "name": "dismiss_notification",
       "input_class_name": "rustic_ai.mcp.connectors.github.DismissNotificationInput",
       "description": "Dismiss a notification by marking it as read or done"
     },
     {
       "name": "fork_repository",
       "input_class_name": "rustic_ai.mcp.connectors.github.ForkRepositoryInput",
       "description": "Fork a GitHub repository to your account or specified organization"
     },
     {
       "name": "get_code_quality_finding",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetCodeQualityFindingInput",
       "description": "Get details of a specific code quality finding in a GitHub repository."
     },
     {
       "name": "get_code_scanning_alert",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetCodeScanningAlertInput",
       "description": "Get details of a specific code scanning alert in a GitHub repository."
     },
     {
       "name": "get_commit",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetCommitInput",
       "description": "Get details for a commit from a GitHub repository"
     },
     {
       "name": "get_copilot_space",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetCopilotSpaceInput",
       "description": "This tool can be used to provide additional context to the chat from a specific Copilot space. If the user mentions the keyword 'Copilot space' with the name and owner of the space, execute this tool.\n\nThe response includes a table of contents (TOC) listing all documents in the space, followed by the full content of each document. Documents are separated by markers in the format: '--- Document N: path (size) ---'. When searching for specific information, use grep (or equivalent command) to search across all documents; the separator lines will help identify which document contains the matching content."
     },
     {
       "name": "get_dependabot_alert",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetDependabotAlertInput",
       "description": "Get details of a specific dependabot alert in a GitHub repository."
     },
     {
       "name": "get_discussion",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetDiscussionInput",
       "description": "Get a specific discussion by ID"
     },
     {
       "name": "get_discussion_comments",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetDiscussionCommentsInput",
       "description": "Get comments from a discussion"
     },
     {
       "name": "get_file_contents",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetFileContentsInput",
       "description": "Get the contents of a file or directory from a GitHub repository"
     },
     {
       "name": "get_gist",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetGistInput",
       "description": "Get gist content of a particular gist, by gist ID"
     },
     {
       "name": "get_global_security_advisory",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetGlobalSecurityAdvisoryInput",
       "description": "Get a global security advisory"
     },
     {
       "name": "get_job_logs",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetJobLogsInput",
       "description": "Get logs for GitHub Actions workflow jobs.\nUse this tool to retrieve logs for a specific job or all failed jobs in a workflow run.\nFor single job logs, provide job_id. For all failed jobs in a run, provide run_id with failed_only=true.\n"
     },
     {
       "name": "get_label",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetLabelInput",
       "description": "Get a specific label from a repository."
     },
     {
       "name": "get_latest_release",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetLatestReleaseInput",
       "description": "Get the latest release in a GitHub repository"
     },
     {
       "name": "get_me",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetMeInput",
       "description": "Get details of the authenticated GitHub user. Use this when a request is about the user's own profile for GitHub. Or when information is missing to build other tool calls."
     },
     {
       "name": "get_notification_details",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetNotificationDetailsInput",
       "description": "Get detailed information for a specific GitHub notification, always call this tool when the user asks for details about a specific notification, if you don't know the ID list notifications first."
     },
     {
       "name": "get_release_by_tag",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetReleaseByTagInput",
       "description": "Get a specific release by its tag name in a GitHub repository"
     },
     {
       "name": "get_repository_tree",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetRepositoryTreeInput",
       "description": "Get the tree structure (files and directories) of a GitHub repository at a specific ref or SHA"
     },
     {
       "name": "get_secret_scanning_alert",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetSecretScanningAlertInput",
       "description": "Get details of a specific secret scanning alert in a GitHub repository."
     },
     {
       "name": "get_tag",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetTagInput",
       "description": "Get details about a specific git tag in a GitHub repository"
     },
     {
       "name": "get_team_members",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetTeamMembersInput",
       "description": "Get member usernames of a specific team in an organization. Limited to organizations accessible with current credentials"
     },
     {
       "name": "get_teams",
       "input_class_name": "rustic_ai.mcp.connectors.github.GetTeamsInput",
       "description": "Get details of the teams the user is a member of. Limited to organizations accessible with current credentials"
     },
     {
       "name": "github_support_docs_search",
       "input_class_name": "rustic_ai.mcp.connectors.github.GithubSupportDocsSearchInput",
       "description": "Retrieve documentation relevant to answer GitHub product and support questions. Support topics include: GitHub Actions Workflows, Authentication, GitHub Support Inquiries, Pull Request Practices, Repository Maintenance, GitHub Pages, GitHub Packages, GitHub Discussions, Copilot Spaces"
     },
     {
       "name": "issue_read",
       "input_class_name": "rustic_ai.mcp.connectors.github.IssueReadInput",
       "description": "Get information about a specific issue in a GitHub repository."
     },
     {
       "name": "issue_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.IssueWriteInput",
       "description": "Create a new or update an existing issue in a GitHub repository."
     },
     {
       "name": "label_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.LabelWriteInput",
       "description": "Perform write operations on repository labels. To set labels on issues, use the 'update_issue' tool."
     },
     {
       "name": "list_branches",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListBranchesInput",
       "description": "List branches in a GitHub repository"
     },
     {
       "name": "list_code_scanning_alerts",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListCodeScanningAlertsInput",
       "description": "List code scanning alerts in a GitHub repository."
     },
     {
       "name": "list_commits",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListCommitsInput",
       "description": "Get list of commits of a branch in a GitHub repository. Returns at least 30 results per page by default, but can return more if specified using the perPage parameter (up to 100)."
     },
     {
       "name": "list_copilot_spaces",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListCopilotSpacesInput",
       "description": "Retrieves the list of Copilot Spaces accessible to the user, including their names and owners."
     },
     {
       "name": "list_dependabot_alerts",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListDependabotAlertsInput",
       "description": "List dependabot alerts in a GitHub repository."
     },
     {
       "name": "list_discussion_categories",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListDiscussionCategoriesInput",
       "description": "List discussion categories with their id and name, for a repository or organisation."
     },
     {
       "name": "list_discussions",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListDiscussionsInput",
       "description": "List discussions for a repository or organisation."
     },
     {
       "name": "list_gists",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListGistsInput",
       "description": "List gists for a user"
     },
     {
       "name": "list_global_security_advisories",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListGlobalSecurityAdvisoriesInput",
       "description": "List global security advisories from GitHub."
     },
     {
       "name": "list_issue_fields",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListIssueFieldsInput",
       "description": "List issue fields for a repository or organization. Returns field definitions including name, type (text, number, date, single_select), and for single_select fields the list of valid option names. When repo is omitted, returns org-level fields directly."
     },
     {
       "name": "list_issue_types",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListIssueTypesInput",
       "description": "List supported issue types for a repository or its owner organization. When repo is omitted, returns org-level issue types directly."
     },
     {
       "name": "list_issues",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListIssuesInput",
       "description": "List issues in a GitHub repository. For pagination, use the 'endCursor' from the previous response's 'pageInfo' in the 'after' parameter."
     },
     {
       "name": "list_label",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListLabelInput",
       "description": "List labels from a repository"
     },
     {
       "name": "list_notifications",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListNotificationsInput",
       "description": "Lists all GitHub notifications for the authenticated user, including unread notifications, mentions, review requests, assignments, and updates on issues or pull requests. Use this tool whenever the user asks what to work on next, requests a summary of their GitHub activity, wants to see pending reviews, or needs to check for new updates or tasks. This tool is the primary way to discover actionable items, reminders, and outstanding work on GitHub. Always call this tool when asked what to work on next, what is pending, or what needs attention in GitHub."
     },
     {
       "name": "list_org_repository_security_advisories",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListOrgRepositorySecurityAdvisoriesInput",
       "description": "List repository security advisories for a GitHub organization."
     },
     {
       "name": "list_pull_requests",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListPullRequestsInput",
       "description": "List pull requests in a GitHub repository. If the user specifies an author, then DO NOT use this tool and use the search_pull_requests tool instead."
     },
     {
       "name": "list_releases",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListReleasesInput",
       "description": "List releases in a GitHub repository"
     },
     {
       "name": "list_repository_collaborators",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListRepositoryCollaboratorsInput",
       "description": "List collaborators of a GitHub repository. Results are paginated; the response includes `nextPage`, `prevPage`, `firstPage`, and `lastPage` fields. To get the next page, use the `nextPage` value as the `page` parameter."
     },
     {
       "name": "list_repository_security_advisories",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListRepositorySecurityAdvisoriesInput",
       "description": "List repository security advisories for a GitHub repository."
     },
     {
       "name": "list_secret_scanning_alerts",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListSecretScanningAlertsInput",
       "description": "List secret scanning alerts in a GitHub repository."
     },
     {
       "name": "list_starred_repositories",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListStarredRepositoriesInput",
       "description": "List starred repositories"
     },
     {
       "name": "list_tags",
       "input_class_name": "rustic_ai.mcp.connectors.github.ListTagsInput",
       "description": "List git tags in a GitHub repository"
     },
     {
       "name": "manage_notification_subscription",
       "input_class_name": "rustic_ai.mcp.connectors.github.ManageNotificationSubscriptionInput",
       "description": "Manage a notification subscription: ignore, watch, or delete a notification thread subscription."
     },
     {
       "name": "manage_repository_notification_subscription",
       "input_class_name": "rustic_ai.mcp.connectors.github.ManageRepositoryNotificationSubscriptionInput",
       "description": "Manage a repository notification subscription: ignore, watch, or delete repository notifications subscription for the provided repository."
     },
     {
       "name": "mark_all_notifications_read",
       "input_class_name": "rustic_ai.mcp.connectors.github.MarkAllNotificationsReadInput",
       "description": "Mark all notifications as read"
     },
     {
       "name": "merge_pull_request",
       "input_class_name": "rustic_ai.mcp.connectors.github.MergePullRequestInput",
       "description": "Merge a pull request in a GitHub repository."
     },
     {
       "name": "projects_get",
       "input_class_name": "rustic_ai.mcp.connectors.github.ProjectsGetInput",
       "description": "Get details about specific GitHub Projects resources.\nUse this tool to get details about individual projects, project fields, and project items by their unique IDs.\n"
     },
     {
       "name": "projects_list",
       "input_class_name": "rustic_ai.mcp.connectors.github.ProjectsListInput",
       "description": "Tools for listing GitHub Projects resources.\nUse this tool to list projects for a user or organization, or list project fields and items for a specific project.\n"
     },
     {
       "name": "projects_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.ProjectsWriteInput",
       "description": "Create and manage GitHub Projects: create projects, add/update/delete items, create status updates, and add iteration fields."
     },
     {
       "name": "pull_request_read",
       "input_class_name": "rustic_ai.mcp.connectors.github.PullRequestReadInput",
       "description": "Get information on a specific pull request in GitHub repository."
     },
     {
       "name": "pull_request_review_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.PullRequestReviewWriteInput",
       "description": "Create and/or submit, delete review of a pull request.\n\nAvailable methods:\n- create: Create a new review of a pull request. If \"event\" parameter is provided, the review is submitted. If \"event\" is omitted, a pending review is created.\n- submit_pending: Submit an existing pending review of a pull request. This requires that a pending review exists for the current user on the specified pull request. The \"body\" and \"event\" parameters are used when submitting the review.\n- delete_pending: Delete an existing pending review of a pull request. This requires that a pending review exists for the current user on the specified pull request.\n- resolve_thread: Resolve a review thread. Requires only \"threadId\" parameter with the thread's node ID (e.g., PRRT_kwDOxxx). The owner, repo, and pullNumber parameters are not used for this method. Resolving an already-resolved thread is a no-op.\n- unresolve_thread: Unresolve a previously resolved review thread. Requires only \"threadId\" parameter. The owner, repo, and pullNumber parameters are not used for this method. Unresolving an already-unresolved thread is a no-op.\n"
     },
     {
       "name": "push_files",
       "input_class_name": "rustic_ai.mcp.connectors.github.PushFilesInput",
       "description": "Push multiple files to a GitHub repository in a single commit"
     },
     {
       "name": "request_copilot_review",
       "input_class_name": "rustic_ai.mcp.connectors.github.RequestCopilotReviewInput",
       "description": "Request a GitHub Copilot code review for a pull request. Use this for automated feedback on pull requests, usually before requesting a human reviewer."
     },
     {
       "name": "run_secret_scanning",
       "input_class_name": "rustic_ai.mcp.connectors.github.RunSecretScanningInput",
       "description": "Scan files, content, or recent changes for secrets such as API keys, passwords, tokens, and credentials.\n\nThis tool is intended for targeted scans of specific files, snippets, or diffs provided directly as content. The files parameter accepts either a single string or an array of strings containing raw file contents or diff hunks, and returns detected secrets with their locations and related secret scanning metadata. Content must not be empty. For full repository scanning, other mechanisms are available.\n\nCaveats:\n\n- Only files within the codebase should be scanned. Files outside of the codebase should not be sent.\n- Files listed in .gitignore should be skipped."
     },
     {
       "name": "search_code",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchCodeInput",
       "description": "Fast and precise code search across ALL GitHub repositories using GitHub's native search engine. Best for finding exact symbols, functions, classes, or specific code patterns."
     },
     {
       "name": "search_commits",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchCommitsInput",
       "description": "Search for commits across GitHub repositories using GitHub's commit search syntax. Useful for finding specific changes, authors, or messages across one or many repositories. Searches the default branch only."
     },
     {
       "name": "search_issues",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchIssuesInput",
       "description": "Search for issues in GitHub repositories using issues search syntax already scoped to is:issue"
     },
     {
       "name": "search_orgs",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchOrgsInput",
       "description": "Find GitHub organizations by name, location, or other organization metadata. Ideal for discovering companies, open source foundations, or teams."
     },
     {
       "name": "search_pull_requests",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchPullRequestsInput",
       "description": "Search for pull requests in GitHub repositories using issues search syntax already scoped to is:pr"
     },
     {
       "name": "search_repositories",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchRepositoriesInput",
       "description": "Find GitHub repositories by name, description, readme, topics, or other metadata. Perfect for discovering projects, finding examples, or locating specific repositories across GitHub."
     },
     {
       "name": "search_users",
       "input_class_name": "rustic_ai.mcp.connectors.github.SearchUsersInput",
       "description": "Find GitHub users by username, real name, or other profile information. Useful for locating developers, contributors, or team members."
     },
     {
       "name": "semantic_issue_similarity_search",
       "input_class_name": "rustic_ai.mcp.connectors.github.SemanticIssueSimilaritySearchInput",
       "description": "Find issues that are semantically similar to a given issue using natural language understanding. Useful for identifying duplicates, related issues, or similar problems."
     },
     {
       "name": "semantic_issues_search",
       "input_class_name": "rustic_ai.mcp.connectors.github.SemanticIssuesSearchInput",
       "description": "Search for issues using natural language queries within a GitHub repository or across the user's top repositories.\n\t\t\t\t\tThis tool uses embedded vector data to find relevant issues,\n\t\t\t\t\teven if they don't contain your exact keywords.\n\t\t\t\t\tThe embeddings are pre-computed and updated regularly,\n\t\t\t\t\tso the search is a fast and cheap way to find related issues.\n\n\t\t\t\t\tUse this tool when:\n\t\t\t\t\t- You want to find issues related to a concept or topic\n\t\t\t\t\t- You want related / similar issues without enumerating every keyword\n\t\t\t\t\t- You're exploring or de-duplicating problem reports\n\t\t\t\t\t- You are researching introspection queries about a repo (such as when asking about the most requested features or progress on a specific feature), since Issues represent the planning & tracking portion of the work\n\n\t\t\t\t\tBenefits:\n\t\t\t\t\t- Captures synonyms & paraphrases (e.g. \"screen reader focus loss\" vs \"VoiceOver loses focus\")\n\t\t\t\t\t- Reduces missed matches from narrow keyword lists\n\n\t\t\t\t\tExamples:\n\t\t\t\t\t- Find authentication bugs: query=\"authentication login errors\", owner=\"octocat\", repo=\"Hello-World\"\n\t\t\t\t\t- Find open issues about auth authored by a specific user: query=\"state:open author:monalisa User permissions, access control, and authentication errors\", owner=\"octocat\", repo=\"Hello-World\"\n\t\t\t\t\t- Find performance problems: query=\"slow rendering performance\", owner=\"octocat\", repo=\"Hello-World\"\n\t\t\t\t\t- Find issues across the user's top repositories: query=\"memory leak\"\n\n\t\t\t\t\tIf no repository is specified, searches across the user's top repositories. For more targeted results, specify a specific repository.\n\t\t"
     },
     {
       "name": "star_repository",
       "input_class_name": "rustic_ai.mcp.connectors.github.StarRepositoryInput",
       "description": "Star a GitHub repository"
     },
     {
       "name": "sub_issue_write",
       "input_class_name": "rustic_ai.mcp.connectors.github.SubIssueWriteInput",
       "description": "Add a sub-issue to a parent issue in a GitHub repository."
     },
     {
       "name": "triage_issue",
       "input_class_name": "rustic_ai.mcp.connectors.github.TriageIssueInput",
       "description": "Triage an issue by capturing a focused triage rationale and optionally applying metadata (labels, issue type, and issue fields) in a single operation.\nUse this tool when:\n- You are triaging a newly opened or untriaged issue for maintainers\n- You need to categorize the issue (type) and suggest/apply relevant labels\n- You want to record a brief, structured triage report\n\nDo not use this tool when:\n- The user is asking a general product question unrelated to triaging a specific issue\n\ntriage_rationale should be concise markdown aimed at maintainers (not the issue author); it  should contain:\n- Summary of the issue\n- Analysis of the problem or request\n- Suggested next steps or actions."
     },
     {
       "name": "unstar_repository",
       "input_class_name": "rustic_ai.mcp.connectors.github.UnstarRepositoryInput",
       "description": "Unstar a GitHub repository"
     },
     {
       "name": "update_gist",
       "input_class_name": "rustic_ai.mcp.connectors.github.UpdateGistInput",
       "description": "Update an existing gist"
     },
     {
       "name": "update_pull_request",
       "input_class_name": "rustic_ai.mcp.connectors.github.UpdatePullRequestInput",
       "description": "Update an existing pull request in a GitHub repository."
     },
     {
       "name": "update_pull_request_branch",
       "input_class_name": "rustic_ai.mcp.connectors.github.UpdatePullRequestBranchInput",
       "description": "Update the branch of a pull request with the latest changes from the base branch."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Method(Enum):
    """
    The method to execute
    """

    GET_WORKFLOW = "get_workflow"
    GET_WORKFLOW_RUN = "get_workflow_run"
    GET_WORKFLOW_JOB = "get_workflow_job"
    DOWNLOAD_WORKFLOW_RUN_ARTIFACT = "download_workflow_run_artifact"
    GET_WORKFLOW_RUN_USAGE = "get_workflow_run_usage"
    GET_WORKFLOW_RUN_LOGS_URL = "get_workflow_run_logs_url"


class ActionsGetInput(BaseModel):
    method: Annotated[Method, Field(description="The method to execute")]
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    resource_id: Annotated[
        str,
        Field(
            description=(
                'The unique identifier of the resource. This will vary based on the "method" provided, so ensure you'
                " provide the correct ID:\n- Provide a workflow ID or workflow file name (e.g. ci.yaml) for"
                " 'get_workflow' method.\n- Provide a workflow run ID for 'get_workflow_run',"
                " 'get_workflow_run_usage', and 'get_workflow_run_logs_url' methods.\n- Provide an artifact ID for"
                " 'download_workflow_run_artifact' method.\n- Provide a job ID for 'get_workflow_job' method.\n"
            )
        ),
    ]


class Method1(Enum):
    """
    The action to perform
    """

    LIST_WORKFLOWS = "list_workflows"
    LIST_WORKFLOW_RUNS = "list_workflow_runs"
    LIST_WORKFLOW_JOBS = "list_workflow_jobs"
    LIST_WORKFLOW_RUN_ARTIFACTS = "list_workflow_run_artifacts"


class Filter(Enum):
    """
    Filters jobs by their completed_at timestamp
    """

    LATEST = "latest"
    ALL = "all"


class WorkflowJobsFilter(BaseModel):
    """
    Filters for workflow jobs. **ONLY** used when method is 'list_workflow_jobs'
    """

    filter: Annotated[Optional[Filter], Field(description="Filters jobs by their completed_at timestamp")] = None


class Event(Enum):
    """
    Filter workflow runs to a specific event type
    """

    BRANCH_PROTECTION_RULE = "branch_protection_rule"
    CHECK_RUN = "check_run"
    CHECK_SUITE = "check_suite"
    CREATE = "create"
    DELETE = "delete"
    DEPLOYMENT = "deployment"
    DEPLOYMENT_STATUS = "deployment_status"
    DISCUSSION = "discussion"
    DISCUSSION_COMMENT = "discussion_comment"
    FORK = "fork"
    GOLLUM = "gollum"
    ISSUE_COMMENT = "issue_comment"
    ISSUES = "issues"
    LABEL = "label"
    MERGE_GROUP = "merge_group"
    MILESTONE = "milestone"
    PAGE_BUILD = "page_build"
    PUBLIC = "public"
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PULL_REQUEST_REVIEW_COMMENT = "pull_request_review_comment"
    PULL_REQUEST_TARGET = "pull_request_target"
    PUSH = "push"
    REGISTRY_PACKAGE = "registry_package"
    RELEASE = "release"
    REPOSITORY_DISPATCH = "repository_dispatch"
    SCHEDULE = "schedule"
    STATUS = "status"
    WATCH = "watch"
    WORKFLOW_CALL = "workflow_call"
    WORKFLOW_DISPATCH = "workflow_dispatch"
    WORKFLOW_RUN = "workflow_run"


class Status(Enum):
    """
    Filter workflow runs to only runs with a specific status
    """

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REQUESTED = "requested"
    WAITING = "waiting"


class WorkflowRunsFilter(BaseModel):
    """
    Filters for workflow runs. **ONLY** used when method is 'list_workflow_runs'
    """

    actor: Annotated[Optional[str], Field(description="Filter to a specific GitHub user's workflow runs.")] = None
    branch: Annotated[
        Optional[str], Field(description="Filter workflow runs to a specific Git branch. Use the name of the branch.")
    ] = None
    event: Annotated[Optional[Event], Field(description="Filter workflow runs to a specific event type")] = None
    status: Annotated[
        Optional[Status], Field(description="Filter workflow runs to only runs with a specific status")
    ] = None


class ActionsListInput(BaseModel):
    method: Annotated[Method1, Field(description="The action to perform")]
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (default: 1)", ge=1.0)] = None
    per_page: Annotated[
        Optional[float], Field(description="Results per page for pagination (default: 30, max: 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    resource_id: Annotated[
        Optional[str],
        Field(
            description=(
                'The unique identifier of the resource. This will vary based on the "method" provided, so ensure you'
                " provide the correct ID:\n- Do not provide any resource ID for 'list_workflows' method.\n- Provide a"
                " workflow ID or workflow file name (e.g. ci.yaml) for 'list_workflow_runs' method, or omit to list"
                " all workflow runs in the repository.\n- Provide a workflow run ID for 'list_workflow_jobs' and"
                " 'list_workflow_run_artifacts' methods.\n"
            )
        ),
    ] = None
    workflow_jobs_filter: Annotated[
        Optional[WorkflowJobsFilter],
        Field(description="Filters for workflow jobs. **ONLY** used when method is 'list_workflow_jobs'"),
    ] = None
    workflow_runs_filter: Annotated[
        Optional[WorkflowRunsFilter],
        Field(description="Filters for workflow runs. **ONLY** used when method is 'list_workflow_runs'"),
    ] = None


class Method2(Enum):
    """
    The method to execute
    """

    RUN_WORKFLOW = "run_workflow"
    RERUN_WORKFLOW_RUN = "rerun_workflow_run"
    RERUN_FAILED_JOBS = "rerun_failed_jobs"
    CANCEL_WORKFLOW_RUN = "cancel_workflow_run"
    DELETE_WORKFLOW_RUN_LOGS = "delete_workflow_run_logs"


class ActionsRunTriggerInput(BaseModel):
    inputs: Annotated[
        Optional[dict[str, Any]], Field(description="Inputs the workflow accepts. Only used for 'run_workflow' method.")
    ] = None
    method: Annotated[Method2, Field(description="The method to execute")]
    owner: Annotated[str, Field(description="Repository owner")]
    ref: Annotated[
        Optional[str],
        Field(
            description=(
                "The git reference for the workflow. The reference can be a branch or tag name. Required for"
                " 'run_workflow' method."
            )
        ),
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    run_id: Annotated[
        Optional[float],
        Field(description="The ID of the workflow run. Required for all methods except 'run_workflow'."),
    ] = None
    workflow_id: Annotated[
        Optional[str],
        Field(
            description=(
                "The workflow ID (numeric) or workflow file name (e.g., main.yml, ci.yaml). Required for 'run_workflow'"
                " method."
            )
        ),
    ] = None


class Side(Enum):
    """
    The side of the diff to comment on. LEFT indicates the previous state, RIGHT indicates the new state
    """

    LEFT = "LEFT"
    RIGHT = "RIGHT"


class StartSide(Enum):
    """
    For multi-line comments, the starting side of the diff that the comment applies to. LEFT indicates the previous state, RIGHT indicates the new state
    """

    LEFT = "LEFT"
    RIGHT = "RIGHT"


class SubjectType(Enum):
    """
    The level at which the comment is targeted
    """

    FILE = "FILE"
    LINE = "LINE"


class AddCommentToPendingReviewInput(BaseModel):
    body: Annotated[str, Field(description="The text of the review comment")]
    line: Annotated[
        Optional[float],
        Field(
            description=(
                "The line of the blob in the pull request diff that the comment applies to. For multi-line comments,"
                " the last line of the range"
            )
        ),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    path: Annotated[str, Field(description="The relative path to the file that necessitates a comment")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]
    side: Annotated[
        Optional[Side],
        Field(
            description=(
                "The side of the diff to comment on. LEFT indicates the previous state, RIGHT indicates the new state"
            )
        ),
    ] = None
    startLine: Annotated[
        Optional[float],
        Field(description="For multi-line comments, the first line of the range that the comment applies to"),
    ] = None
    startSide: Annotated[
        Optional[StartSide],
        Field(
            description=(
                "For multi-line comments, the starting side of the diff that the comment applies to. LEFT indicates the"
                " previous state, RIGHT indicates the new state"
            )
        ),
    ] = None
    subjectType: Annotated[SubjectType, Field(description="The level at which the comment is targeted")]


class AddIssueCommentInput(BaseModel):
    body: Annotated[str, Field(description="Comment content")]
    issue_number: Annotated[float, Field(description="Issue number to comment on")]
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class AddReplyToPullRequestCommentInput(BaseModel):
    body: Annotated[str, Field(description="The text of the reply")]
    commentId: Annotated[float, Field(description="The ID of the comment to reply to")]
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]


class Ecosystem(Enum):
    """
    Package ecosystem
    """

    NPM = "npm"
    PIP = "pip"
    MAVEN = "maven"
    NUGET = "nuget"
    COMPOSER = "composer"
    PUB = "pub"
    ACTIONS = "actions"
    BUNDLER = "bundler"
    GOMOD = "gomod"
    CARGO = "cargo"
    HEX = "hex"


class Dependency(BaseModel):
    ecosystem: Annotated[Ecosystem, Field(description="Package ecosystem")]
    name: Annotated[str, Field(description="Package name")]
    version: Annotated[str, Field(description="Package version")]


class CheckDependencyVulnerabilitiesInput(BaseModel):
    dependencies: Annotated[list[Dependency], Field(description="List of dependencies to check for vulnerabilities")]
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    repo: Annotated[str, Field(description="Repository name")]


class CreateBranchInput(BaseModel):
    branch: Annotated[str, Field(description="Name for new branch")]
    from_branch: Annotated[Optional[str], Field(description="Source branch (defaults to repo default)")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class CreateGistInput(BaseModel):
    content: Annotated[str, Field(description="Content for simple single-file gist creation")]
    description: Annotated[Optional[str], Field(description="Description of the gist")] = None
    filename: Annotated[str, Field(description="Filename for simple single-file gist creation")]
    public: Annotated[Optional[bool], Field(description="Whether the gist is public")] = False


class CreateOrUpdateFileInput(BaseModel):
    branch: Annotated[str, Field(description="Branch to create/update the file in")]
    content: Annotated[str, Field(description="Content of the file")]
    message: Annotated[str, Field(description="Commit message")]
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    path: Annotated[str, Field(description="Path where to create/update the file")]
    repo: Annotated[str, Field(description="Repository name")]
    sha: Annotated[
        Optional[str],
        Field(description="The blob SHA of the file being replaced. Required if the file already exists."),
    ] = None


class CreatePullRequestInput(BaseModel):
    base: Annotated[str, Field(description="Branch to merge into")]
    body: Annotated[Optional[str], Field(description="PR description")] = None
    draft: Annotated[Optional[bool], Field(description="Create as draft PR")] = None
    head: Annotated[str, Field(description="Branch containing changes")]
    maintainer_can_modify: Annotated[Optional[bool], Field(description="Allow maintainer edits")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    reviewers: Annotated[
        Optional[list[str]],
        Field(description="GitHub usernames or ORG/team-slug team reviewers to request reviews from"),
    ] = None
    title: Annotated[str, Field(description="PR title")]


class CreateRepositoryInput(BaseModel):
    autoInit: Annotated[Optional[bool], Field(description="Initialize with README")] = None
    description: Annotated[Optional[str], Field(description="Repository description")] = None
    name: Annotated[str, Field(description="Repository name")]
    organization: Annotated[
        Optional[str],
        Field(description="Organization to create the repository in (omit to create in your personal account)"),
    ] = None
    private: Annotated[
        Optional[bool],
        Field(description="Whether the repository should be private. Defaults to true (private) when omitted."),
    ] = True


class DeleteFileInput(BaseModel):
    branch: Annotated[str, Field(description="Branch to delete the file from")]
    message: Annotated[str, Field(description="Commit message")]
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    path: Annotated[str, Field(description="Path to the file to delete")]
    repo: Annotated[str, Field(description="Repository name")]


class Method3(Enum):
    """
    Write operation to perform on a discussion comment.
    Options are:
    - 'add' - adds a new top-level comment to a discussion.
    - 'reply' - replies to a top-level discussion comment (GitHub Discussions only support one level of nesting).
    - 'update' - updates an existing discussion comment.
    - 'delete' - deletes a discussion comment.
    - 'mark_answer' - marks a discussion comment as the answer (Q&A only).
    - 'unmark_answer' - unmarks a discussion comment as the answer (Q&A only).

    """

    ADD = "add"
    REPLY = "reply"
    UPDATE = "update"
    DELETE = "delete"
    MARK_ANSWER = "mark_answer"
    UNMARK_ANSWER = "unmark_answer"


class DiscussionCommentWriteInput(BaseModel):
    body: Annotated[
        Optional[str], Field(description="Comment content (required for 'add', 'reply', and 'update' methods)")
    ] = None
    commentNodeID: Annotated[
        Optional[str],
        Field(
            description=(
                "The Node ID of the discussion comment (required for 'reply', 'update', 'delete', 'mark_answer', and"
                " 'unmark_answer' methods). For 'reply', this is the top-level comment to reply to; GitHub Discussions"
                " only support one level of nesting."
            )
        ),
    ] = None
    discussionNumber: Annotated[
        Optional[float], Field(description="Discussion number (required for 'add' and 'reply' methods)")
    ] = None
    method: Annotated[
        Method3,
        Field(
            description=(
                "Write operation to perform on a discussion comment.\nOptions are:\n- 'add' - adds a new top-level"
                " comment to a discussion.\n- 'reply' - replies to a top-level discussion comment (GitHub Discussions"
                " only support one level of nesting).\n- 'update' - updates an existing discussion comment.\n- 'delete'"
                " - deletes a discussion comment.\n- 'mark_answer' - marks a discussion comment as the answer (Q&A"
                " only).\n- 'unmark_answer' - unmarks a discussion comment as the answer (Q&A only).\n"
            )
        ),
    ]
    owner: Annotated[Optional[str], Field(description="Repository owner (required for 'add' and 'reply' methods)")] = (
        None
    )
    repo: Annotated[Optional[str], Field(description="Repository name (required for 'add' and 'reply' methods)")] = None


class State(Enum):
    """
    The new state of the notification (read/done)
    """

    READ = "read"
    DONE = "done"


class DismissNotificationInput(BaseModel):
    state: Annotated[State, Field(description="The new state of the notification (read/done)")]
    threadID: Annotated[str, Field(description="The ID of the notification thread")]


class ForkRepositoryInput(BaseModel):
    organization: Annotated[Optional[str], Field(description="Organization to fork to")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class GetCodeQualityFindingInput(BaseModel):
    findingNumber: Annotated[float, Field(description="The number of the finding.")]
    owner: Annotated[str, Field(description="The owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]


class GetCodeScanningAlertInput(BaseModel):
    alertNumber: Annotated[float, Field(description="The number of the alert.")]
    owner: Annotated[str, Field(description="The owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]


class Detail(Enum):
    """
    Level of detail to include for changed files. "none" omits stats and files entirely. "stats" (default) includes
    per-file metadata: filename, status, and lines-of-code counts (additions, deletions, changes), with no patch
    content. "full_patch" additionally includes the unified diff content for each file and can be very large.
    """

    NONE = "none"
    STATS = "stats"
    FULL_PATCH = "full_patch"


class GetCommitInput(BaseModel):
    detail: Annotated[
        Optional[Detail],
        Field(
            description=(
                'Level of detail to include for changed files. "none" omits stats and files entirely. "stats" (default)'
                " includes per-file metadata: filename, status, and lines-of-code counts (additions, deletions,"
                ' changes), with no patch content. "full_patch" additionally includes the unified diff content for each'
                " file and can be very large."
            )
        ),
    ] = Detail.STATS
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    sha: Annotated[str, Field(description="Commit SHA, branch name, or tag name")]


class GetCopilotSpaceInput(BaseModel):
    name: Annotated[str, Field(description="The name of the space")]
    owner: Annotated[str, Field(description="The owner of the space")]


class GetDependabotAlertInput(BaseModel):
    alertNumber: Annotated[float, Field(description="The number of the alert.")]
    owner: Annotated[str, Field(description="The owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]


class GetDiscussionInput(BaseModel):
    discussionNumber: Annotated[float, Field(description="Discussion Number")]
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class GetDiscussionCommentsInput(BaseModel):
    after: Annotated[
        Optional[str], Field(description="Cursor for pagination. Use the cursor from the previous response.")
    ] = None
    discussionNumber: Annotated[float, Field(description="Discussion Number")]
    includeReplies: Annotated[
        Optional[bool],
        Field(
            description=(
                "When true, each top-level comment will include its replies nested within it (up to 100 replies per"
                " comment, which is the GitHub API maximum). Defaults to false."
            )
        ),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]


class GetFileContentsInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    path: Annotated[Optional[str], Field(description="Path to file/directory")] = "/"
    ref: Annotated[
        Optional[str],
        Field(
            description=(
                "Accepts optional git refs such as `refs/tags/{tag}`, `refs/heads/{branch}` or"
                " `refs/pull/{pr_number}/head`"
            )
        ),
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    sha: Annotated[
        Optional[str], Field(description="Accepts optional commit SHA. If specified, it will be used instead of ref")
    ] = None


class GetGistInput(BaseModel):
    gist_id: Annotated[str, Field(description="The ID of the gist")]


class GetGlobalSecurityAdvisoryInput(BaseModel):
    ghsaId: Annotated[str, Field(description="GitHub Security Advisory ID (format: GHSA-xxxx-xxxx-xxxx).")]


class GetJobLogsInput(BaseModel):
    failed_only: Annotated[
        Optional[bool],
        Field(
            description=(
                "When true, gets logs for all failed jobs in the workflow run specified by run_id. Requires run_id to"
                " be provided."
            )
        ),
    ] = None
    job_id: Annotated[
        Optional[float],
        Field(description="The unique identifier of the workflow job. Required when getting logs for a single job."),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    return_content: Annotated[Optional[bool], Field(description="Returns actual log content instead of URLs")] = None
    run_id: Annotated[
        Optional[float],
        Field(
            description=(
                "The unique identifier of the workflow run. Required when failed_only is true to get logs for all"
                " failed jobs in the run."
            )
        ),
    ] = None
    tail_lines: Annotated[Optional[float], Field(description="Number of lines to return from the end of the log")] = 500


class GetLabelInput(BaseModel):
    name: Annotated[str, Field(description="Label name.")]
    owner: Annotated[str, Field(description="Repository owner (username or organization name)")]
    repo: Annotated[str, Field(description="Repository name")]


class GetLatestReleaseInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class GetMeInput(BaseModel):
    pass


class GetNotificationDetailsInput(BaseModel):
    notificationID: Annotated[str, Field(description="The ID of the notification")]


class GetReleaseByTagInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    tag: Annotated[str, Field(description="Tag name (e.g., 'v1.0.0')")]


class GetRepositoryTreeInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    path_filter: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional path prefix to filter the tree results (e.g., 'src/' to only show files in the src directory)"
            )
        ),
    ] = None
    recursive: Annotated[
        Optional[bool],
        Field(
            description=(
                "Setting this parameter to true returns the objects or subtrees referenced by the tree. Default is"
                " false"
            )
        ),
    ] = False
    repo: Annotated[str, Field(description="Repository name")]
    tree_sha: Annotated[
        Optional[str],
        Field(
            description=(
                "The SHA1 value or ref (branch or tag) name of the tree. Defaults to the repository's default branch"
            )
        ),
    ] = None


class GetSecretScanningAlertInput(BaseModel):
    alertNumber: Annotated[float, Field(description="The number of the alert.")]
    owner: Annotated[str, Field(description="The owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]


class GetTagInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    tag: Annotated[str, Field(description="Tag name")]


class GetTeamMembersInput(BaseModel):
    org: Annotated[str, Field(description="Organization login (owner) that contains the team.")]
    team_slug: Annotated[str, Field(description="Team slug")]


class GetTeamsInput(BaseModel):
    user: Annotated[
        Optional[str], Field(description="Username to get teams for. If not provided, uses the authenticated user.")
    ] = None


class GithubSupportDocsSearchInput(BaseModel):
    query: Annotated[
        str,
        Field(
            description=(
                "Input from the user about the question they need answered. This is the latest raw unedited user"
                " message. You should ALWAYS leave the user message as it is, you should never modify it."
            )
        ),
    ]


class Method4(Enum):
    """
    The read operation to perform on a single issue.
    Options are:
    1. get - Get details of a specific issue.
    2. get_comments - Get issue comments.
    3. get_sub_issues - Get sub-issues of the issue.
    4. get_labels - Get labels assigned to the issue.

    """

    GET = "get"
    GET_COMMENTS = "get_comments"
    GET_SUB_ISSUES = "get_sub_issues"
    GET_LABELS = "get_labels"


class IssueReadInput(BaseModel):
    issue_number: Annotated[float, Field(description="The number of the issue")]
    method: Annotated[
        Method4,
        Field(
            description=(
                "The read operation to perform on a single issue.\nOptions are:\n1. get - Get details of a specific"
                " issue.\n2. get_comments - Get issue comments.\n3. get_sub_issues - Get sub-issues of the issue.\n4."
                " get_labels - Get labels assigned to the issue.\n"
            )
        ),
    ]
    owner: Annotated[str, Field(description="The owner of the repository")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="The name of the repository")]


class Delete(Enum):
    """
    Set to true to clear this field's current value on the issue. Cannot be combined with 'value' or 'field_option_name'.
    """

    BOOLEAN_TRUE = True


class IssueField(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    delete: Annotated[
        Optional[Delete],
        Field(
            description=(
                "Set to true to clear this field's current value on the issue. Cannot be combined with 'value' or"
                " 'field_option_name'."
            )
        ),
    ] = None
    field_name: Annotated[
        str,
        Field(
            description=(
                "Issue field name (case-insensitive). Must match a field returned by list_issue_fields for this"
                " repository or its organization."
            )
        ),
    ]
    field_option_name: Annotated[
        Optional[str],
        Field(
            description=(
                "Option name for single-select fields. Validated against the field's options before the API call."
                " Cannot be combined with 'value' or 'delete'."
            )
        ),
    ] = None
    value: Annotated[
        Optional[Union[str, float, bool]],
        Field(
            description=(
                "Value to set. Use for text, number, and date fields (date as YYYY-MM-DD). For single-select fields,"
                " prefer 'field_option_name' so the option is validated before the API call. Cannot be combined with"
                " 'field_option_name' or 'delete'."
            )
        ),
    ] = None


class Method5(Enum):
    """
    Write operation to perform on a single issue.
    Options are:
    - 'create' - creates a new issue.
    - 'update' - updates an existing issue.

    """

    CREATE = "create"
    UPDATE = "update"


class State1(Enum):
    """
    New state
    """

    OPEN = "open"
    CLOSED = "closed"


class StateReason(Enum):
    """
    Reason for the state change. Ignored unless state is changed.
    """

    COMPLETED = "completed"
    NOT_PLANNED = "not_planned"
    DUPLICATE = "duplicate"


class IssueWriteInput(BaseModel):
    assignees: Annotated[Optional[list[str]], Field(description="Usernames to assign to this issue")] = None
    body: Annotated[Optional[str], Field(description="Issue body content")] = None
    duplicate_of: Annotated[
        Optional[float],
        Field(
            description="Issue number that this issue is a duplicate of. Only used when state_reason is 'duplicate'."
        ),
    ] = None
    issue_fields: Annotated[
        Optional[list[IssueField]],
        Field(
            description=(
                "Issue field values to set or clear. Each item requires 'field_name' and exactly one of 'value',"
                " 'field_option_name', or 'delete: true'."
            )
        ),
    ] = None
    issue_number: Annotated[Optional[float], Field(description="Issue number to update")] = None
    labels: Annotated[Optional[list[str]], Field(description="Labels to apply to this issue")] = None
    method: Annotated[
        Method5,
        Field(
            description=(
                "Write operation to perform on a single issue.\nOptions are:\n- 'create' - creates a new issue.\n-"
                " 'update' - updates an existing issue.\n"
            )
        ),
    ]
    milestone: Annotated[Optional[float], Field(description="Milestone number")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]
    state: Annotated[Optional[State1], Field(description="New state")] = None
    state_reason: Annotated[
        Optional[StateReason], Field(description="Reason for the state change. Ignored unless state is changed.")
    ] = None
    title: Annotated[Optional[str], Field(description="Issue title")] = None
    type: Annotated[
        Optional[str],
        Field(
            description=(
                "Type of this issue. Only use if issue types are enabled for this repository. Use list_issue_types tool"
                " to get valid type values for this repository or its owner organization. If the repository doesn't"
                " support issue types, omit this parameter."
            )
        ),
    ] = None


class Method6(Enum):
    """
    Operation to perform: 'create', 'update', or 'delete'
    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class LabelWriteInput(BaseModel):
    color: Annotated[
        Optional[str],
        Field(
            description=(
                "Label color as 6-character hex code without '#' prefix (e.g., 'f29513'). Required for 'create',"
                " optional for 'update'."
            )
        ),
    ] = None
    description: Annotated[
        Optional[str], Field(description="Label description text. Optional for 'create' and 'update'.")
    ] = None
    method: Annotated[Method6, Field(description="Operation to perform: 'create', 'update', or 'delete'")]
    name: Annotated[str, Field(description="Label name - required for all operations")]
    new_name: Annotated[
        Optional[str], Field(description="New name for the label (used only with 'update' method to rename)")
    ] = None
    owner: Annotated[str, Field(description="Repository owner (username or organization name)")]
    repo: Annotated[str, Field(description="Repository name")]


class ListBranchesInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]


class Severity(Enum):
    """
    Filter code scanning alerts by severity
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    WARNING = "warning"
    NOTE = "note"
    ERROR = "error"


class State2(Enum):
    """
    Filter code scanning alerts by state. Defaults to open
    """

    OPEN = "open"
    CLOSED = "closed"
    DISMISSED = "dismissed"
    FIXED = "fixed"


class ListCodeScanningAlertsInput(BaseModel):
    owner: Annotated[str, Field(description="The owner of the repository.")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    ref: Annotated[Optional[str], Field(description="The Git reference for the results you want to list.")] = None
    repo: Annotated[str, Field(description="The name of the repository.")]
    severity: Annotated[Optional[Severity], Field(description="Filter code scanning alerts by severity")] = None
    state: Annotated[Optional[State2], Field(description="Filter code scanning alerts by state. Defaults to open")] = (
        State2.OPEN
    )
    tool_name: Annotated[Optional[str], Field(description="The name of the tool used for code scanning.")] = None


class ListCommitsInput(BaseModel):
    author: Annotated[Optional[str], Field(description="Author username or email address to filter commits by")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    path: Annotated[Optional[str], Field(description="Only commits containing this file path will be returned")] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    sha: Annotated[
        Optional[str],
        Field(
            description=(
                "Commit SHA, branch or tag name to list commits of. If not provided, uses the default branch of the"
                " repository. If a commit SHA is provided, will list commits up to that SHA."
            )
        ),
    ] = None
    since: Annotated[
        Optional[str],
        Field(
            description=(
                "Only commits after this date will be returned (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD)"
            )
        ),
    ] = None
    until: Annotated[
        Optional[str],
        Field(
            description=(
                "Only commits before this date will be returned (ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD)"
            )
        ),
    ] = None


class ListCopilotSpacesInput(BaseModel):
    pass


class Severity1(Enum):
    """
    Filter dependabot alerts by severity
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class State3(Enum):
    """
    Filter dependabot alerts by state. Defaults to open
    """

    OPEN = "open"
    FIXED = "fixed"
    DISMISSED = "dismissed"
    AUTO_DISMISSED = "auto_dismissed"


class ListDependabotAlertsInput(BaseModel):
    after: Annotated[
        Optional[str], Field(description="Cursor for pagination. Use the cursor from the previous response.")
    ] = None
    owner: Annotated[str, Field(description="The owner of the repository.")]
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="The name of the repository.")]
    severity: Annotated[Optional[Severity1], Field(description="Filter dependabot alerts by severity")] = None
    state: Annotated[Optional[State3], Field(description="Filter dependabot alerts by state. Defaults to open")] = (
        State3.OPEN
    )


class ListDiscussionCategoriesInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "Repository name. If not provided, discussion categories will be queried at the organisation level."
            )
        ),
    ] = None


class Direction(Enum):
    """
    Order direction.
    """

    ASC = "ASC"
    DESC = "DESC"


class OrderBy(Enum):
    """
    Order discussions by field. If provided, the 'direction' also needs to be provided.
    """

    CREATED_AT = "CREATED_AT"
    UPDATED_AT = "UPDATED_AT"


class ListDiscussionsInput(BaseModel):
    after: Annotated[
        Optional[str], Field(description="Cursor for pagination. Use the cursor from the previous response.")
    ] = None
    category: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional filter by discussion category ID. If provided, only discussions with this category are"
                " listed."
            )
        ),
    ] = None
    direction: Annotated[Optional[Direction], Field(description="Order direction.")] = None
    orderBy: Annotated[
        Optional[OrderBy],
        Field(description="Order discussions by field. If provided, the 'direction' also needs to be provided."),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[
        Optional[str],
        Field(description="Repository name. If not provided, discussions will be queried at the organisation level."),
    ] = None


class ListGistsInput(BaseModel):
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    since: Annotated[Optional[str], Field(description="Only gists updated after this time (ISO 8601 timestamp)")] = None
    username: Annotated[Optional[str], Field(description="GitHub username (omit for authenticated user's gists)")] = (
        None
    )


class Ecosystem1(Enum):
    """
    Filter by package ecosystem.
    """

    ACTIONS = "actions"
    COMPOSER = "composer"
    ERLANG = "erlang"
    GO = "go"
    MAVEN = "maven"
    NPM = "npm"
    NUGET = "nuget"
    OTHER = "other"
    PIP = "pip"
    PUB = "pub"
    RUBYGEMS = "rubygems"
    RUST = "rust"


class Severity2(Enum):
    """
    Filter by severity.
    """

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Type(Enum):
    """
    Advisory type.
    """

    REVIEWED = "reviewed"
    MALWARE = "malware"
    UNREVIEWED = "unreviewed"


class ListGlobalSecurityAdvisoriesInput(BaseModel):
    affects: Annotated[
        Optional[str],
        Field(description='Filter advisories by affected package or version (e.g. "package1,package2@1.0.0").'),
    ] = None
    cveId: Annotated[Optional[str], Field(description="Filter by CVE ID.")] = None
    cwes: Annotated[
        Optional[list[str]], Field(description='Filter by Common Weakness Enumeration IDs (e.g. ["79", "284", "22"]).')
    ] = None
    ecosystem: Annotated[Optional[Ecosystem1], Field(description="Filter by package ecosystem.")] = None
    ghsaId: Annotated[
        Optional[str], Field(description="Filter by GitHub Security Advisory ID (format: GHSA-xxxx-xxxx-xxxx).")
    ] = None
    isWithdrawn: Annotated[Optional[bool], Field(description="Whether to only return withdrawn advisories.")] = None
    modified: Annotated[
        Optional[str], Field(description="Filter by publish or update date or date range (ISO 8601 date or range).")
    ] = None
    published: Annotated[
        Optional[str], Field(description="Filter by publish date or date range (ISO 8601 date or range).")
    ] = None
    severity: Annotated[Optional[Severity2], Field(description="Filter by severity.")] = None
    type: Annotated[Optional[Type], Field(description="Advisory type.")] = Type.REVIEWED
    updated: Annotated[
        Optional[str], Field(description="Filter by update date or date range (ISO 8601 date or range).")
    ] = None


class ListIssueFieldsInput(BaseModel):
    owner: Annotated[
        str, Field(description="The account owner of the repository or organization. The name is not case sensitive.")
    ]
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the repository. When provided, returns fields for this specific repository (inherited from"
                " its organization). When omitted, returns org-level fields directly."
            )
        ),
    ] = None


class ListIssueTypesInput(BaseModel):
    owner: Annotated[str, Field(description="The account owner of the repository or organization.")]
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the repository. When provided, returns issue types for this specific repository. When"
                " omitted, returns org-level issue types directly."
            )
        ),
    ] = None


class Direction1(Enum):
    """
    Order direction. If provided, the 'orderBy' also needs to be provided.
    """

    ASC = "ASC"
    DESC = "DESC"


class FieldFilter(BaseModel):
    field_name: Annotated[str, Field(description='Name of the custom field (e.g. "Priority"). Case-insensitive.')]
    value: Annotated[
        str,
        Field(
            description=(
                'Value to filter on. For single-select fields, the option name (e.g. "P1"). For dates, YYYY-MM-DD. For'
                " numbers, the numeric value as a string. For text, the text value."
            )
        ),
    ]


class OrderBy1(Enum):
    """
    Order issues by field. If provided, the 'direction' also needs to be provided.
    """

    CREATED_AT = "CREATED_AT"
    UPDATED_AT = "UPDATED_AT"
    COMMENTS = "COMMENTS"


class State4(Enum):
    """
    Filter by state, by default both open and closed issues are returned when not provided
    """

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ListIssuesInput(BaseModel):
    after: Annotated[
        Optional[str], Field(description="Cursor for pagination. Use the cursor from the previous response.")
    ] = None
    direction: Annotated[
        Optional[Direction1],
        Field(description="Order direction. If provided, the 'orderBy' also needs to be provided."),
    ] = None
    field_filters: Annotated[
        Optional[list[FieldFilter]],
        Field(
            description=(
                "Filter by custom issue field values. Each entry takes a field_name and a value; the server looks up"
                " the field and coerces the value to its type (single-select option name, text, number, or YYYY-MM-DD"
                " date)."
            )
        ),
    ] = None
    labels: Annotated[Optional[list[str]], Field(description="Filter by labels")] = None
    orderBy: Annotated[
        Optional[OrderBy1],
        Field(description="Order issues by field. If provided, the 'direction' also needs to be provided."),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    since: Annotated[Optional[str], Field(description="Filter by date (ISO 8601 timestamp)")] = None
    state: Annotated[
        Optional[State4],
        Field(description="Filter by state, by default both open and closed issues are returned when not provided"),
    ] = None


class ListLabelInput(BaseModel):
    owner: Annotated[
        str, Field(description="Repository owner (username or organization name) - required for all operations")
    ]
    repo: Annotated[str, Field(description="Repository name - required for all operations")]


class Filter1(Enum):
    """
    Filter notifications to, use default unless specified. Read notifications are ones that have already been
    acknowledged by the user. Participating notifications are those that the user is directly involved in,
    such as issues or pull requests they have commented on or created.
    """

    DEFAULT = "default"
    INCLUDE_READ_NOTIFICATIONS = "include_read_notifications"
    ONLY_PARTICIPATING = "only_participating"


class ListNotificationsInput(BaseModel):
    before: Annotated[
        Optional[str], Field(description="Only show notifications updated before the given time (ISO 8601 format)")
    ] = None
    filter: Annotated[
        Optional[Filter1],
        Field(
            description=(
                "Filter notifications to, use default unless specified. Read notifications are ones that have already"
                " been acknowledged by the user. Participating notifications are those that the user is directly"
                " involved in, such as issues or pull requests they have commented on or created."
            )
        ),
    ] = None
    owner: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository owner. If provided with repo, only notifications for this repository are listed."
            )
        ),
    ] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository name. If provided with owner, only notifications for this repository are listed."
            )
        ),
    ] = None
    since: Annotated[
        Optional[str], Field(description="Only show notifications updated after the given time (ISO 8601 format)")
    ] = None


class Direction2(Enum):
    """
    Sort direction.
    """

    ASC = "asc"
    DESC = "desc"


class Sort(Enum):
    """
    Sort field.
    """

    CREATED = "created"
    UPDATED = "updated"
    PUBLISHED = "published"


class State5(Enum):
    """
    Filter by advisory state.
    """

    TRIAGE = "triage"
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ListOrgRepositorySecurityAdvisoriesInput(BaseModel):
    direction: Annotated[Optional[Direction2], Field(description="Sort direction.")] = None
    org: Annotated[str, Field(description="The organization login.")]
    sort: Annotated[Optional[Sort], Field(description="Sort field.")] = None
    state: Annotated[Optional[State5], Field(description="Filter by advisory state.")] = None


class Direction3(Enum):
    """
    Sort direction
    """

    ASC = "asc"
    DESC = "desc"


class Sort1(Enum):
    """
    Sort by
    """

    CREATED = "created"
    UPDATED = "updated"
    POPULARITY = "popularity"
    LONG_RUNNING = "long-running"


class State6(Enum):
    """
    Filter by state
    """

    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class ListPullRequestsInput(BaseModel):
    base: Annotated[Optional[str], Field(description="Filter by base branch")] = None
    direction: Annotated[Optional[Direction3], Field(description="Sort direction")] = None
    head: Annotated[Optional[str], Field(description="Filter by head user/org and branch")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    sort: Annotated[Optional[Sort1], Field(description="Sort by")] = None
    state: Annotated[Optional[State6], Field(description="Filter by state")] = None


class ListReleasesInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]


class Affiliation(Enum):
    """
    Filter by affiliation. Can be one of: 'outside' (outside collaborators), 'direct' (all with permissions
    regardless of org membership), 'all' (all collaborators). Default: 'all'
    """

    OUTSIDE = "outside"
    DIRECT = "direct"
    ALL = "all"


class ListRepositoryCollaboratorsInput(BaseModel):
    affiliation: Annotated[
        Optional[Affiliation],
        Field(
            description=(
                "Filter by affiliation. Can be one of: 'outside' (outside collaborators), 'direct' (all with"
                " permissions regardless of org membership), 'all' (all collaborators). Default: 'all'"
            )
        ),
    ] = None
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (default 1, min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float],
        Field(description="Results per page for pagination (default 30, min 1, max 100)", ge=1.0, le=100.0),
    ] = None
    repo: Annotated[str, Field(description="Repository name")]


class Direction4(Enum):
    """
    Sort direction.
    """

    ASC = "asc"
    DESC = "desc"


class Sort2(Enum):
    """
    Sort field.
    """

    CREATED = "created"
    UPDATED = "updated"
    PUBLISHED = "published"


class State7(Enum):
    """
    Filter by advisory state.
    """

    TRIAGE = "triage"
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ListRepositorySecurityAdvisoriesInput(BaseModel):
    direction: Annotated[Optional[Direction4], Field(description="Sort direction.")] = None
    owner: Annotated[str, Field(description="The owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]
    sort: Annotated[Optional[Sort2], Field(description="Sort field.")] = None
    state: Annotated[Optional[State7], Field(description="Filter by advisory state.")] = None


class Resolution(Enum):
    """
    Filter by resolution
    """

    FALSE_POSITIVE = "false_positive"
    WONT_FIX = "wont_fix"
    REVOKED = "revoked"
    PATTERN_EDITED = "pattern_edited"
    PATTERN_DELETED = "pattern_deleted"
    USED_IN_TESTS = "used_in_tests"


class State8(Enum):
    """
    Filter by state
    """

    OPEN = "open"
    RESOLVED = "resolved"


class ListSecretScanningAlertsInput(BaseModel):
    owner: Annotated[str, Field(description="The owner of the repository.")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="The name of the repository.")]
    resolution: Annotated[Optional[Resolution], Field(description="Filter by resolution")] = None
    secret_type: Annotated[
        Optional[str],
        Field(
            description=(
                "A comma-separated list of secret types to return. All default secret patterns are returned. To return"
                " generic patterns, pass the token name(s) in the parameter."
            )
        ),
    ] = None
    state: Annotated[Optional[State8], Field(description="Filter by state")] = None


class Direction5(Enum):
    """
    The direction to sort the results by.
    """

    ASC = "asc"
    DESC = "desc"


class Sort3(Enum):
    """
    How to sort the results. Can be either 'created' (when the repository was starred) or 'updated' (when the repository was last pushed to).
    """

    CREATED = "created"
    UPDATED = "updated"


class ListStarredRepositoriesInput(BaseModel):
    direction: Annotated[Optional[Direction5], Field(description="The direction to sort the results by.")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    sort: Annotated[
        Optional[Sort3],
        Field(
            description=(
                "How to sort the results. Can be either 'created' (when the repository was starred) or 'updated' (when"
                " the repository was last pushed to)."
            )
        ),
    ] = None
    username: Annotated[
        Optional[str],
        Field(description="Username to list starred repositories for. Defaults to the authenticated user."),
    ] = None


class ListTagsInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    repo: Annotated[str, Field(description="Repository name")]


class Action(Enum):
    """
    Action to perform: ignore, watch, or delete the notification subscription.
    """

    IGNORE = "ignore"
    WATCH = "watch"
    DELETE = "delete"


class ManageNotificationSubscriptionInput(BaseModel):
    action: Annotated[
        Action, Field(description="Action to perform: ignore, watch, or delete the notification subscription.")
    ]
    notificationID: Annotated[str, Field(description="The ID of the notification thread.")]


class Action1(Enum):
    """
    Action to perform: ignore, watch, or delete the repository notification subscription.
    """

    IGNORE = "ignore"
    WATCH = "watch"
    DELETE = "delete"


class ManageRepositoryNotificationSubscriptionInput(BaseModel):
    action: Annotated[
        Action1,
        Field(description="Action to perform: ignore, watch, or delete the repository notification subscription."),
    ]
    owner: Annotated[str, Field(description="The account owner of the repository.")]
    repo: Annotated[str, Field(description="The name of the repository.")]


class MarkAllNotificationsReadInput(BaseModel):
    lastReadAt: Annotated[
        Optional[str],
        Field(description="Describes the last point that notifications were checked (optional). Default: Now"),
    ] = None
    owner: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository owner. If provided with repo, only notifications for this repository are marked as"
                " read."
            )
        ),
    ] = None
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository name. If provided with owner, only notifications for this repository are marked as"
                " read."
            )
        ),
    ] = None


class MergeMethod(Enum):
    """
    Merge method
    """

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class MergePullRequestInput(BaseModel):
    commit_message: Annotated[Optional[str], Field(description="Extra detail for merge commit")] = None
    commit_title: Annotated[Optional[str], Field(description="Title for merge commit")] = None
    merge_method: Annotated[Optional[MergeMethod], Field(description="Merge method")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]


class Method7(Enum):
    """
    The method to execute
    """

    GET_PROJECT = "get_project"
    GET_PROJECT_FIELD = "get_project_field"
    GET_PROJECT_ITEM = "get_project_item"
    GET_PROJECT_STATUS_UPDATE = "get_project_status_update"


class OwnerType(Enum):
    """
    Owner type (user or org). If not provided, will be automatically detected.
    """

    USER = "user"
    ORG = "org"


class ProjectsGetInput(BaseModel):
    field_id: Annotated[
        Optional[float], Field(description="The field's ID. Required for 'get_project_field' method.")
    ] = None
    fields: Annotated[
        Optional[list[str]],
        Field(
            description=(
                'Specific list of field IDs to include in the response when getting a project item (e.g. ["102589",'
                ' "985201", "169875"]). If not provided, only the title field is included. Only used for'
                " 'get_project_item' method."
            )
        ),
    ] = None
    item_id: Annotated[Optional[float], Field(description="The item's ID. Required for 'get_project_item' method.")] = (
        None
    )
    method: Annotated[Method7, Field(description="The method to execute")]
    owner: Annotated[
        Optional[str], Field(description="The owner (user or organization login). The name is not case sensitive.")
    ] = None
    owner_type: Annotated[
        Optional[OwnerType],
        Field(description="Owner type (user or org). If not provided, will be automatically detected."),
    ] = None
    project_number: Annotated[Optional[float], Field(description="The project's number.")] = None
    status_update_id: Annotated[
        Optional[str],
        Field(description="The node ID of the project status update. Required for 'get_project_status_update' method."),
    ] = None


class Method8(Enum):
    """
    The action to perform
    """

    LIST_PROJECTS = "list_projects"
    LIST_PROJECT_FIELDS = "list_project_fields"
    LIST_PROJECT_ITEMS = "list_project_items"
    LIST_PROJECT_STATUS_UPDATES = "list_project_status_updates"


class OwnerType1(Enum):
    """
    Owner type (user or org). If not provided, will automatically try both.
    """

    USER = "user"
    ORG = "org"


class ProjectsListInput(BaseModel):
    after: Annotated[
        Optional[str], Field(description="Forward pagination cursor from previous pageInfo.nextCursor.")
    ] = None
    before: Annotated[
        Optional[str], Field(description="Backward pagination cursor from previous pageInfo.prevCursor (rare).")
    ] = None
    fields: Annotated[
        Optional[list[str]],
        Field(
            description=(
                'Field IDs to include when listing project items (e.g. ["102589", "985201"]). CRITICAL: Always provide'
                " to get field values. Without this, only titles returned. Only used for 'list_project_items' method."
            )
        ),
    ] = None
    method: Annotated[Method8, Field(description="The action to perform")]
    owner: Annotated[str, Field(description="The owner (user or organization login). The name is not case sensitive.")]
    owner_type: Annotated[
        Optional[OwnerType1],
        Field(description="Owner type (user or org). If not provided, will automatically try both."),
    ] = None
    per_page: Annotated[Optional[float], Field(description="Results per page (max 50)")] = None
    project_number: Annotated[
        Optional[float],
        Field(
            description=(
                "The project's number. Required for 'list_project_fields', 'list_project_items', and"
                " 'list_project_status_updates' methods."
            )
        ),
    ] = None
    query: Annotated[
        Optional[str],
        Field(
            description=(
                'Filter/query string. For list_projects: filter by title text and state (e.g. "roadmap is:open"). For'
                " list_project_items: advanced filtering using GitHub's project filtering syntax."
            )
        ),
    ] = None


class ItemType(Enum):
    """
    The item's type, either issue or pull_request. Required for 'add_project_item' method.
    """

    ISSUE = "issue"
    PULL_REQUEST = "pull_request"


class Iteration(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    duration: Annotated[float, Field(description="Duration in days")]
    start_date: Annotated[str, Field(description="Start date in YYYY-MM-DD format")]
    title: Annotated[str, Field(description="Iteration title (e.g. 'Sprint 1')")]


class Method9(Enum):
    """
    The method to execute
    """

    ADD_PROJECT_ITEM = "add_project_item"
    UPDATE_PROJECT_ITEM = "update_project_item"
    DELETE_PROJECT_ITEM = "delete_project_item"
    CREATE_PROJECT_STATUS_UPDATE = "create_project_status_update"
    CREATE_PROJECT = "create_project"
    CREATE_ITERATION_FIELD = "create_iteration_field"


class OwnerType2(Enum):
    """
    Owner type (user or org). Required for 'create_project' method. If not provided for other methods, will be automatically detected.
    """

    USER = "user"
    ORG = "org"


class Status1(Enum):
    """
    The status of the project. Used for 'create_project_status_update' method.
    """

    INACTIVE = "INACTIVE"
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    OFF_TRACK = "OFF_TRACK"
    COMPLETE = "COMPLETE"


class ProjectsWriteInput(BaseModel):
    body: Annotated[
        Optional[str],
        Field(description="The body of the status update (markdown). Used for 'create_project_status_update' method."),
    ] = None
    field_name: Annotated[
        Optional[str],
        Field(
            description="The name of the iteration field (e.g. 'Sprint'). Required for 'create_iteration_field' method."
        ),
    ] = None
    issue_number: Annotated[
        Optional[float],
        Field(
            description=(
                "The issue number (use when item_type is 'issue' for 'add_project_item' method). Provide either"
                " issue_number or pull_request_number."
            )
        ),
    ] = None
    item_id: Annotated[
        Optional[float],
        Field(description="The project item ID. Required for 'update_project_item' and 'delete_project_item' methods."),
    ] = None
    item_owner: Annotated[
        Optional[str],
        Field(
            description=(
                "The owner (user or organization) of the repository containing the issue or pull request. Required for"
                " 'add_project_item' method."
            )
        ),
    ] = None
    item_repo: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the repository containing the issue or pull request. Required for 'add_project_item'"
                " method."
            )
        ),
    ] = None
    item_type: Annotated[
        Optional[ItemType],
        Field(description="The item's type, either issue or pull_request. Required for 'add_project_item' method."),
    ] = None
    iteration_duration: Annotated[
        Optional[float],
        Field(
            description=(
                "Duration in days for iterations of the field (e.g. 7 for weekly, 14 for bi-weekly). Required for"
                " 'create_iteration_field' method."
            )
        ),
    ] = None
    iterations: Annotated[
        Optional[list[Iteration]],
        Field(
            description=(
                "Custom iterations for 'create_iteration_field' method. Only set this when you need iterations with"
                " varying durations, breaks between them, or specific titles. Otherwise omit it: GitHub auto-creates"
                " three iterations of 'iteration_duration' days starting on 'start_date', which is the right choice for"
                " most cases."
            )
        ),
    ] = None
    method: Annotated[Method9, Field(description="The method to execute")]
    owner: Annotated[
        str, Field(description="The project owner (user or organization login). The name is not case sensitive.")
    ]
    owner_type: Annotated[
        Optional[OwnerType2],
        Field(
            description=(
                "Owner type (user or org). Required for 'create_project' method. If not provided for other methods,"
                " will be automatically detected."
            )
        ),
    ] = None
    project_number: Annotated[
        Optional[float], Field(description="The project's number. Required for all methods except 'create_project'.")
    ] = None
    pull_request_number: Annotated[
        Optional[float],
        Field(
            description=(
                "The pull request number (use when item_type is 'pull_request' for 'add_project_item' method). Provide"
                " either issue_number or pull_request_number."
            )
        ),
    ] = None
    start_date: Annotated[
        Optional[str],
        Field(
            description=(
                "Start date in YYYY-MM-DD format. Used for 'create_project_status_update' and 'create_iteration_field'"
                " methods."
            )
        ),
    ] = None
    status: Annotated[
        Optional[Status1],
        Field(description="The status of the project. Used for 'create_project_status_update' method."),
    ] = None
    target_date: Annotated[
        Optional[str],
        Field(
            description=(
                "The target date of the status update in YYYY-MM-DD format. Used for 'create_project_status_update'"
                " method."
            )
        ),
    ] = None
    title: Annotated[Optional[str], Field(description="The project title. Required for 'create_project' method.")] = (
        None
    )
    updated_field: Annotated[
        Optional[dict[str, Any]],
        Field(
            description=(
                "Object consisting of the ID of the project field to update and the new value for the field. To clear"
                ' the field, set value to null. Example: {"id": 123456, "value": "New Value"}. Required for'
                " 'update_project_item' method."
            )
        ),
    ] = None


class Method10(Enum):
    """
    Action to specify what pull request data needs to be retrieved from GitHub. Possible options: 1. get - Get
    details of a specific pull request. 2. get_diff - Get the diff of a pull request. 3. get_status - Get combined
    commit status of a head commit in a pull request. 4. get_files - Get the list of files changed in a pull request.
    Use with pagination parameters to control the number of results returned. 5. get_commits - Get the list of
    commits on a pull request. Use with pagination parameters to control the number of results returned. 6.
    get_review_comments - Get review threads on a pull request. Each thread contains logically grouped review
    comments made on the same code location during pull request reviews. Returns threads with metadata (isResolved,
    isOutdated, isCollapsed) and their associated comments. Use cursor-based pagination (perPage, after) to control
    results. 7. get_reviews - Get the reviews on a pull request. When asked for review comments,
    use get_review_comments method. Use with pagination parameters to control the number of results returned. 8.
    get_comments - Get comments on a pull request. Use this if user doesn't specifically want review comments. Use
    with pagination parameters to control the number of results returned. 9. get_check_runs - Get check runs for the
    head commit of a pull request. Check runs are the individual CI/CD jobs and checks that run on the PR.

    """

    GET = "get"
    GET_DIFF = "get_diff"
    GET_STATUS = "get_status"
    GET_FILES = "get_files"
    GET_COMMITS = "get_commits"
    GET_REVIEW_COMMENTS = "get_review_comments"
    GET_REVIEWS = "get_reviews"
    GET_COMMENTS = "get_comments"
    GET_CHECK_RUNS = "get_check_runs"


class PullRequestReadInput(BaseModel):
    after: Annotated[
        Optional[str],
        Field(
            description=(
                "Cursor for pagination, used only by the get_review_comments method. Pass the endCursor from the"
                " previous page's PageInfo to fetch the next page."
            )
        ),
    ] = None
    method: Annotated[
        Method10,
        Field(
            description=(
                "Action to specify what pull request data needs to be retrieved from GitHub. \nPossible options: \n 1."
                " get - Get details of a specific pull request.\n 2. get_diff - Get the diff of a pull request.\n 3."
                " get_status - Get combined commit status of a head commit in a pull request.\n 4. get_files - Get the"
                " list of files changed in a pull request. Use with pagination parameters to control the number of"
                " results returned.\n 5. get_commits - Get the list of commits on a pull request. Use with pagination"
                " parameters to control the number of results returned.\n 6. get_review_comments - Get review threads"
                " on a pull request. Each thread contains logically grouped review comments made on the same code"
                " location during pull request reviews. Returns threads with metadata (isResolved, isOutdated,"
                " isCollapsed) and their associated comments. Use cursor-based pagination (perPage, after) to control"
                " results.\n 7. get_reviews - Get the reviews on a pull request. When asked for review comments, use"
                " get_review_comments method. Use with pagination parameters to control the number of results"
                " returned.\n 8. get_comments - Get comments on a pull request. Use this if user doesn't specifically"
                " want review comments. Use with pagination parameters to control the number of results returned.\n 9."
                " get_check_runs - Get check runs for the head commit of a pull request. Check runs are the individual"
                " CI/CD jobs and checks that run on the PR.\n"
            )
        ),
    ]
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]


class Event1(Enum):
    """
    Review action to perform.
    """

    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class Method11(Enum):
    """
    The write operation to perform on pull request review.
    """

    CREATE = "create"
    SUBMIT_PENDING = "submit_pending"
    DELETE_PENDING = "delete_pending"
    RESOLVE_THREAD = "resolve_thread"
    UNRESOLVE_THREAD = "unresolve_thread"


class PullRequestReviewWriteInput(BaseModel):
    body: Annotated[Optional[str], Field(description="Review comment text")] = None
    commitID: Annotated[Optional[str], Field(description="SHA of commit to review")] = None
    event: Annotated[Optional[Event1], Field(description="Review action to perform.")] = None
    method: Annotated[Method11, Field(description="The write operation to perform on pull request review.")]
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]
    threadId: Annotated[
        Optional[str],
        Field(
            description=(
                "The node ID of the review thread (e.g., PRRT_kwDOxxx). Required for resolve_thread and"
                " unresolve_thread methods. Get thread IDs from pull_request_read with method get_review_comments."
            )
        ),
    ] = None


class File(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    content: Annotated[str, Field(description="file content")]
    path: Annotated[str, Field(description="path to the file")]


class PushFilesInput(BaseModel):
    branch: Annotated[str, Field(description="Branch to push to")]
    files: Annotated[
        list[File],
        Field(description="Array of file objects to push, each object with path (string) and content (string)"),
    ]
    message: Annotated[str, Field(description="Commit message")]
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class RequestCopilotReviewInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]


class Files(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description=(
                "A single string or an array of strings containing file contents, snippets, or diff hunks to scan for"
                " secrets. These must be raw contents, not repository file paths."
            ),
            min_length=1,
        ),
    ]


class Files1(RootModel[list[str]]):
    root: Annotated[
        list[str],
        Field(
            description=(
                "A single string or an array of strings containing file contents, snippets, or diff hunks to scan for"
                " secrets. These must be raw contents, not repository file paths."
            ),
            max_length=100,
            min_length=1,
        ),
    ]


class RunSecretScanningInput(BaseModel):
    files: Annotated[
        Union[Files, Files1],
        Field(
            description=(
                "A single string or an array of strings containing file contents, snippets, or diff hunks to scan for"
                " secrets. These must be raw contents, not repository file paths."
            )
        ),
    ]
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class Order(Enum):
    """
    Sort order for results
    """

    ASC = "asc"
    DESC = "desc"


class SearchCodeInput(BaseModel):
    order: Annotated[Optional[Order], Field(description="Sort order for results")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[
        str,
        Field(
            description=(
                'Search query (GitHub code search REST). Implicit AND between terms; supports `OR`, `NOT`, and `"quoted'
                ' phrase"` for exact match. Qualifiers: `repo:owner/repo`, `org:`, `user:`, `language:`, `path:dir`'
                " (prefix match), `filename:exact.ext`, `extension:`, `in:file`, `in:path`, `size:`, `is:archived`,"
                ' `is:fork`. Max 256 chars. Examples: `WithContext language:go org:github`; `"package main" repo:o/r`;'
                " `func extension:go path:cmd repo:o/r`; `NOT TODO language:go repo:o/r`."
            )
        ),
    ]
    sort: Annotated[Optional[str], Field(description="Sort field ('indexed' only)")] = None


class Order1(Enum):
    """
    Sort order
    """

    ASC = "asc"
    DESC = "desc"


class Sort4(Enum):
    """
    Sort by author or committer date (defaults to best match)
    """

    AUTHOR_DATE = "author-date"
    COMMITTER_DATE = "committer-date"


class SearchCommitsInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[
        str,
        Field(
            description=(
                "Commit search query (GitHub commit search REST). Searches commit messages on the default branch only."
                " Scope the search with `repo:owner/repo`, `org:`, or `user:` (queries without a scope qualifier match"
                " across all of GitHub and are usually not what you want). Other qualifiers: `author:`, `committer:`,"
                " `author-name:`, `committer-name:`, `author-email:`, `committer-email:`, `author-date:`,"
                " `committer-date:` (supports `>`, `<`, `>=`, `<=`, and `YYYY-MM-DD..YYYY-MM-DD` ranges),"
                " `merge:true|false`, `hash:`, `tree:`, `parent:`, `is:public`. Examples: `repo:owner/repo fix panic`;"
                ' `org:github author:defunkt committer-date:>=2024-01-01`; `"refactor cache" repo:o/r`; `hash:abc1234'
                " repo:o/r`."
            )
        ),
    ]
    sort: Annotated[Optional[Sort4], Field(description="Sort by author or committer date (defaults to best match)")] = (
        None
    )


class Sort5(Enum):
    """
    Sort field by number of matches of categories, defaults to best match
    """

    COMMENTS = "comments"
    REACTIONS = "reactions"
    REACTIONS__1 = "reactions-+1"
    reactions__1_1 = "reactions--1"
    REACTIONS_SMILE = "reactions-smile"
    REACTIONS_THINKING_FACE = "reactions-thinking_face"
    REACTIONS_HEART = "reactions-heart"
    REACTIONS_TADA = "reactions-tada"
    INTERACTIONS = "interactions"
    CREATED = "created"
    UPDATED = "updated"


class SearchIssuesInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    owner: Annotated[
        Optional[str],
        Field(
            description="Optional repository owner. If provided with repo, only issues for this repository are listed."
        ),
    ] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[str, Field(description="Search query using GitHub issues search syntax")]
    repo: Annotated[
        Optional[str],
        Field(
            description="Optional repository name. If provided with owner, only issues for this repository are listed."
        ),
    ] = None
    sort: Annotated[
        Optional[Sort5], Field(description="Sort field by number of matches of categories, defaults to best match")
    ] = None


class Sort6(Enum):
    """
    Sort field by category
    """

    FOLLOWERS = "followers"
    REPOSITORIES = "repositories"
    JOINED = "joined"


class SearchOrgsInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[
        str,
        Field(
            description=(
                "Organization search query. Examples: 'microsoft', 'location:california', 'created:>=2025-01-01'."
                " Search is automatically scoped to type:org."
            )
        ),
    ]
    sort: Annotated[Optional[Sort6], Field(description="Sort field by category")] = None


class Sort7(Enum):
    """
    Sort field by number of matches of categories, defaults to best match
    """

    COMMENTS = "comments"
    REACTIONS = "reactions"
    REACTIONS__1 = "reactions-+1"
    reactions__1_1 = "reactions--1"
    REACTIONS_SMILE = "reactions-smile"
    REACTIONS_THINKING_FACE = "reactions-thinking_face"
    REACTIONS_HEART = "reactions-heart"
    REACTIONS_TADA = "reactions-tada"
    INTERACTIONS = "interactions"
    CREATED = "created"
    UPDATED = "updated"


class SearchPullRequestsInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    owner: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository owner. If provided with repo, only pull requests for this repository are listed."
            )
        ),
    ] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[str, Field(description="Search query using GitHub pull request search syntax")]
    repo: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional repository name. If provided with owner, only pull requests for this repository are listed."
            )
        ),
    ] = None
    sort: Annotated[
        Optional[Sort7], Field(description="Sort field by number of matches of categories, defaults to best match")
    ] = None


class Sort8(Enum):
    """
    Sort repositories by field, defaults to best match
    """

    STARS = "stars"
    FORKS = "forks"
    HELP_WANTED_ISSUES = "help-wanted-issues"
    UPDATED = "updated"


class SearchRepositoriesInput(BaseModel):
    minimal_output: Annotated[
        Optional[bool],
        Field(
            description=(
                "Return minimal repository information (default: true). When false, returns full GitHub API repository"
                " objects."
            )
        ),
    ] = True
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[
        str,
        Field(
            description=(
                "Repository search query. Examples: 'machine learning in:name stars:>1000 language:python',"
                " 'topic:react', 'user:facebook'. Supports advanced search syntax for precise filtering."
            )
        ),
    ]
    sort: Annotated[Optional[Sort8], Field(description="Sort repositories by field, defaults to best match")] = None


class Sort9(Enum):
    """
    Sort users by number of followers or repositories, or when the person joined GitHub.
    """

    FOLLOWERS = "followers"
    REPOSITORIES = "repositories"
    JOINED = "joined"


class SearchUsersInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    perPage: Annotated[
        Optional[float], Field(description="Results per page for pagination (min 1, max 100)", ge=1.0, le=100.0)
    ] = None
    query: Annotated[
        str,
        Field(
            description=(
                "User search query. Examples: 'john smith', 'location:seattle', 'followers:>100'. Search is"
                " automatically scoped to type:user."
            )
        ),
    ]
    sort: Annotated[
        Optional[Sort9],
        Field(description="Sort users by number of followers or repositories, or when the person joined GitHub."),
    ] = None


class SemanticIssueSimilaritySearchInput(BaseModel):
    issue_number: Annotated[float, Field(description="The issue number to find similar issues for", ge=1.0)]
    owner: Annotated[str, Field(description="Repository owner")]
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    per_page: Annotated[
        Optional[float],
        Field(description="Number of similar issues to return per page (default: 3, max: 10)", ge=1.0, le=10.0),
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    threshold: Annotated[
        Optional[float], Field(description="Similarity threshold between 0.0 and 1.0 (default: 0.80)", ge=0.0, le=1.0)
    ] = None


class Sort10(Enum):
    """
    Sort field for search results. Defaults to best match.
    """

    COMMENTS = "comments"
    REACTIONS = "reactions"
    REACTIONS__1 = "reactions-+1"
    reactions__1_1 = "reactions--1"
    REACTIONS_SMILE = "reactions-smile"
    REACTIONS_THINKING_FACE = "reactions-thinking_face"
    REACTIONS_HEART = "reactions-heart"
    REACTIONS_TADA = "reactions-tada"
    INTERACTIONS = "interactions"
    CREATED = "created"
    UPDATED = "updated"


class SemanticIssuesSearchInput(BaseModel):
    order: Annotated[Optional[Order1], Field(description="Sort order")] = None
    owner: Annotated[Optional[str], Field(description="Repository owner. Required if `repo` is specified.")] = None
    page: Annotated[Optional[float], Field(description="Page number for pagination (min 1)", ge=1.0)] = None
    query: Annotated[
        str,
        Field(
            description=(
                "Natural language query with optional GitHub search qualifiers. Supports semantic matching. Examples:"
                " 'authentication login errors', 'state:open author:username performance issues'. Supports advanced"
                " GitHub issue search syntax for filtering by state, author, labels, etc."
            )
        ),
    ]
    repo: Annotated[Optional[str], Field(description="Repository name. Required if `owner` is specified.")] = None
    sort: Annotated[Optional[Sort10], Field(description="Sort field for search results. Defaults to best match.")] = (
        None
    )


class StarRepositoryInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class SubIssueWriteInput(BaseModel):
    after_id: Annotated[
        Optional[float],
        Field(
            description=(
                "The ID of the sub-issue to be prioritized after (either after_id OR before_id should be specified)"
            )
        ),
    ] = None
    before_id: Annotated[
        Optional[float],
        Field(
            description=(
                "The ID of the sub-issue to be prioritized before (either after_id OR before_id should be specified)"
            )
        ),
    ] = None
    issue_number: Annotated[float, Field(description="The number of the parent issue")]
    method: Annotated[
        str,
        Field(
            description=(
                "The action to perform on a single sub-issue\nOptions are:\n- 'add' - add a sub-issue to a parent issue"
                " in a GitHub repository.\n- 'remove' - remove a sub-issue from a parent issue in a GitHub"
                " repository.\n- 'reprioritize' - change the order of sub-issues within a parent issue in a GitHub"
                " repository. Use either 'after_id' or 'before_id' to specify the new position.\n\t\t\t\t"
            )
        ),
    ]
    owner: Annotated[str, Field(description="Repository owner")]
    replace_parent: Annotated[
        Optional[bool],
        Field(description="When true, replaces the sub-issue's current parent issue. Use with 'add' method only."),
    ] = None
    repo: Annotated[str, Field(description="Repository name")]
    sub_issue_id: Annotated[
        float, Field(description="The ID of the sub-issue to add. ID is not the same as issue number")
    ]


class FieldModel(BaseModel):
    name: Annotated[str, Field(description="Field name")]
    value: Annotated[Any, Field(description="Field value (string, number, or other supported type)")]


class TriageIssueInput(BaseModel):
    fields: Annotated[Optional[list[FieldModel]], Field(description="Custom fields to set on the issue (optional)")] = (
        None
    )
    issue_number: Annotated[float, Field(description="The issue number to triage", ge=1.0)]
    labels: Annotated[Optional[list[str]], Field(description="Labels to apply to the issue (optional)")] = None
    owner: Annotated[str, Field(description="Repository owner (username or organization)")]
    repo: Annotated[str, Field(description="Repository name")]
    triage_rationale: Annotated[
        str,
        Field(
            description=(
                "The triage comment body containing analysis and rationale. This will be posted as a comment on the"
                " issue."
            )
        ),
    ]
    type: Annotated[
        Optional[str], Field(description="The issue type to set (optional, e.g., 'bug', 'feature_request')")
    ] = None


class UnstarRepositoryInput(BaseModel):
    owner: Annotated[str, Field(description="Repository owner")]
    repo: Annotated[str, Field(description="Repository name")]


class UpdateGistInput(BaseModel):
    content: Annotated[str, Field(description="Content for the file")]
    description: Annotated[Optional[str], Field(description="Updated description of the gist")] = None
    filename: Annotated[str, Field(description="Filename to update or create")]
    gist_id: Annotated[str, Field(description="ID of the gist to update")]


class State9(Enum):
    """
    New state
    """

    OPEN = "open"
    CLOSED = "closed"


class UpdatePullRequestInput(BaseModel):
    base: Annotated[Optional[str], Field(description="New base branch name")] = None
    body: Annotated[Optional[str], Field(description="New description")] = None
    draft: Annotated[
        Optional[bool], Field(description="Mark pull request as draft (true) or ready for review (false)")
    ] = None
    maintainer_can_modify: Annotated[Optional[bool], Field(description="Allow maintainer edits")] = None
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number to update")]
    repo: Annotated[str, Field(description="Repository name")]
    reviewers: Annotated[
        Optional[list[str]],
        Field(description="GitHub usernames or ORG/team-slug team reviewers to request reviews from"),
    ] = None
    state: Annotated[Optional[State9], Field(description="New state")] = None
    title: Annotated[Optional[str], Field(description="New title")] = None


class UpdatePullRequestBranchInput(BaseModel):
    expectedHeadSha: Annotated[Optional[str], Field(description="The expected SHA of the pull request's HEAD ref")] = (
        None
    )
    owner: Annotated[str, Field(description="Repository owner")]
    pullNumber: Annotated[float, Field(description="Pull request number")]
    repo: Annotated[str, Field(description="Repository name")]
