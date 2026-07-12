"""
Auto-generated Pydantic models for monday's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.monday.com/mcp"
   },
   "tools": [
     {
       "name": "get_board_items_page",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetBoardItemsPageInput",
       "description": "Get all items from a monday.com board with pagination support and optional column values and item descriptions. Returns structured JSON with item details, creation/update timestamps, and pagination info. Use the nextCursor parameter from the response to get the next page of results when has_more is true. To retrieve an item description (the rich-text body/details of a monday.com item), set includeItemDescription to true \u2014 the response will include the item description document blocks with their content, type, and id. Use this whenever the user asks about an item description, body, details, or notes. [REQUIRED PRECONDITION]: Before using this tool, if new columns were added to the board or if you are not familiar with the board structure (column IDs, column types, status labels, etc.), first use get_board_info to understand the board metadata. This is essential for constructing proper filters and knowing which columns are available. [REQUIRED PRECONDITION]: For board-relation / cross-board linking tasks, call link_board_items_workflow before using this tool. VIEW-BASED FILTERING: If the user refers to a board view by name (e.g. \"show me items in the Overdue view\"), first call get_board_info to get the board views, find the matching view by name, then extract its filter field and pass it as the filters argument here."
     },
     {
       "name": "create_item",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateItemInput",
       "description": "Create a new item with provided values, create a subitem under a parent item, or duplicate an existing item and update it with new values. Use parentItemId when creating a subitem under an existing item. Use duplicateFromItemId when copying an existing item with modifications.[REQUIRED PRECONDITION]: Before using this tool, if new columns were added to the board or if you are not familiar with the board's structure (column IDs, column types, status labels, etc.), first use get_board_info to understand the board metadata. This is essential for constructing proper column values and knowing which columns are available."
     },
     {
       "name": "create_update",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateUpdateInput",
       "description": "Create a new update (comment/post) on a monday.com item. Updates can be used to add comments, notes, or discussions to items. You can optionally mention users, teams, or boards in the update. You can also reply to an existing update by using the parentId parameter."
     },
     {
       "name": "get_updates",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetUpdatesInput",
       "description": "Get updates (comments/posts) from a monday.com item or board. Specify objectId and objectType (Item or Board) to retrieve updates. For Board queries, you can filter by date range using fromDate and toDate (both required together, ISO8601 format). By default, Board queries return only board discussion. Set includeItemUpdates to true to also include updates on individual items. Returns update text, creator info, timestamps, and optionally replies and assets."
     },
     {
       "name": "get_board_activity",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetBoardActivityInput",
       "description": "Get board activity logs for a specified time range (defaults to last 30 days). Optionally filter by item ids or user ids to avoid fetching activity for the entire board."
     },
     {
       "name": "get_board_info",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetBoardInfoInput",
       "description": "Get comprehensive board information including metadata, structure, owners, and configuration. Also returns the board's views (e.g. table views, filter views) \u2014 each view includes its id, name, type, and a structured filter object. "
     },
     {
       "name": "list_users_and_teams",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ListUsersAndTeamsInput",
       "description": "Tool to fetch users and/or teams data. \n\n      MANDATORY BEST PRACTICES:\n      1. ALWAYS use specific IDs or names when available\n      2. If no ids available, use name search if possible (USERS ONLY)\n      3. Use 'getMe: true' to get current user information\n      4. AVOID broad queries (no parameters) - use only as last resort\n\n      REQUIRED PARAMETER PRIORITY (use in this order):\n      1. getMe - STANDALONE\n      2. userIds\n      3. name - STANDALONE (USERS ONLY, NOT for teams)\n      4. teamIds + teamsOnly\n      5. No parameters - LAST RESORT\n\n      CRITICAL USAGE RULES:\n      \u2022 userIds + teamIds requires explicit includeTeams: true flag\n      \u2022 includeTeams: true fetches both users and teams, do not use this to fetch a specific user's teams rather fetch that user by id and you will get their team memberships.\n      \u2022 name parameter is for USER search ONLY - it cannot be used to search for teams. Use teamIds to fetch specific teams."
     },
     {
       "name": "change_item_column_values",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ChangeItemColumnValuesInput",
       "description": "Change the column values of an item in a monday.com board. [REQUIRED PRECONDITION]: For board-relation linking tasks, call link_board_items_workflow before using this tool."
     },
     {
       "name": "create_board",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateBoardInput",
       "description": "Create a monday.com board"
     },
     {
       "name": "create_form",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateFormInput",
       "description": "Create a monday.com form. Also creates a backing board to store responses. Returns the formToken for future mutations."
     },
     {
       "name": "update_form",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateFormInput",
       "description": "Update a monday.com form. Use the action field to specify the operation."
     },
     {
       "name": "get_form",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetFormInput",
       "description": "Get a monday.com form by its form token. Form tokens can be extracted from the form's url. Given a form url, such as https://forms.monday.com/forms/abc123def456ghi789?r=use1, the formToken is the alphanumeric string that appears right after /forms/ and before the ?. In the example, the formToken is abc123def456ghi789."
     },
     {
       "name": "form_questions_editor",
       "input_class_name": "rustic_ai.mcp.connectors.monday.FormQuestionsEditorInput",
       "description": "Create, update, or delete a question in a monday.com form"
     },
     {
       "name": "create_form_submission",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateFormSubmissionInput",
       "description": "Submit a response to a monday.com WorkForm. Use get_form first to retrieve the WorkForm, then:\n- Inspect each question's showIfRules to determine which questions are conditionally shown based on previous answers.\n- Inspect each question's settings for any answer constraints (e.g. rating limits, select options, label limits).\n- Take note of any titles, descriptions, and content blocks to present the form naturally as you walk the user through it.\n- Take note of pages and question order to present questions in the correct sequence.\nGather all answers upfront before calling this tool \u2014 do not submit one question at a time. Accepts a bare form token, a full WorkForm URL (e.g. https://forms.monday.com/forms/{form_token}?r=use1), or a shortened wkf.ms URL (e.g. https://wkf.ms/4tqP28t) \u2014 shortened URLs are automatically resolved by following the redirect. Returns the submission ID."
     },
     {
       "name": "create_column",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateColumnInput",
       "description": "Create a new column in a monday.com board"
     },
     {
       "name": "create_group",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateGroupInput",
       "description": "Create a new group in a monday.com board. Groups are sections that organize related items. Use when users want to add structure, categorize items, or create workflow phases. Groups can be positioned relative to existing groups and assigned predefined colors. Items will always be created in the top group and so the top group should be the most relevant one for new item creation"
     },
     {
       "name": "all_monday_api",
       "input_class_name": "rustic_ai.mcp.connectors.monday.AllMondayApiInput",
       "description": "Execute any monday.com API operation by generating GraphQL queries and mutations dynamically. Make sure you ask only for the fields you need and nothing more. When providing the query/mutation - use get_graphql_schema and get_type_details tools first to understand the schema before crafting your query."
     },
     {
       "name": "get_graphql_schema",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetGraphqlSchemaInput",
       "description": "Fetch the monday.com GraphQL schema structure including query and mutation definitions. This tool returns available query fields, mutation fields, and a list of GraphQL types in the schema. You can filter results by operation type (read/write) to focus on either queries or mutations."
     },
     {
       "name": "get_column_type_info",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetColumnTypeInfoInput",
       "description": "Retrieves comprehensive information about a specific column type. Use fetchMode \"schema\" (default) to get the JSON schema definition from the API \u2014 use this before creating or updating columns (e.g. create_column) to understand structure, validation rules, and available properties for column settings. Use fetchMode \"guidelines\" to get only guidelines.filter and guidelines.aggregation for building items_page filters and board insights counts (no schema, no GraphQL round-trip). "
     },
     {
       "name": "get_type_details",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetTypeDetailsInput",
       "description": "Get detailed information about a specific GraphQL type from the monday.com API schema"
     },
     {
       "name": "create_notification",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateNotificationInput",
       "description": "Send a notification to a user via the bell icon and optionally by email. Use target_type \"Post\" for updates/replies or \"Project\" for items/boards."
     },
     {
       "name": "read_docs",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ReadDocsInput",
       "description": "Get information about monday.com documents. Supports two modes:\n\nMODE: \"content\" (default) \u2014 Fetch documents with their full markdown content.\n- Requires: type (\"ids\" | \"object_ids\" | \"workspace_ids\") and ids array\n- Supports pagination via page/limit. Check has_more_pages in response.\n- If type \"ids\" returns no results, automatically retries with object_ids.\n- Set include_blocks: true to include block IDs, types, and positions in the response \u2014 required before calling update_doc.\n- Blocks default to 25 per page. Use blocks_limit and blocks_page to paginate through long documents.\n- Set include_comments: true to fetch all comments and replies on the document. Each comment is enriched with anchor info (block_id, selection_from, selection_length) indicating which block and text range it's attached to. Use comments_limit to control how many comments per item (default 50).\n\nMODE: \"version_history\" \u2014 Fetch the edit history of a single document.\n- Requires: ids with the document's object_id (use the object_id field from content mode results, NOT the id field).\n- The object_id is the numeric ID visible in the document URL.\n- Returns restoring points sorted newest-first. Use version_history_limit to cap results (e.g., \"last 3 changes\" \u2192 version_history_limit: 3).\n- Use since/until to filter by time range. If omitted, returns full history.\n- Set include_diff: true to see what content changed between versions (fetches up to 10 diffs, may be slower).\n- Examples:\n  - { mode: \"version_history\", ids: [\"5001466606\"], version_history_limit: 3 }\n  - { mode: \"version_history\", ids: [\"5001466606\"], since: \"2026-03-11T00:00:00Z\", include_diff: true }"
     },
     {
       "name": "workspace_info",
       "input_class_name": "rustic_ai.mcp.connectors.monday.WorkspaceInfoInput",
       "description": "This tool returns the boards, docs and folders in a workspace and which folder they are in. It returns up to 100 of each object type, if you receive 100 assume there are additional objects of that type in the workspace."
     },
     {
       "name": "list_workspaces",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ListWorkspacesInput",
       "description": "List all workspaces available to the user, ordered by membership (user's workspaces first). Returns workspaces with their ID, name, and description.\n[IMPORTANT] To search for workspaces by name, use the \"search\" tool with searchType WORKSPACES instead \u2014 it provides faster and more accurate results."
     },
     {
       "name": "create_doc",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateDocInput",
       "description": "Create a new monday.com doc either inside a workspace or attached to an item (via a doc column). After creation, the provided markdown will be appended to the document.\n\nLOCATION TYPES:\n- workspace: Creates a document in a workspace (requires workspace_id, optional doc_kind, optional folder_id, optional docOwnerIds)\n- item: Creates a document attached to an item (requires item_id, optional column_id, optional docOwnerIds)\n\nUSAGE EXAMPLES:\n- Workspace doc: { location: \"workspace\", workspace_id: 123, doc_name: \"My Doc\", doc_kind: \"private\" , markdown: \"...\" }\n- Workspace doc in folder: { location: \"workspace\", workspace_id: 123, doc_name: \"My Doc\", folder_id: 17264196 , markdown: \"...\" }\n- Item doc: { location: \"item\", item_id: 456, doc_name: \"My Doc\", column_id: \"doc_col_1\" , markdown: \"...\" }\n- Workspace doc with agent owner: { location: \"workspace\", workspace_id: 123, doc_name: \"My Doc\", markdown: \"...\", docOwnerIds: [\"<agent_owner_user_id>\"] }"
     },
     {
       "name": "update_doc",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateDocInput",
       "description": "Update an existing monday.com document. Provide doc_id (preferred) or object_id, plus an ordered operations array (executed sequentially, stops on first failure).\n\nOPERATIONS:\n- set_name: Rename the document.\n- add_markdown_content: Append markdown as blocks (or insert after a block). Best for text, headings, lists, simple tables \u2014 no block IDs needed.\n- update_block: Update content of an existing text, code, or list_item block in-place.\n- create_block: Create a new block at a precise position. Use parent_block_id to nest inside notice_box, table cell, or layout cell.\n- delete_block: Remove any block. The ONLY option for BOARD, WIDGET, DOC embed, and GIPHY blocks.\n- replace_block: Delete a block and create a new one in its place (use when update_block is not supported).\n- add_comment: Create a new comment or reply on the document (doc-level, block-level, or text-selection).\n\nWHEN TO USE EACH OPERATION:\n- text / code / list_item \u2192 update_block. Use replace_block to change subtype (e.g. NORMAL_TEXT\u2192LARGE_TITLE)\n- divider / table / image / video / notice_box / layout \u2192 replace_block (properties immutable after creation)\n- BOARD / WIDGET / DOC / GIPHY \u2192 delete_block only\n\nGETTING BLOCK IDs: Call read_docs with include_blocks: true \u2014 returns id, type, position, and content per block.\n\nBLOCK CONTENT (delta_format): Array of insert ops. Last op MUST be {insert: {text: \"\\n\"}}.\n- Plain: [{insert: {text: \"Hello\"}}, {insert: {text: \"\\n\"}}]\n- Bold: [{insert: {text: \"Hi\"}, attributes: {bold: true}}, {insert: {text: \"\\n\"}}]\n- Mention user/doc/board: [{insert: {text: \"Hey \"}}, {insert: {mention: {id: 12345, type: \"USER\"}}}, {insert: {text: \"\\n\"}}] \u2014 type is USER, DOC, or BOARD. id is numeric (user IDs from list_users_and_teams)\n- Inline column value: [{insert: {column_value: {item_id: 111, column_id: \"status\"}}}, {insert: {text: \"\\n\"}}]\n- Supported attributes: bold, italic, underline, strike, code, link, color, background (not applicable to mention/column_value ops)\n\nIMAGE WITH ASSET: For asset-based images, use create_block with block_type \"image\" and asset_id (instead of public_url). add_markdown_content does NOT support asset images \u2014 for mixed content, alternate add_markdown_content (text) and create_block (image) operations in sequence.\n\nCOMMENTS:\n- add_comment: Create a new comment or reply on the document. Three scopes:\n  - Doc-level (no block_id): comment appears on the doc as a whole.\n  - Block-level (block_id only): comment is anchored to a specific block. The block shows a comment indicator in the UI.\n  - Text-selection (block_id + selection_from + selection_length): comment is anchored to a specific character range inside a text/code/list_item block. That text is highlighted with a comment marker.\n  Block-level and text-selection comments only work on blocks with text content (text, code, list_item, title, quote). They do NOT work on: divider, page_break, table, layout, notice_box, image, video, or giphy blocks.\n  Get block IDs from read_docs with include_blocks: true. Format body with HTML, not markdown. Use mentions_list for @mentions."
     },
     {
       "name": "update_workspace",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateWorkspaceInput",
       "description": "Update an existing workspace in monday.com"
     },
     {
       "name": "update_folder",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateFolderInput",
       "description": "Update an existing folder in monday.com"
     },
     {
       "name": "create_workspace",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateWorkspaceInput",
       "description": "Create a new workspace in monday.com"
     },
     {
       "name": "create_folder",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateFolderInput",
       "description": "Create a new folder in a monday.com workspace"
     },
     {
       "name": "move_object",
       "input_class_name": "rustic_ai.mcp.connectors.monday.MoveObjectInput",
       "description": "Move a folder, board, or overview in monday.com. Use position for relative placement based on another object, parentFolderId for folder changes, workspaceId for workspace moves, and accountProductId for account product changes."
     },
     {
       "name": "create_dashboard",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateDashboardInput",
       "description": "Use this tool to create a new monday.com dashboard that aggregates data from one or more boards. \n    Dashboards provide visual representations of board data through widgets and charts.\n    \n    Use this tool when users want to:\n    - Create a dashboard to visualize board data\n    - Aggregate information from multiple boards\n    - Set up a data visualization container for widgets"
     },
     {
       "name": "all_widgets_schema",
       "input_class_name": "rustic_ai.mcp.connectors.monday.AllWidgetsSchemaInput",
       "description": "Fetch complete JSON Schema 7 definitions for all available widget types in monday.com.\n    \n    This tool is essential before creating widgets as it provides:\n    - Complete schema definitions for all supported widgets\n    - Required and optional fields for each widget type\n    - Data type specifications and validation rules\n    - Detailed descriptions of widget capabilities\n    \n    Use this tool when you need to:\n    - Understand widget configuration requirements before creating widgets\n    - Validate widget settings against official schemas\n    - Plan widget implementations with proper data structures\n    \n    The response includes JSON Schema 7 definitions that describe exactly what settings each widget type accepts."
     },
     {
       "name": "create_widget",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateWidgetInput",
       "description": "Create a new widget in a dashboard or board view with specific configuration settings.\n    \n    This tool creates data visualization widgets that display information from monday.com boards:\n    **Parent Containers:**\n    - **DASHBOARD**: Place widget in a dashboard (most common use case)\n    - **BOARD_VIEW**: Place widget in a specific board view\n    \n    **Critical Requirements:**\n    1. **Schema Compliance**: Widget settings MUST conform to the JSON schema for the specific widget type\n    2. **Use all_widgets_schema first**: Always fetch widget schemas before creating widgets\n    3. **Validate settings**: Ensure all required fields are provided and data types match\n    \n    **Workflow:**\n    1. Use 'all_widgets_schema' to get schema definitions\n    2. Prepare widget settings according to the schema\n    3. Use this tool to create the widget"
     },
     {
       "name": "board_insights",
       "input_class_name": "rustic_ai.mcp.connectors.monday.BoardInsightsInput",
       "description": "This tool allows you to calculate insights about board's data by filtering, grouping and aggregating columns. For example, you can get the total number of items in a board, the number of items in each status, the number of items in each column, etc. Use this tool when you need to get a summary of the board's data, for example, you want to know the total number of items in a board, the number of items in each status, the number of items in each column, etc.[REQUIRED PRECONDITION]: Before using this tool, if new columns were added to the board or if you are not familiar with the board's structure (column IDs, column types, status labels, etc.), first use get_board_info to understand the board metadata. This is essential for constructing proper filters and knowing which columns are available.[IMPORTANT]: For some columns, human-friendly label is returned inside 'LABEL_<column_id' field. E.g. for column with id 'status_123' the label is returned inside 'LABEL_status_123' field."
     },
     {
       "name": "search",
       "input_class_name": "rustic_ai.mcp.connectors.monday.SearchInput",
       "description": "Search within monday.com platform. Can search for boards, documents, folders, workspaces, updates, and items.\nFor searching/listing specific users and teams, use list_users_and_teams tool.\nFor account-level info (plan, member count, products), use get_user_context tool.\nFor groups, use get_board_info tool.\nITEMS search requires a searchTerm and only returns id, title, and url.\nWORKSPACES search requires a searchTerm and only returns id, title, and description.\nUPDATES search requires a searchTerm and returns id, title (the update body), itemId, boardId, and creatorId. Optionally scope it with boardIds and/or creatorIds.\nIMPORTANT: ids returned by this tool are prefixed with the type of the object (e.g doc-123, board-456, folder-789, workspace-101, update-303, item-321). When passing the ids to other tools, you need to remove the prefix and just pass the number.\n    "
     },
     {
       "name": "get_user_context",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetUserContextInput",
       "description": "Fetch current user information, account information, and their relevant items (boards, folders, workspaces, dashboards).\n\n    Use this tool to:\n    - Get context about who the current user is (id, name, title)\n    - Get account info: plan tier, active member count, trial status, and active products\n    - Get the number of active members in the account (returns active_members_count)\n    - Discover user's favorite boards, folders, workspaces, and dashboards\n    - Get user's most relevant boards based on visit frequency and recency\n    - Get user's most relevant people based on interaction frequency and recency\n    - Reduce the need for search requests by knowing user's commonly accessed items\n    "
     },
     {
       "name": "get_assets",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetAssetsInput",
       "description": "Get assets (files) by their IDs. Returns file metadata including name, extension, size, public URL (valid for 1 hour), thumbnail URL, upload date, and who uploaded it."
     },
     {
       "name": "get_notetaker_meetings",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetNotetakerMeetingsInput",
       "description": "Retrieve notetaker meetings with optional detailed fields. Use include_summary, include_topics, include_action_items, and include_transcript flags to control which details are returned. Use access to filter by meeting access level (OWN, SHARED_WITH_ME, SHARED_WITH_ACCOUNT, ALL). Defaults to OWN. Supports filtering by ids, search term, and cursor-based pagination."
     },
     {
       "name": "create_view",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateViewInput",
       "description": "Create a new board view (tab) with optional filters and sorting. This creates a saved view on a monday.com board that users can switch to.\n\nFilter operators: any_of, not_any_of, is_empty, is_not_empty, greater_than, lower_than, between, contains_text, not_contains_text\n\nExample filter for people column: { \"rules\": [{ \"column_id\": \"people\", \"compare_value\": [\"person-12345\"], \"operator\": \"any_of\" }] }\nExample filter for status column: { \"rules\": [{ \"column_id\": \"status\", \"compare_value\": [1], \"operator\": \"any_of\" }] }"
     },
     {
       "name": "update_view",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateViewInput",
       "description": "Update an existing board view (tab) \u2014 change its name, filter rules, or sort order. Provide only the fields you want to change. Omitted fields are left unchanged.\n\nFilter operators: any_of, not_any_of, is_empty, is_not_empty, greater_than, lower_than, between, contains_text, not_contains_text\n\nExample filter for people column: { \"rules\": [{ \"column_id\": \"people\", \"compare_value\": [\"person-12345\"], \"operator\": \"any_of\" }] }\nExample filter for status column: { \"rules\": [{ \"column_id\": \"status\", \"compare_value\": [1], \"operator\": \"any_of\" }] }"
     },
     {
       "name": "create_view_table",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateViewTableInput",
       "description": "Create a new table-type board view with optional filters, sort, tags, and table-specific settings (column visibility/order and group-by). Use this instead of create_view when you need to configure table-specific settings. For a simple table view, create_view also works.\n\nFilter operators: any_of, not_any_of, is_empty, is_not_empty, greater_than, lower_than, between, contains_text, not_contains_text\n\nExample settings.columns: { \"column_properties\": [{ \"column_id\": \"status\", \"visible\": true }], \"column_order\": [\"name\", \"status\", \"date\"] }\nExample settings.group_by: { \"conditions\": [{ \"columnId\": \"status\" }], \"hideEmptyGroups\": true }"
     },
     {
       "name": "update_view_table",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateViewTableInput",
       "description": "Update an existing table-type board view \u2014 change its name, filters, sort, tags, or table-specific settings (column visibility/order and group-by). Provide only the fields you want to change. Omitted fields are left unchanged.\n\nFilter operators: any_of, not_any_of, is_empty, is_not_empty, greater_than, lower_than, between, contains_text, not_contains_text\n\nExample settings.columns: { \"column_properties\": [{ \"column_id\": \"status\", \"visible\": true }], \"column_order\": [\"name\", \"status\", \"date\"] }\nExample settings.group_by: { \"conditions\": [{ \"columnId\": \"status\" }], \"hideEmptyGroups\": true }"
     },
     {
       "name": "get_asset_upload_url",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetAssetUploadUrlInput",
       "description": "Get a presigned URL to upload a file to monday.com. Returns an upload_id and upload_url.\n\nAfter calling this tool, upload the file to the returned URL using an HTTP PUT request and capture the ETag header from the response:\n\ncurl -i -X PUT \"<upload_url>\" \\\n  -H \"Content-Type: <the contentType you provided>\" \\\n  --data-binary @<local_file_path>\n\nThe response includes an ETag header (e.g. ETag: \"abc123...\") \u2014 save this value.\n\nThen call finalize_asset_upload with the upload_id, etag, board_id, item_id, and column_id to complete the upload and attach the file to an item's file column.\n\nMax file size: 500MB."
     },
     {
       "name": "finalize_asset_upload",
       "input_class_name": "rustic_ai.mcp.connectors.monday.FinalizeAssetUploadInput",
       "description": "Finalize a file upload and create the asset on monday.com. Call this after uploading the file to the presigned URL from get_asset_upload_url. Requires the etag value from the PUT response headers. Automatically attaches the uploaded asset to the specified file column on the item. Returns the created asset_id."
     },
     {
       "name": "manage_agent",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ManageAgentInput",
       "description": "Full lifecycle management for monday platform agents \u2014 create, read, update, delete, change state, and run.\n\nmonday platform agents are user-built work orchestrators on monday.com \u2014 each has a profile (name, role, avatar), a goal, and a markdown execution plan. Agents in state ACTIVE can be triggered automatically. They are NOT local LangChain or MCP agents.\n\nACTIONS (only pass fields that apply to the chosen action):\n- create:        { action:\"create\", prompt, agent_model? } \u2014 AI-generated agent. Platform creates profile, goal, and plan from the prompt.\n- create_blank:  { action:\"create_blank\", name?, role?, role_description?, avatar_url?, gender?, background_color?, user_prompt? } \u2014 manually defined agent.\n- get one:       { action:\"get\", agent_id }\n- list owned:    { action:\"get\" }\n- update:        { action:\"update\", agent_id, name?, role?, role_description?, plan?, agent_model? }\n- delete:        { action:\"delete\", agent_id }\n- activate:      { action:\"activate\", agent_id }\n- deactivate:    { action:\"deactivate\", agent_id }\n- run:           { action:\"run\", agent_id }\n\nRULES:\n- \"create_blank\" with no fields creates a nameless blank agent \u2014 only do this intentionally.\n- \"update\" requires at least one of name/role/role_description/plan/agent_model.\n- \"update\", \"delete\", \"activate\", \"deactivate\", \"run\" all require \"agent_id\".\n- Created agents start INACTIVE. Follow with action:\"activate\" using the returned agent_id before they can be triggered.\n- \u26a0\ufe0f DESTRUCTIVE \u2014 \"delete\" is permanent and irreversible. When the user refers to an agent by name, ALWAYS call action:\"get\" first to confirm the correct agent_id before deleting.\n- \"run\" is fire-and-forget. Returns trigger_uuid \u2014 no run-status query exists, treat successful enqueue as the only signal.\n- Agent state is one of ACTIVE, INACTIVE, ARCHIVED, or FAILED. DELETED only appears as the return value of action:\"delete\".\n\nUSAGE EXAMPLES:\n- AI create:    { \"action\": \"create\", \"prompt\": \"Run my daily standup every weekday at 9am.\" }\n- Manual create:{ \"action\": \"create_blank\", \"name\": \"Standup Bot\", \"role\": \"Project Manager\", \"gender\": \"female\" }\n- Fetch one:    { \"action\": \"get\", \"agent_id\": \"42\" }\n- List mine:    { \"action\": \"get\" }\n- Rename:       { \"action\": \"update\", \"agent_id\": \"7\", \"name\": \"New Name\" }\n- Activate:     { \"action\": \"activate\", \"agent_id\": \"7\" }\n- Deactivate:   { \"action\": \"deactivate\", \"agent_id\": \"7\" }\n- Run:          { \"action\": \"run\", \"agent_id\": \"7\" }\n- Delete:       { \"action\": \"delete\", \"agent_id\": \"7\" }\n\nRELATED TOOLS:\n- agent_catalog \u2014 browse available trigger types and skills before wiring them to an agent\n- manage_agent_triggers \u2014 manage which triggers fire this agent automatically\n- manage_agent_skills \u2014 manage which skills this agent can perform\n- manage_agent_knowledge \u2014 manage which boards/docs this agent has access to"
     },
     {
       "name": "manage_agent_triggers",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ManageAgentTriggersInput",
       "description": "Manage the triggers attached to a monday platform agent \u2014 triggers define WHEN the agent runs automatically.\n\nACTIONS:\n- list:   { agent_id } \u2014 returns active triggers with node_id, block_reference_id, name, field_summary.\n- add:    { agent_id, block_reference_id, field_values? } \u2014 attaches a trigger type to the agent.\n- remove: { agent_id, node_id } \u2014 detaches a trigger instance by node_id (NOT block_reference_id).\n\nWORKFLOW \u2014 add a trigger:\n1. Call agent_catalog action:\"list_triggers\" \u2014 note block_reference_id, field_schemas, and required_fields.\n2. Collect required field values from the user (e.g. board_id, column_id).\n3. Call this tool action:\"add\" with block_reference_id and field_values.\nNote: add returns only { success } \u2014 no node_id for the new instance. Call action:\"list\" afterward if you need the node_id.\n\nWORKFLOW \u2014 remove a trigger:\n1. Call action:\"list\" to see active triggers and note the node_id of the instance to remove.\n2. Call action:\"remove\" with that node_id.\n\nNOTE: Only triggers that can be added programmatically appear in the catalog. OAuth/3rd-party triggers (Slack, Gmail, Salesforce, etc.)\nrequire user setup in the monday.com UI \u2014 they will not appear in agent_catalog and cannot be managed here.\n\nUSAGE EXAMPLES:\n- List triggers:  { \"action\": \"list\", \"agent_id\": \"7\" }\n- Add trigger:    { \"action\": \"add\", \"agent_id\": \"7\", \"block_reference_id\": \"status-change-ref\", \"field_values\": { \"board_id\": \"42\" } }\n- Remove trigger: { \"action\": \"remove\", \"agent_id\": \"7\", \"node_id\": \"node-abc\" }\n\nRELATED TOOLS:\n- agent_catalog action:\"list_triggers\" \u2014 discover available trigger types and their required field_values before calling action:\"add\" here\n- manage_agent_skills \u2014 manage which skills this agent can perform\n- manage_agent \u2014 manage the agent entity itself (create, activate, deactivate, etc.)"
     },
     {
       "name": "manage_agent_skills",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ManageAgentSkillsInput",
       "description": "Manage the full skill lifecycle for monday platform agents \u2014 create new skills in the catalog, attach skills to an agent, or detach them.\n\nSkills extend what an agent can do (e.g. sending emails, querying databases, posting to Slack).\n\nACTIONS:\n- create: { name, content, description? } \u2014 creates a new custom skill in the account-wide catalog.\n  The skill becomes available to all agents in the account.\n- add:    { agent_id, skill_id } \u2014 attaches a skill to this agent.\n- remove: { agent_id, skill_id } \u2014 detaches a skill from this agent.\n\nWORKFLOW \u2014 attach an existing skill:\n1. Call agent_catalog action:\"list_skills\" \u2014 find the skill_id of the skill to attach.\n2. Call this tool action:\"add\" with agent_id and that skill_id.\n\nWORKFLOW \u2014 create a new skill and attach it:\n1. Call this tool action:\"create\" with name and content \u2014 note the returned id.\n2. Call this tool action:\"add\" with agent_id and that id directly (no catalog lookup needed).\n\nNOTE: There is no action to list which skills are currently attached to a specific agent \u2014 the platform does not yet expose that query.\nTo browse all skills available in the account catalog, use agent_catalog action:\"list_skills\".\n\nUSAGE EXAMPLES:\n- Create a skill:  { \"action\": \"create\", \"name\": \"Send Slack Message\", \"content\": \"## Instructions\\nPost a message to a Slack channel.\", \"description\": \"Sends a message to Slack\" }\n- Add a skill:     { \"action\": \"add\", \"agent_id\": \"7\", \"skill_id\": \"skill-abc-123\" }\n- Remove a skill:  { \"action\": \"remove\", \"agent_id\": \"7\", \"skill_id\": \"skill-abc-123\" }\n\nRELATED TOOLS:\n- agent_catalog action:\"list_skills\" \u2014 browse existing skills to find a skill_id before calling action:\"add\"\n- manage_agent_triggers \u2014 manage which triggers fire this agent automatically\n- manage_agent \u2014 manage the agent entity itself (create, activate, deactivate, etc.)"
     },
     {
       "name": "manage_agent_knowledge",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ManageAgentKnowledgeInput",
       "description": "List, grant, update, or revoke a monday platform agent's access to boards and docs.\n\nAn agent's \"knowledge\" is the set of monday.com boards and docs it can read from or write to during a run.\n\n- list: Returns all resources the agent currently has access to, including permission level and resource type.\n- add: Grants the agent access to a board or doc with the specified permission level.\n- update: Changes the permission level on a resource the agent already has access to. Call action:\"list\" first to confirm the resource_id exists.\n- remove: Revokes the agent's access to a board or doc entirely. Call action:\"list\" first to confirm the resource_id exists.\n\nPermission types:\n- READ: Agent can read data from the resource.\n- READ_WRITE: Agent can read and write data to the resource.\n\nUSAGE EXAMPLES:\n- List: { \"action\": \"list\", \"agent_id\": \"7\" }\n- Add board access: { \"action\": \"add\", \"agent_id\": \"7\", \"resource_id\": \"42\", \"scope_type\": \"BOARD\", \"permission_type\": \"READ\" }\n- Update to read-write: { \"action\": \"update\", \"agent_id\": \"7\", \"resource_id\": \"42\", \"scope_type\": \"BOARD\", \"permission_type\": \"READ_WRITE\" }\n- Remove access: { \"action\": \"remove\", \"agent_id\": \"7\", \"resource_id\": \"42\", \"scope_type\": \"BOARD\" }\n\nRELATED TOOLS:\n- manage_agent \u2014 manage the agent entity itself (create, activate, deactivate, etc.)\n- manage_agent_triggers \u2014 manage which triggers fire this agent automatically\n- manage_agent_skills \u2014 manage which skills this agent can perform"
     },
     {
       "name": "agent_catalog",
       "input_class_name": "rustic_ai.mcp.connectors.monday.AgentCatalogInput",
       "description": "Browse the account-wide catalog of available trigger types and skills for monday platform agents. READ-ONLY \u2014 no agent_id required.\n\nUse this tool to discover what's available BEFORE wiring anything to a specific agent.\n\nACTIONS:\n- list_triggers: { block_reference_ids? } \u2014 returns available trigger types.\n  Each entry has block_reference_id (required for manage_agent_triggers action:\"add\"), name, description,\n  field_schemas (describes field_values shape), and required_fields (fields to collect from the user).\n  Note: only triggers that can be added programmatically appear here. OAuth/3rd-party triggers (Slack, Gmail, Salesforce, etc.)\n  require user setup in the monday.com UI and will not appear here.\n\n- list_skills: {} \u2014 returns available skills with id, name, description.\n  Never guess or invent a skill id \u2014 always look it up here before calling manage_agent_skills action:\"add\".\n\nUSAGE EXAMPLES:\n- List all trigger types:    { \"action\": \"list_triggers\" }\n- Fetch specific trigger:    { \"action\": \"list_triggers\", \"block_reference_ids\": [\"some-block-ref-id\"] }\n- List all skills:           { \"action\": \"list_skills\" }\n\nRELATED TOOLS:\n- manage_agent_triggers \u2014 use block_reference_id from list_triggers to attach a trigger to a specific agent\n- manage_agent_skills \u2014 use skill id from list_skills, or action:\"create\" to author a new skill, then attach to an agent\n- manage_agent \u2014 manage the agent entity itself (create, update, delete, activate, etc.)"
     },
     {
       "name": "list_automations",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ListAutomationsInput",
       "description": "List all automations on a specific monday.com board, including their ids, titles, active state, and configuration.\nWhen NOT to use: Do not call this tool to get general board information unrelated to automations.\nNote: Some legacy automations may not appear \u2014 mention this if users ask about missing automations.\n"
     },
     {
       "name": "manage_automations",
       "input_class_name": "rustic_ai.mcp.connectors.monday.ManageAutomationsInput",
       "description": "Activate, deactivate, or delete an existing monday.com automation.\n\nRequires an automation id. When the user refers to an automation by name, always call list_automations first to resolve the id \u2014 never guess or infer ids.\n\nActions:\n- activate: enables a paused automation so it starts responding to its trigger.\n- deactivate: pauses an automation while preserving its definition.\n- delete: permanently removes an automation \u2014 irreversible.\n\nWhen intent is ambiguous (\"stop\", \"turn off\", \"pause\"), prefer deactivate over delete."
     },
     {
       "name": "create_automation",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateAutomationInput",
       "description": "\n    Creates an automation on a monday board from a structured natural-language description.\n\nUse this tool only when you know:\n- boardId\n- the user's intended trigger\n- at least one intended action\n- any details the user provided that are relevant to the trigger, conditions, or actions\n\nThe caller does not need to know the exact available automation blocks or their required fields. Describe the user's intent clearly \u2014 the tool will translate that intent into supported blocks and values.\n\nIf a required detail is missing from the user's request, ask for clarification before calling the tool.\n\nIf the tool returns status: \"needs_clarification\", present the unresolved fields to the user, gather answers, then call the tool again.\n\nDescribe the automation in this format:\n\nTrigger:\n  When <the event that should start the automation>\n  Details:\n    <relevant detail>: <value>\n\nConditions:\n  - Only if <condition that should be true>\n    Details:\n      <relevant detail>: <value>\n\nActions:\n  - <action the automation should perform>:\n      <relevant detail>: <value>\n\nRules:\n- Use one trigger.\n- Conditions are optional.\n- Multiple conditions mean AND.\n- Use one or more actions.\n- Do not use branching.\n- Use natural language, not block IDs or internal field names.\n- Actions may reference values from the trigger context, such as \"{{item name}}\", \"{{creator}}\", \"{{status}}\", \"{{group}}\", or \"{{board}}\".\n\nTerminology:\n- Trigger: the event that starts the automation, such as \"when a new item is created\".\n- Conditions: optional requirements that must be true before actions run.\n- Actions: what the automation does when it runs.\n\nExample:\n\nTrigger:\n  When a new item is created\n\nActions:\n  - Send a notification:\n      Recipient: John Snow\n      Title: Important Update\n      Message: The item \"{{item name}}\" was created.\n\n  - Move the item to a group:\n      Group: Top group\n"
     },
     {
       "name": "get_automation_runs",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetAutomationRunsInput",
       "description": "Read automation/workflow run history. Read-only.\n\nModes:\n- \"history\": paginated run feed (state, duration, error reason). Use \"filters\" to narrow results and \"nextPageOffset\" to page (offset-only \u2014 next page = previous offset + returned count).\n- \"detail\": single run by \"triggerUuid\" (required) \u2014 returns block steps and MCP tool calls. Set \"includeToolEvents\": false to skip tool calls.\n\nScope: provide \"boardId\" for a specific board or \"accountWide\": true. One is required.\n\nKnown event states: \"success\", \"failure\", \"exhausted\"."
     },
     {
       "name": "get_automation_statistics",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetAutomationStatisticsInput",
       "description": "Aggregate automation run statistics. Read-only.\n\nBreakdowns:\n- \"totals\": success/failure/total counts at the account or board level.\n- \"by_entity\": per-automation and per-workflow counts for a given \"runStatus\" (required: \"success\" | \"failure\" | \"exhausted\"). Use \"excludeAutomationIds\" to omit specific automations.\n\nScope: provide \"boardId\" for a specific board or \"accountWide\": true. One is required.\n\nOptional \"userIds\" narrows results to specific creators."
     },
     {
       "name": "create_workflow",
       "input_class_name": "rustic_ai.mcp.connectors.monday.CreateWorkflowInput",
       "description": "Creates a new empty workflow in a monday.com workspace.\n\nUse this when the user wants to build a new standalone workflow from scratch. Workflows are cross-board, workspace-level \u2014 distinct from automations (use create_automation for those). You only need a workspaceId to get started \u2014 all other fields are optional.\n\nReturns:\n- workflowObjectId: the workflow object ID\n- workflowDraftId: the current draft version ID \u2014 workflows start as drafts and must be published before they run\n\nTerminology:\n- Workflows vs. automations: workflows are standalone objects scoped to a workspace. Automations (create_automation) are per-board trigger/action rules. They are different products.\n- Draft: the editable, inactive version of a workflow. Changes are made on the draft version until it is published as the live version.\n- Privacy: PUBLIC \u2014 visible to all workspace members (default). PRIVATE \u2014 restricted access. SHAREABLE \u2014 accessible to guests outside the account.\n\nNote: if directing the user to the workflow in the UI, the correct URL path is custom_objects/, not workflows/ \u2014 e.g. {account}.monday.com/custom_objects/{workflowObjectId}.\n"
     },
     {
       "name": "update_workflow",
       "input_class_name": "rustic_ai.mcp.connectors.monday.UpdateWorkflowInput",
       "description": "Updates an existing workflow draft using an AI agent.\n\nThe agent interprets the prompt and applies structural changes to the workflow \u2014 creating, updating, or deleting steps. Pass clear, descriptive instructions and the agent will decide which operations to perform, then return a summary of what it did.\n\nUse this after create_workflow to build out the workflow step by step. You can call it multiple times on the same draft to iteratively refine the workflow.\n\nParameters:\n- workflowObjectId and workflowDraftId: both returned by create_workflow \u2014 they identify which draft to update.\n- prompt: describe what you want to change in plain English (e.g. \"Add a trigger that fires when an item is created on the Marketing board\"). Maximum 2000 characters.\n\nReturns:\n- workflowObjectId: the workflow object ID (unchanged)\n- workflowDraftId: the draft version ID (unchanged)\n- result: agent response describing the changes made\n\nNote: if directing the user to the workflow in the UI, the correct URL path is custom_objects/, not workflows/ \u2014 e.g. {account}.monday.com/custom_objects/{workflowObjectId}.\n\nNote: the workflow runs only after it is published to live version.\n"
     },
     {
       "name": "plan_workflow",
       "input_class_name": "rustic_ai.mcp.connectors.monday.PlanWorkflowInput",
       "description": "Plans one or more monday.com workflows for a described process using an AI agent.\n\nThe agent analyzes the prompt, decides how many workflows are needed, identifies the required boards and columns, selects the correct trigger and action blocks (with their IDs), and returns a structured implementation plan with Mermaid diagrams and build notes for each workflow.\n\nUse this before create_workflow to understand how to break a complex process into individual workflows and which resources to create first.\n\nParameters:\n- prompt: describe the full end-to-end process in plain English. Maximum 2000 characters.\n\nReturns:\n- result: structured markdown plan with workflow breakdowns, block IDs, resource definitions, and a list of assumptions and gaps\n"
     },
     {
       "name": "publish_workflow",
       "input_class_name": "rustic_ai.mcp.connectors.monday.PublishWorkflowInput",
       "description": "Publishes a workflow draft, promoting it to the live version.\n\nUse this after create_workflow (and optionally update_workflow) to make the workflow active. Before publishing, the workflow is validated \u2014 if it has missing or misconfigured steps, publish will fail with a WORKFLOW_VALIDATION_FAILED error that includes structured issue details: which step failed, the issue type, and which inputs are missing. Use those details to guide the user on what to fix before retrying.\n\nParameters:\n- workflowObjectId and workflowDraftId: returned by create_workflow \u2014 they identify which draft to publish.\n- shouldActivate: whether to activate the workflow immediately after publish. Defaults to true \u2014 pass false to publish without activating.\n\nReturns:\n- workflowObjectId: the workflow object ID (unchanged)\n- workflowLiveId: the new live version ID \u2014 this changes on every publish, so do not cache it\n\nNote: if directing the user to the workflow in the UI, the correct URL path is custom_objects/, not workflows/ \u2014 e.g. {account}.monday.com/custom_objects/{workflowObjectId}.\n\n"
     },
     {
       "name": "get_monday_dev_sprints_boards",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetMondayDevSprintsBoardsInput",
       "description": "Discover monday-dev sprints boards and their associated tasks boards in your account.\n\n## Purpose:\nIdentifies and returns monday-dev sprints board IDs and tasks board IDs that you need to use with other monday-dev tools. \nThis tool scans your recently used boards (up to 100) to find valid monday-dev sprint management boards.\n\n## What it Returns:\n- Pairs of sprints boards and their corresponding tasks boards\n- Board IDs, names, and workspace information for each pair\n- The bidirectional relationship between each sprints board and its tasks board\n\n## Note:\nSearches recently used boards (up to 100). If none found, ask user to provide board IDs manually."
     },
     {
       "name": "get_sprints_metadata",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetSprintsMetadataInput",
       "description": "Get comprehensive sprint metadata from a monday-dev sprints board including:\n\n## Data Retrieved:\nA table of sprints with the following information:\n- Sprint ID\n- Sprint Name\n- Sprint timeline (planned from/to dates)\n- Sprint completion status (completed/in-progress/planned)\n- Sprint start date (actual)\n- Sprint end date (actual)\n- Sprint activation status\n- Sprint summary document object ID\n\n## Parameters:\n- **limit**: Number of sprints to retrieve (default: 25, max: 100)\n\nRequires the Main Sprints board ID of the monday-dev containing your sprints."
     },
     {
       "name": "get_sprint_summary",
       "input_class_name": "rustic_ai.mcp.connectors.monday.GetSprintSummaryInput",
       "description": "Get the complete summary and analysis of a sprint.\n\n## Purpose:\nUnlock deep insights into completed sprint performance. \n\nThe sprint summary content including:\n- **Scope Management**: Analysis of planned vs. unplanned tasks, scope creep\n- **Velocity & Performance**: Individual velocity, task completion rates, workload distribution per team member\n- **Task Distribution**: Breakdown of completed tasks by type (Feature, Bug, Tech Debt, Infrastructure, etc.)\n- **AI Recommendations**: Action items, process improvements, retrospective focus areas\n\n## Requirements:\n- Sprint must be completed and must be created after 1/1/2025 \n\n## Important Note:\nWhen viewing the section \"Completed by Assignee\", you'll see user IDs in the format \"@user-12345678\". the 8 digits after the @is the user ID. To retrieve the actual owner names, use the list_users_and_teams tool with the user ID and set includeTeams=false for optimal performance.\n\n"
     },
     {
       "name": "show-chart",
       "input_class_name": "rustic_ai.mcp.connectors.monday.Show-chartInput",
       "description": "[UI COMPONENT] Renders an interactive chart/graph visualization that the user can see and interact with. IMPORTANT: This is a UI DISPLAY tool - use it to RENDER visual components for the user to see and interact with. Do NOT use data-fetching tools when the user explicitly asks to \"show\", \"display\", \"visualize\", or \"see\" something visually. Use when user asks for: pie chart, bar chart, line graph, data visualization, or any graphical representation of numbers/statistics."
     },
     {
       "name": "show-table",
       "input_class_name": "rustic_ai.mcp.connectors.monday.Show-tableInput",
       "description": "[UI COMPONENT] Renders an interactive table visualization that the user can see and interact with. IMPORTANT: This is a UI DISPLAY tool - use it to RENDER visual components for the user to see and interact with. Do NOT use data-fetching tools when the user explicitly asks to \"show\", \"display\", \"visualize\", or \"see\" something visually. Use when user asks to: display a board as table, show items in table format, view data in tabular layout, or see a Monday.com board visually.\nWhen asked to update an item, use the currently selected item ID (get it from the widget state, using tools like \"get_widget_state\") for deciding which item to update. \nIf no item is selected, ask the user which item should be updated.\nAfter adding an update to an item, you MUST display the table AGAIN, even if the user did not ask you to.\n\n[IMPORTANT][FILTERING PRECONDITION]: IF using filters, you MUST call get_board_info(boardId) FIRST and use the returned boardContextToken."
     },
     {
       "name": "show-assign",
       "input_class_name": "rustic_ai.mcp.connectors.monday.Show-assignInput",
       "description": "[UI COMPONENT] Renders an interactive smart assignment interface visualization that the user can see and interact with. IMPORTANT: This is a UI DISPLAY tool - use it to RENDER visual components for the user to see and interact with. Do NOT use data-fetching tools when the user explicitly asks to \"show\", \"display\", \"visualize\", or \"see\" something visually. Helps assign tasks to the right people. Assignment suggestions are based on task details (like name) and person details (such as title, availability, etc).Use for requests to see or use an interactive assignment interface. Always show as much as data possible, while showing the person details like title etc. If you do not have the data available - use the list_users_and_teams tool."
     },
     {
       "name": "show-battery",
       "input_class_name": "rustic_ai.mcp.connectors.monday.Show-batteryInput",
       "description": "[UI COMPONENT] Renders an interactive battery/progress indicator visualization that the user can see and interact with. IMPORTANT: This is a UI DISPLAY tool - use it to RENDER visual components for the user to see and interact with. Do NOT use data-fetching tools when the user explicitly asks to \"show\", \"display\", \"visualize\", or \"see\" something visually. Use when user asks for: battery view, progress indicator, status distribution bar, completion percentage visualization, or Monday.com style status breakdown."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, RootModel


class Operator(Enum):
    """
    The operator to use for the filter
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Filter(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="The id of the column to filter by")]
    compareAttribute: Annotated[
        Optional[str], Field(description="The attribute to compare the value to. This is OPTIONAL property.")
    ] = None
    compareValue: Annotated[
        Union[str, float, bool, list[Union[str, float]]],
        Field(
            description=(
                "The value to compare the attribute to. This can be a string or index value depending on the column"
                " type."
            )
        ),
    ]
    operator: Annotated[Optional[Operator], Field(description="The operator to use for the filter")] = Operator.ANY_OF


class FiltersOperator(Enum):
    """
    The operator to use for the filters
    """

    AND = "and"
    OR = "or"


class Direction(Enum):
    """
    The direction to order by
    """

    ASC = "asc"
    DESC = "desc"


class OrderByItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="The id of the column to order by")]
    direction: Annotated[Optional[Direction], Field(description="The direction to order by")] = Direction.ASC


class GetBoardItemsPageInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to get items from")]
    itemIds: Annotated[
        Optional[list[float]],
        Field(description="The ids of the items to get. The count of items should be less than 100."),
    ] = None
    searchTerm: Annotated[
        Optional[str],
        Field(
            description=(
                "\n    The search term to use for the search.\n    - Use this when: the user provides a vague,"
                " incomplete, or approximate search term (e.g., “marketing campaign”, “John’s task”, “budget-related”),"
                " and there isn’t a clear exact compare value for a specific field.\n    - Do not use this when: the"
                " user specifies an exact value that maps directly to a column comparison (e.g., name contains"
                ' "marketing campaign", status = "Done", priority = "High", owner = "Daniel"). In these cases, prefer'
                " structured compare filters.\n  "
            )
        ),
    ] = None
    limit: Annotated[Optional[float], Field(description="The number of items to get", ge=1.0, le=500.0)] = 25
    cursor: Annotated[
        Optional[str],
        Field(
            description=(
                "The cursor to get the next page of items, use the nextCursor from the previous response. If the"
                " nextCursor was null, it means there are no more items to get"
            )
        ),
    ] = None
    includeColumns: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to include column values in the response.\nPERFORMANCE OPTIMIZATION: Only set this to true"
                " when you actually need the column data. Excluding columns significantly reduces token usage and"
                " improves response latency. If you only need to count items, get item IDs/names, or check if items"
                " exist, keep this false."
            )
        ),
    ] = False
    includeItemDescription: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to include the item's description in the response. The item description is the rich-text body"
                " content that appears inside a monday.com item (similar to a task description or issue body). Set this"
                " to true when the user asks about an item's description, details, body, or notes. PERFORMANCE"
                " OPTIMIZATION: Only set this to true when you actually need the item description content."
            )
        ),
    ] = False
    includeSubItems: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to include sub items in the response. PERFORMANCE OPTIMIZATION: Only set this to true when you"
                " actually need the sub items data."
            )
        ),
    ] = False
    subItemLimit: Annotated[
        Optional[float],
        Field(
            description="The number of sub items to get per item. This is only used when includeSubItems is true.",
            ge=1.0,
            le=100.0,
        ),
    ] = 25
    filters: Annotated[
        Optional[list[Filter]],
        Field(
            description=(
                "The configuration of filters to apply on the items. Use get_board_info for column ids and types on the"
                ' board. Before sending the filters, use get_column_type_info with fetchMode "guidelines" and use'
                " data.guidelines.filter (null if that type has no documented rules)."
            )
        ),
    ] = None
    filtersOperator: Annotated[Optional[FiltersOperator], Field(description="The operator to use for the filters")] = (
        FiltersOperator.AND
    )
    columnIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The ids of the item columns and subitem columns to get, can be used to reduce the response size when"
                " user asks for specific columns. Works only when includeColumns is true. If not provided, all columns"
                " will be returned"
            )
        ),
    ] = None
    orderBy: Annotated[
        Optional[list[OrderByItem]],
        Field(description="The columns to order by, will control the order of the items in the response"),
    ] = None


class CreateItemInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to which the new item will be added")]
    name: Annotated[
        str, Field(description="The name of the new item to be created, must be relevant to the user's request")
    ]
    groupId: Annotated[
        Optional[str],
        Field(
            description=(
                "The id of the group id to which the new item will be added, if its not clearly specified, leave empty"
            )
        ),
    ] = None
    columnValues: Annotated[
        str,
        Field(
            description=(
                'A string containing the new column values for the item following this structure: {\\"column_id\\":'
                ' \\"value\\",... you can change multiple columns at once, note that for status column you must use'
                " nested value with 'label' as a key and for date column use 'date' as key} - example:"
                ' "{\\"text_column_id\\":\\"New text\\", \\"status_column_id\\":{\\"label\\":\\"Done\\"},'
                ' \\"date_column_id\\":{\\"date\\":\\"2023-05-25\\"},\\"dropdown_id\\":\\"value\\",'
                ' \\"phone_id\\":\\"123-456-7890\\", \\"email_id\\":\\"test@example.com\\"}"'
            )
        ),
    ]
    parentItemId: Annotated[
        Optional[float], Field(description="The id of the parent item under which the new subitem will be created")
    ] = None
    duplicateFromItemId: Annotated[
        Optional[float],
        Field(
            description=(
                "The id of existing item to duplicate and update with new values (only provide when duplicating)"
            )
        ),
    ] = None


class CreateUpdateInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    itemId: Annotated[float, Field(description="The id of the item to which the update will be added")]
    body: Annotated[
        str,
        Field(
            description=(
                "The update text to be created. Do not use @ to mention users, use the mentionsList field instead. use"
                " html tags to format the text, dont use markdown."
            )
        ),
    ]
    mentionsList: Annotated[
        Optional[str],
        Field(
            description=(
                'Optional JSON array of mentions in the format: [{"id": "123", "type": "User"}, {"id": "456", "type":'
                ' "Team"}]. Valid types are: User, Team, Board, Project'
            )
        ),
    ] = None
    parentId: Annotated[
        Optional[float],
        Field(
            description=(
                "The ID of the update to reply to. Use this parameter when you want to reply on an existing update"
                " leave it empty if you want to create a new update"
            )
        ),
    ] = None


class ObjectType(Enum):
    """
    Type of object for which objectId was provided
    """

    ITEM = "Item"
    BOARD = "Board"


class GetUpdatesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    objectId: Annotated[str, Field(description="The ID of the item or board to get updates from")]
    objectType: Annotated[ObjectType, Field(description="Type of object for which objectId was provided")]
    limit: Annotated[
        Optional[float], Field(description="Number of updates per page (default: 25, max: 100)", ge=1.0, le=100.0)
    ] = 25
    page: Annotated[Optional[float], Field(description="Page number for pagination (default: 1)", ge=1.0)] = 1
    includeReplies: Annotated[Optional[bool], Field(description="Include update replies in the response")] = False
    includeAssets: Annotated[Optional[bool], Field(description="Include file attachments in the response")] = False
    fromDate: Annotated[
        Optional[str],
        Field(
            description=(
                'Start of date range filter (e.g. "2025-01-01" or "2025-01-01T00:00:00Z"). Must be used together with'
                " toDate. Only supported for Board objectType."
            )
        ),
    ] = None
    toDate: Annotated[
        Optional[str],
        Field(
            description=(
                'End of date range filter (e.g. "2025-06-01" or "2025-06-01T23:59:59Z"). Must be used together with'
                " fromDate. Only supported for Board objectType."
            )
        ),
    ] = None
    includeItemUpdates: Annotated[
        Optional[bool],
        Field(
            description=(
                "When objectType is Board, also include updates on individual items. Defaults to false, returning only"
                " board discussion. Set to true to retrieve all updates on a board, including updates on individual"
                " items."
            )
        ),
    ] = False


class GetBoardActivityInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to get activity for")]
    itemIds: Annotated[
        Optional[list[float]],
        Field(description="Filter activity to specific item ids. Omit to get activity for the whole board."),
    ] = None
    userIds: Annotated[
        Optional[list[float]], Field(description="Filter activity to actions performed by specific user ids.")
    ] = None
    fromDate: Annotated[
        Optional[str],
        Field(description="Start date for activity range (ISO8601DateTime format). Defaults to 30 days ago"),
    ] = None
    toDate: Annotated[
        Optional[str], Field(description="End date for activity range (ISO8601DateTime format). Defaults to now")
    ] = None
    includeData: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to include the raw data payload for each activity entry. The data field contains the full"
                " before/after state of changes and can be very large. Only set to true when you need the detailed"
                " change data."
            )
        ),
    ] = False


class GetBoardInfoInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to get information for")]


class ListUsersAndTeamsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    userIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Specific user IDs to fetch.[IMPORTANT] ALWAYS use when you have user IDs in context. PREFER over"
                " general search. RETURNS: user profiles including team memberships"
            ),
            max_length=500,
        ),
    ] = None
    teamIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Specific team IDs to fetch.[IMPORTANT] ALWAYS use when you have team IDs in context, NEVER fetch all"
                " teams if specific IDs are available.\n      RETURNS: Team details with owners and optional member"
                " data."
            ),
            max_length=500,
        ),
    ] = None
    name: Annotated[
        Optional[str],
        Field(
            description=(
                "Name-based USER search ONLY. STANDALONE parameter - cannot be combined with others. PREFERRED method"
                " for finding users when you know names. Performs fuzzy matching.\n      CRITICAL: This parameter"
                " searches for USERS ONLY, NOT teams. To search for teams, use teamIds parameter instead."
            )
        ),
    ] = None
    getMe: Annotated[
        Optional[bool],
        Field(
            description=(
                "[TOP PRIORITY] Use ALWAYS when requesting current user information. Examples of when it should be"
                ' used: ["get my user" or "get my teams"].\n      This parameter CONFLICTS with all others. '
            )
        ),
    ] = None
    includeTeams: Annotated[
        Optional[bool],
        Field(
            description=(
                "[AVOID] This fetches all teams in the account. To fetch a specific user's teams just fetch that user"
                " by id and you will get their team memberships."
            )
        ),
    ] = None
    teamsOnly: Annotated[
        Optional[bool],
        Field(description="Fetch only teams, no users returned. Combine with includeTeamMembers for member details."),
    ] = None
    includeTeamMembers: Annotated[
        Optional[bool],
        Field(
            description="Set to true only when you need additional member details for teams other than names and ids."
        ),
    ] = None


class ChangeItemColumnValuesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The ID of the board that contains the item to be updated")]
    itemId: Annotated[float, Field(description="The ID of the item to be updated")]
    columnValues: Annotated[
        str,
        Field(
            description=(
                'A string containing the new column values for the item following this structure: {\\"column_id\\":'
                ' \\"value\\",... you can change multiple columns at once, note that for status column you must use'
                " nested value with 'label' as a key and for date column use 'date' as key} - example:"
                ' "{\\"text_column_id\\":\\"New text\\", \\"status_column_id\\":{\\"label\\":\\"Done\\"},'
                ' \\"date_column_id\\":{\\"date\\":\\"2023-05-25\\"}, \\"phone_id\\":\\"123-456-7890\\",'
                ' \\"email_id\\":\\"test@example.com\\"}"'
            )
        ),
    ]
    createLabelsIfMissing: Annotated[
        Optional[bool],
        Field(
            description=(
                "If true, create missing Status/Dropdown labels when setting those columns. Requires permission to"
                " change board structure. Omit or false to only use existing labels."
            )
        ),
    ] = None


class BoardKind(Enum):
    """
    The kind of board to create
    """

    PRIVATE = "private"
    PUBLIC = "public"
    SHARE = "share"


class CreateBoardInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardName: Annotated[str, Field(description="The name of the board to create")]
    boardKind: Annotated[Optional[BoardKind], Field(description="The kind of board to create")] = BoardKind.PUBLIC
    boardDescription: Annotated[Optional[str], Field(description="The description of the board to create")] = None
    workspaceId: Annotated[Optional[str], Field(description="The ID of the workspace to create the board in")] = None
    boardOwnerIds: Annotated[
        Optional[list[str]], Field(description="Optional list of user IDs to set as board owners")
    ] = None


class BoardKind1(Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    SHARE = "share"


class CreateFormInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    destination_workspace_id: str
    destination_folder_id: Optional[str] = None
    destination_folder_name: Optional[str] = None
    board_kind: Optional[BoardKind1] = None
    destination_name: Annotated[Optional[str], Field(description="Board name (stores form responses).")] = None
    board_owner_ids: Optional[list[str]] = None
    board_owner_team_ids: Optional[list[str]] = None
    board_subscriber_ids: Annotated[Optional[list[str]], Field(description="User IDs to notify on board activity.")] = (
        None
    )
    board_subscriber_teams_ids: Annotated[
        Optional[list[str]], Field(description="Team IDs to notify on board activity.")
    ] = None


class Action(Enum):
    """
    Action to execute on the form. Each action requires different fields — check field descriptions to know what to include.
    """

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    SHORTEN_FORM_URL = "shortenFormUrl"
    SET_FORM_PASSWORD = "setFormPassword"
    CREATE_TAG = "createTag"
    DELETE_TAG = "deleteTag"
    UPDATE_TAG = "updateTag"
    UPDATE_APPEARANCE = "updateAppearance"
    UPDATE_ACCESSIBILITY = "updateAccessibility"
    UPDATE_FEATURES = "updateFeatures"
    UPDATE_QUESTION_ORDER = "updateQuestionOrder"
    UPDATE_FORM_HEADER = "updateFormHeader"


class Tag(BaseModel):
    """
    Tag to create/update/delete. Delete: id only. Create: name+value (id/columnId auto-generated). Update: id+new value.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Optional[str], Field(description="Required for update/delete. Auto-generated.")] = None
    name: Annotated[Optional[str], Field(description="Required for create. Cannot be updated.")] = None
    value: Annotated[Optional[str], Field(description="Required for create/update.")] = None
    columnId: Annotated[Optional[str], Field(description="Auto-generated. Cannot be updated.")] = None


class Type(Enum):
    IMAGE = "Image"
    COLOR = "Color"
    NONE = "None"


class Background(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    type: Optional[Type] = None
    value: Annotated[Optional[str], Field(description="Hex color or image URL (depends on type).")] = None


class Format(Enum):
    ONE_BY_ONE = "OneByOne"
    CLASSIC = "Classic"


class Alignment(Enum):
    FULL_LEFT = "FullLeft"
    LEFT = "Left"
    CENTER = "Center"
    RIGHT = "Right"
    FULL_RIGHT = "FullRight"


class Direction1(Enum):
    LT_R = "LtR"
    RTL = "Rtl"


class Layout(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    format: Optional[Format] = None
    alignment: Optional[Alignment] = None
    direction: Optional[Direction1] = None


class Position(Enum):
    AUTO = "Auto"
    LEFT = "Left"
    CENTER = "Center"
    RIGHT = "Right"


class Size(Enum):
    """
    Logo size for the form header.
    """

    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    EXTRA_LARGE = "ExtraLarge"


class Logo(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    position: Optional[Position] = None
    size: Annotated[Optional[Size], Field(description="Logo size for the form header.")] = None


class SubmitButton(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: Optional[str] = None


class Size1(Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"


class Text(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    font: Optional[str] = None
    color: Optional[str] = None
    size: Optional[Size1] = None


class Appearance(BaseModel):
    """
    Patch. Required for updateAppearance.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    background: Optional[Background] = None
    hideBranding: Optional[bool] = None
    layout: Optional[Layout] = None
    logo: Optional[Logo] = None
    primaryColor: Optional[str] = None
    showProgressBar: Optional[bool] = None
    submitButton: Optional[SubmitButton] = None
    text: Optional[Text] = None


class Accessibility(BaseModel):
    """
    Patch. Required for updateAccessibility.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    language: Annotated[Optional[str], Field(description="Form locale, e.g. 'en', 'es', 'fr'.")] = None
    logoAltText: Optional[str] = None


class RedirectAfterSubmission(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None
    redirectUrl: Optional[str] = None


class AfterSubmissionView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    allowEditSubmission: Optional[bool] = None
    allowResubmit: Optional[bool] = None
    allowViewSubmission: Optional[bool] = None
    description: Optional[str] = None
    redirectAfterSubmission: Optional[RedirectAfterSubmission] = None
    showSuccessImage: Optional[bool] = None
    title: Optional[str] = None


class AiTranslate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None


class CloseDate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None
    date: Annotated[Optional[str], Field(description="ISO timestamp.")] = None


class DraftSubmission(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None


class Monday(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    itemGroupId: Optional[str] = None
    includeNameQuestion: Annotated[Optional[bool], Field(description="Adds name column as a form question.")] = None
    includeUpdateQuestion: Annotated[
        Optional[bool], Field(description="Adds updates/comments field linked to the board item.")
    ] = None
    syncQuestionAndColumnsTitles: Annotated[
        Optional[bool], Field(description="Syncs question titles with board column names.")
    ] = None
    allow_create_item: Annotated[
        Optional[bool], Field(description="Shows 'Create Item' button on the board to open this form.")
    ] = None


class Password(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Annotated[
        Optional[bool], Field(description="Can only be set to false. Use setFormPassword to enable.")
    ] = None


class StartButton(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: Optional[str] = None


class PreSubmissionView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None
    title: Optional[str] = None
    description: Optional[str] = None
    startButton: Optional[StartButton] = None


class RequireLogin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None
    redirectToLogin: Optional[bool] = None


class ResponseLimit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: Optional[bool] = None
    limit: Optional[float] = None


class Features(BaseModel):
    """
    Patch. Required for updateFeatures.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    afterSubmissionView: Optional[AfterSubmissionView] = None
    ai_translate: Optional[AiTranslate] = None
    closeDate: Optional[CloseDate] = None
    draftSubmission: Optional[DraftSubmission] = None
    monday: Optional[Monday] = None
    password: Optional[Password] = None
    preSubmissionView: Optional[PreSubmissionView] = None
    reCaptchaChallenge: Optional[bool] = None
    requireLogin: Optional[RequireLogin] = None
    responseLimit: Optional[ResponseLimit] = None
    is_anonymous: Annotated[Optional[bool], Field(description="Hides submitter identity.")] = None


class Question(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="Question ID. Required for update/delete.")]
    page_block_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Page block ID to group this question within. Set to null to remove from page block. Omit to leave"
                " unchanged."
            )
        ),
    ] = None


class Form(BaseModel):
    """
    Form data to update (patch semantics).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    appearance: Annotated[Optional[Appearance], Field(description="Patch. Required for updateAppearance.")] = None
    accessibility: Annotated[Optional[Accessibility], Field(description="Patch. Required for updateAccessibility.")] = (
        None
    )
    features: Annotated[Optional[Features], Field(description="Patch. Required for updateFeatures.")] = None
    title: Annotated[Optional[str], Field(description="Required for updateFormHeader.")] = None
    description: Annotated[Optional[str], Field(description="Required for updateFormHeader.")] = None
    questions: Annotated[
        Optional[list[Question]],
        Field(
            description="All question IDs in order. Must include every existing ID. Required for updateQuestionOrder."
        ),
    ] = None


class UpdateFormInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    formToken: str
    action: Annotated[
        Action,
        Field(
            description=(
                "Action to execute on the form. Each action requires different fields — check field descriptions to"
                " know what to include."
            )
        ),
    ]
    formPassword: Annotated[Optional[str], Field(description="Required for setFormPassword action.")] = None
    tag: Annotated[
        Optional[Tag],
        Field(
            description=(
                "Tag to create/update/delete. Delete: id only. Create: name+value (id/columnId auto-generated). Update:"
                " id+new value."
            )
        ),
    ] = None
    form: Annotated[Optional[Form], Field(description="Form data to update (patch semantics).")] = None


class GetFormInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    formToken: str


class Action1(Enum):
    """
    Action to perform on the question of a form. create requires question. update requires questionId and question
    with type always included. delete requires questionId.
    """

    DELETE = "delete"
    UPDATE = "update"
    CREATE = "create"


class Type1(Enum):
    """
    Question type. Always required. Cannot be changed after creation — always send the existing type when updating.
    """

    BOOLEAN = "Boolean"
    CONNECTED_BOARDS = "ConnectedBoards"
    COUNTRY = "Country"
    DISPLAY_TEXT = "DISPLAY_TEXT"
    DATE = "Date"
    DATE_RANGE = "DateRange"
    EMAIL = "Email"
    FILE = "File"
    HOUR = "HOUR"
    LINK = "Link"
    LOCATION = "Location"
    LONG_TEXT = "LongText"
    MULTI_SELECT = "MultiSelect"
    NAME = "Name"
    NUMBER = "Number"
    PAGE_BLOCK = "PAGE_BLOCK"
    PEOPLE = "People"
    PHONE = "Phone"
    RATING = "Rating"
    SHORT_TEXT = "ShortText"
    SIGNATURE = "Signature"
    SINGLE_SELECT = "SingleSelect"
    SUBITEMS = "Subitems"
    UPDATES = "Updates"


class Operator1(Enum):
    OR = "OR"


class Condition(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    building_block_id: Annotated[str, Field(description="Question ID to evaluate.")]
    operator: Operator1
    values: Annotated[list[str], Field(description="Answer values that satisfy the condition.")]


class Rule(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Operator1
    conditions: list[Condition]


class ShowIfRules(BaseModel):
    """
    Conditional visibility. All operators must be OR.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Operator1
    rules: list[Rule]


class Option(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: str
    value: Annotated[
        Optional[str],
        Field(
            description=(
                "Unique identifier for the option. If this option was used in existing submissions, it must keep its"
                " original value to preserve data integrity."
            )
        ),
    ] = None
    visible: Optional[bool] = None


class Display(Enum):
    """
    SingleSelect/MultiSelect only.
    """

    DROPDOWN = "Dropdown"
    HORIZONTAL = "Horizontal"
    VERTICAL = "Vertical"


class OptionsOrder(Enum):
    """
    SingleSelect/MultiSelect only.
    """

    ALPHABETICAL = "Alphabetical"
    CUSTOM = "Custom"
    RANDOM = "Random"


class PrefixPredefined(BaseModel):
    """
    Phone only. Sets a default country prefix.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: bool
    prefix: Annotated[Optional[str], Field(description="Country code, e.g. 'US', 'IL'.")] = None


class Source(Enum):
    ACCOUNT = "Account"
    QUERY_PARAM = "QueryParam"


class Prefill(BaseModel):
    """
    Auto-populates from account data or URL query params.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    enabled: bool
    lookup: Annotated[Optional[str], Field(description="Field name (e.g. 'email') or URL param name.")] = None
    source: Optional[Source] = None


class Settings(BaseModel):
    """
    Type-specific question settings. Check each field description to see which question type it applies to.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    checkedByDefault: Annotated[Optional[bool], Field(description="Boolean question type only.")] = None
    defaultCurrentDate: Annotated[Optional[bool], Field(description="Date question type only.")] = None
    display: Annotated[Optional[Display], Field(description="SingleSelect/MultiSelect only.")] = None
    includeTime: Annotated[Optional[bool], Field(description="Date only. Adds time picker.")] = None
    locationAutofilled: Annotated[Optional[bool], Field(description="Location only. Auto-fills current location.")] = (
        None
    )
    optionsOrder: Annotated[Optional[OptionsOrder], Field(description="SingleSelect/MultiSelect only.")] = None
    prefixAutofilled: Annotated[Optional[bool], Field(description="Phone only. Auto-detects country prefix.")] = None
    prefixPredefined: Annotated[
        Optional[PrefixPredefined], Field(description="Phone only. Sets a default country prefix.")
    ] = None
    skipValidation: Annotated[Optional[bool], Field(description="Link only. Skips URL format validation.")] = None
    labelLimitCount: Annotated[
        Optional[int], Field(description="MultiSelect only. Max selections. Pair with labelLimitCountEnabled.")
    ] = None
    label_limit_count_enabled: Annotated[
        Optional[bool], Field(description="MultiSelect only. Enables selection limit.")
    ] = None
    default_answer: Annotated[
        Optional[str], Field(description="ShortText/LongText/Name/Link only. Pre-filled default value.")
    ] = None
    prefill: Annotated[
        Optional[Prefill], Field(description="Auto-populates from account data or URL query params.")
    ] = None


class Question1(BaseModel):
    """
    The question to create or update. Always include type, then only the fields you want to set or change.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Annotated[
        Type1,
        Field(
            description=(
                "Question type. Always required. Cannot be changed after creation — always send the existing type when"
                " updating."
            )
        ),
    ]
    title: Annotated[Optional[str], Field(description="Question text. Required when creating.")] = None
    description: Annotated[Optional[str], Field(description="Help text shown under the question.")] = None
    visible: Optional[bool] = None
    required: Optional[bool] = None
    insert_after_question_id: Annotated[
        Optional[str], Field(description="ID to insert after. Omit to append. Null for first position.")
    ] = None
    page_block_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Page block ID to group this question within. Set to null to remove from page block. Omit to leave"
                " unchanged."
            )
        ),
    ] = None
    show_if_rules: Annotated[
        Optional[ShowIfRules], Field(description="Conditional visibility. All operators must be OR.")
    ] = None
    options: Annotated[
        Optional[list[Option]],
        Field(
            description=(
                "Options for select questions. Always include all options — omitting an existing option will delete it."
                " To update safely, call get_form first to retrieve existing option values, then include all options"
                " you want to keep with their original value fields."
            )
        ),
    ] = None
    settings: Annotated[
        Optional[Settings],
        Field(
            description=(
                "Type-specific question settings. Check each field description to see which question type it"
                " applies to."
            )
        ),
    ] = None


class FormQuestionsEditorInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action1,
        Field(
            description=(
                "Action to perform on the question of a form. create requires question. update requires questionId and"
                " question with type always included. delete requires questionId."
            )
        ),
    ]
    formToken: str
    questionId: Annotated[Optional[str], Field(description="Question ID. Required for update/delete.")] = None
    question: Annotated[
        Optional[Question1],
        Field(
            description=(
                "The question to create or update. Always include type, then only the fields you want to set or change."
            )
        ),
    ] = None


class Phone(BaseModel):
    """
    Answer for phone questions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    phone: Annotated[str, Field(description="The phone number.")]
    country_short_name: Annotated[str, Field(description='The ISO 3166-1 alpha-2 country code (e.g. "US").')]


class Country(BaseModel):
    """
    Answer for country questions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    country_name: Annotated[str, Field(description='The full country name (e.g. "United States").')]
    country_code: Annotated[str, Field(description='The ISO 3166-1 alpha-2 country code (e.g. "US").')]


class Date(BaseModel):
    """
    Answer for date questions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    date: Annotated[str, Field(description="The date in YYYY-MM-DD format.")]
    zone_diff: Annotated[Optional[int], Field(description="UTC offset in minutes.")] = None


class DateRange(BaseModel):
    """
    Answer for date range questions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    from_: Annotated[str, Field(alias="from", description="Start date in YYYY-MM-DD format.")]
    to: Annotated[str, Field(description="End date in YYYY-MM-DD format.")]


class Country1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    long_name: Annotated[str, Field(description="Full country name.")]
    short_name: Annotated[str, Field(description="ISO 3166-1 alpha-2 country code.")]


class City(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    long_name: Annotated[str, Field(description="Full city name.")]
    short_name: Annotated[str, Field(description="Abbreviated city name.")]


class Street(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    long_name: Annotated[str, Field(description="Full street name.")]
    short_name: Annotated[str, Field(description="Abbreviated street name.")]


class StreetNumber(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    long_name: Annotated[str, Field(description="Full street number.")]
    short_name: Annotated[str, Field(description="Abbreviated street number.")]


class Location(BaseModel):
    """
    Answer for location questions. Requires a Google Maps place ID and structured address components.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lat: Annotated[float, Field(description="Latitude.")]
    lng: Annotated[float, Field(description="Longitude.")]
    place_id: Annotated[str, Field(description="Google Maps place ID.")]
    address: Annotated[str, Field(description="Full formatted address.")]
    country: Country1
    city: City
    street: Street
    street_number: StreetNumber


class FileItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="The file ID returned by the workforms upload endpoint.")]
    name: Annotated[str, Field(description='Original file name (e.g. "image.png").')]
    extension: Annotated[Optional[str], Field(description='File extension (e.g. "pdf", "png").')] = None
    is_image: Annotated[Optional[bool], Field(description="Whether the file is an image.")] = None


class Tag1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID this tag maps to.")]
    value: Annotated[str, Field(description="The tag value to submit.")]


class ColumnType(Enum):
    """
    The type of the column to be created
    """

    AUTO_NUMBER = "auto_number"
    BOARD_RELATION = "board_relation"
    BUTTON = "button"
    CHECKBOX = "checkbox"
    COLOR_PICKER = "color_picker"
    COUNTRY = "country"
    CREATION_LOG = "creation_log"
    DATE = "date"
    DEPENDENCY = "dependency"
    DIRECT_DOC = "direct_doc"
    DOC = "doc"
    DROPDOWN = "dropdown"
    EMAIL = "email"
    FILE = "file"
    FORMULA = "formula"
    GROUP = "group"
    HOUR = "hour"
    INTEGRATION = "integration"
    ITEM_ASSIGNEES = "item_assignees"
    ITEM_ID = "item_id"
    LAST_UPDATED = "last_updated"
    LINK = "link"
    LOCATION = "location"
    LONG_TEXT = "long_text"
    MIRROR = "mirror"
    NAME = "name"
    NUMBERS = "numbers"
    PEOPLE = "people"
    PHONE = "phone"
    PROGRESS = "progress"
    RATING = "rating"
    STATUS = "status"
    SUBTASKS = "subtasks"
    TAGS = "tags"
    TEAM = "team"
    TEXT = "text"
    TIME_TRACKING = "time_tracking"
    TIMELINE = "timeline"
    UNSUPPORTED = "unsupported"
    VOTE = "vote"
    WEEK = "week"
    WORLD_CLOCK = "world_clock"


class CreateColumnInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to which the new column will be added")]
    columnType: Annotated[ColumnType, Field(description="The type of the column to be created")]
    columnTitle: Annotated[str, Field(description="The title of the column to be created")]
    columnDescription: Annotated[Optional[str], Field(description="The description of the column to be created")] = None
    columnSettings: Annotated[
        Optional[str],
        Field(
            description=(
                "Column-specific configuration settings as a JSON string. Use get_column_type_info with fetchMode"
                ' "schema" for the JSON schema for the given column type.'
            )
        ),
    ] = None


class GroupColor(Enum):
    """
    The color for the group. Must be one of the predefined Monday.com group colors: #037f4c, #00c875, #9cd326,
    #cab641, #ffcb00, #784bd1, #9d50dd, #007eb5, #579bfc, #66ccff, #bb3354, #df2f4a, #ff007f, #ff5ac4, #ff642e,
    #fdab3d, #7f5347, #c4c4c4, #757575
    """

    FIELD_037F4C = "#037f4c"
    FIELD_00C875 = "#00c875"
    FIELD_9CD326 = "#9cd326"
    CAB641 = "#cab641"
    FFCB00 = "#ffcb00"
    FIELD_784BD1 = "#784bd1"
    FIELD_9D50DD = "#9d50dd"
    FIELD_007EB5 = "#007eb5"
    FIELD_579BFC = "#579bfc"
    FIELD_66CCFF = "#66ccff"
    BB3354 = "#bb3354"
    DF2F4A = "#df2f4a"
    FF007F = "#ff007f"
    FF5AC4 = "#ff5ac4"
    FF642E = "#ff642e"
    FDAB3D = "#fdab3d"
    FIELD_7F5347 = "#7f5347"
    C4C4C4 = "#c4c4c4"
    FIELD_757575 = "#757575"


class PositionRelativeMethod(Enum):
    """
    Whether to position the new group before or after the relativeTo group
    """

    AFTER_AT = "after_at"
    BEFORE_AT = "before_at"


class CreateGroupInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[str, Field(description="The ID of the board to create the group in")]
    groupName: Annotated[str, Field(description="The name of the new group (maximum 255 characters)", max_length=255)]
    groupColor: Annotated[
        Optional[GroupColor],
        Field(
            description=(
                "The color for the group. Must be one of the predefined Monday.com group colors: #037f4c, #00c875,"
                " #9cd326, #cab641, #ffcb00, #784bd1, #9d50dd, #007eb5, #579bfc, #66ccff, #bb3354, #df2f4a, #ff007f,"
                " #ff5ac4, #ff642e, #fdab3d, #7f5347, #c4c4c4, #757575"
            )
        ),
    ] = None
    relativeTo: Annotated[
        Optional[str], Field(description="The ID of the group to position this new group relative to")
    ] = None
    positionRelativeMethod: Annotated[
        Optional[PositionRelativeMethod],
        Field(description="Whether to position the new group before or after the relativeTo group"),
    ] = None


class AllMondayApiInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[
        str, Field(description="Custom GraphQL query/mutation. you need to provide the full query / mutation")
    ]
    variables: Annotated[str, Field(description="JSON string containing the variables for the GraphQL operation")]


class OperationType(Enum):
    """
    Type of operation: "read" for queries, "write" for mutations
    """

    READ = "read"
    WRITE = "write"


class GetGraphqlSchemaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    random_string: Annotated[Optional[str], Field(description="Dummy parameter for no-parameter tools")] = None
    operationType: Annotated[
        Optional[OperationType], Field(description='Type of operation: "read" for queries, "write" for mutations')
    ] = None


class ColumnType1(Enum):
    """
    The column type to retrieve information for (e.g., "text", "status", "date", "numbers")
    """

    AUTO_NUMBER = "auto_number"
    BOARD_RELATION = "board_relation"
    BUTTON = "button"
    CHECKBOX = "checkbox"
    COLOR_PICKER = "color_picker"
    COUNTRY = "country"
    CREATION_LOG = "creation_log"
    DATE = "date"
    DEPENDENCY = "dependency"
    DIRECT_DOC = "direct_doc"
    DOC = "doc"
    DROPDOWN = "dropdown"
    EMAIL = "email"
    FILE = "file"
    FORMULA = "formula"
    GROUP = "group"
    HOUR = "hour"
    INTEGRATION = "integration"
    ITEM_ASSIGNEES = "item_assignees"
    ITEM_ID = "item_id"
    LAST_UPDATED = "last_updated"
    LINK = "link"
    LOCATION = "location"
    LONG_TEXT = "long_text"
    MIRROR = "mirror"
    NAME = "name"
    NUMBERS = "numbers"
    PEOPLE = "people"
    PHONE = "phone"
    PROGRESS = "progress"
    RATING = "rating"
    STATUS = "status"
    SUBTASKS = "subtasks"
    TAGS = "tags"
    TEAM = "team"
    TEXT = "text"
    TIME_TRACKING = "time_tracking"
    TIMELINE = "timeline"
    UNSUPPORTED = "unsupported"
    VOTE = "vote"
    WEEK = "week"
    WORLD_CLOCK = "world_clock"


class FetchMode(Enum):
    """
    fetchMode "schema": JSON settings schema only (GraphQL). fetchMode "guidelines": guidelines.filter and
    guidelines.aggregation only — no GraphQL round-trip.
    """

    SCHEMA = "schema"
    GUIDELINES = "guidelines"


class GetColumnTypeInfoInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnType: Annotated[
        ColumnType1,
        Field(description='The column type to retrieve information for (e.g., "text", "status", "date", "numbers")'),
    ]
    fetchMode: Annotated[
        Optional[FetchMode],
        Field(
            description=(
                'fetchMode "schema": JSON settings schema only (GraphQL). fetchMode "guidelines": guidelines.filter and'
                " guidelines.aggregation only — no GraphQL round-trip."
            )
        ),
    ] = FetchMode.SCHEMA


class GetTypeDetailsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    typeName: Annotated[str, Field(description="The name of the GraphQL type to get details for")]


class TargetType(Enum):
    """
    The target type (Post for update/reply, Project for item/board)
    """

    POST = "Post"
    PROJECT = "Project"


class CreateNotificationInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    user_id: Annotated[str, Field(description="The user ID to send the notification to")]
    target_id: Annotated[
        str, Field(description="The target ID (update/reply ID for Post type, item/board ID for Project type)")
    ]
    text: Annotated[str, Field(description="The notification text")]
    target_type: Annotated[
        TargetType, Field(description="The target type (Post for update/reply, Project for item/board)")
    ]


class Mode(Enum):
    """
    The operation mode. "content" (default) fetches documents with their markdown content. "version_history" fetches the edit history of a single document.
    """

    CONTENT = "content"
    VERSION_HISTORY = "version_history"


class Type2(Enum):
    """
    Query type for content mode: "ids", "object_ids", or "workspace_ids". Required when mode is "content".
    """

    IDS = "ids"
    OBJECT_IDS = "object_ids"
    WORKSPACE_IDS = "workspace_ids"


class OrderBy(Enum):
    """
    Order in which to retrieve docs. Only used in content mode.
    """

    CREATED_AT = "created_at"
    USED_AT = "used_at"


class ReadDocsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Annotated[
        Optional[Mode],
        Field(
            description=(
                'The operation mode. "content" (default) fetches documents with their markdown content.'
                ' "version_history" fetches the edit history of a single document.'
            )
        ),
    ] = Mode.CONTENT
    type: Annotated[
        Optional[Type2],
        Field(
            description=(
                'Query type for content mode: "ids", "object_ids", or "workspace_ids". Required when mode is "content".'
            )
        ),
    ] = None
    ids: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Array of ID values. In content mode: matches the query type (ids/object_ids/workspace_ids). In"
                ' version_history mode: provide the single document object_id here (e.g., ids: ["5001466606"]).'
            )
        ),
    ] = None
    limit: Annotated[
        Optional[float], Field(description="Number of docs per page (default: 25). Only used in content mode.")
    ] = None
    order_by: Annotated[
        Optional[OrderBy], Field(description="Order in which to retrieve docs. Only used in content mode.")
    ] = None
    page: Annotated[
        Optional[float], Field(description="Page number to return (starts at 1). Only used in content mode.")
    ] = None
    include_blocks: Annotated[
        Optional[bool],
        Field(
            description=(
                "If true, includes the blocks array (block IDs, types, positions, content) in the response. Required"
                " when you plan to call update_doc. Defaults to false to reduce response size. Only used in content"
                " mode."
            )
        ),
    ] = False
    blocks_limit: Annotated[
        Optional[float],
        Field(
            description=(
                "Maximum number of blocks to return per document (default: 25). Only used in content mode when"
                " include_blocks is true."
            )
        ),
    ] = None
    blocks_page: Annotated[
        Optional[float],
        Field(
            description=(
                "Page number for block pagination, starting at 1. Omit to use the API default. Use with blocks_limit to"
                " page through documents with more than 25 blocks. Only used in content mode when include_blocks is"
                " true."
            )
        ),
    ] = None
    include_comments: Annotated[
        Optional[bool],
        Field(
            description=(
                "If true, fetches all comments and replies on the document. Comments are stored at the item level"
                " within the doc backing board. Defaults to false. Only used in content mode."
            )
        ),
    ] = False
    comments_limit: Annotated[
        Optional[float],
        Field(
            description=(
                "Maximum number of comments (updates) to fetch per item when include_comments is true. Defaults to 50."
                " Only used in content mode."
            )
        ),
    ] = 50
    version_history_limit: Annotated[
        Optional[float],
        Field(
            description=(
                'Maximum number of restoring points to return. Use this when the user asks for "last N changes". Only'
                " used in version_history mode."
            )
        ),
    ] = None
    since: Annotated[
        Optional[str],
        Field(
            description=(
                'ISO 8601 date string to filter version history from (e.g., "2026-03-15T00:00:00Z"). If omitted,'
                " returns the full history. Only used in version_history mode."
            )
        ),
    ] = None
    until: Annotated[
        Optional[str],
        Field(
            description=(
                'ISO 8601 date string to filter version history until (e.g., "2026-03-16T23:59:59Z"). Defaults to now.'
                " Only used in version_history mode."
            )
        ),
    ] = None
    include_diff: Annotated[
        Optional[bool],
        Field(
            description=(
                "If true, fetches content diffs between consecutive restoring points. May be slower due to additional"
                " API calls. Only used in version_history mode."
            )
        ),
    ] = False


class WorkspaceInfoInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workspace_id: Annotated[float, Field(description="The ID of the workspace to get information for")]


class ListWorkspacesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    limit: Annotated[
        Optional[float],
        Field(
            description="Number of workspaces to return. Default is (100), lower for a smaller response size",
            ge=1.0,
            le=100.0,
        ),
    ] = 100
    page: Annotated[Optional[float], Field(description="Page number to return. Default is 1.", ge=1.0)] = 1


class Location1(Enum):
    """
    Location where the document should be created - either in a workspace or attached to an item
    """

    WORKSPACE = "workspace"
    ITEM = "item"


class DocKind(Enum):
    """
    [OPTIONAL - use only when location="workspace"] Document kind (public/private/share). Defaults to public.
    """

    PRIVATE = "private"
    PUBLIC = "public"
    SHARE = "share"


class CreateDocInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    doc_name: Annotated[str, Field(description="Name for the new document.")]
    markdown: Annotated[
        str, Field(description="Markdown content that will be imported into the newly created document as blocks.")
    ]
    location: Annotated[
        Location1,
        Field(
            description="Location where the document should be created - either in a workspace or attached to an item"
        ),
    ]
    docOwnerIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Optional list of user IDs to set as document owners at creation time. Use this to add the agent owner"
                " so they retain access to the document. Ownership is set inside the creation mutation itself,"
                " bypassing the permission checks that would block a subsequent add_subscribers_to_object call."
            ),
            min_length=1,
        ),
    ] = None
    workspace_id: Annotated[
        Optional[float],
        Field(
            description=(
                '[REQUIRED - use only when location="workspace"] Workspace ID under which to create the new document'
            )
        ),
    ] = None
    doc_kind: Annotated[
        Optional[DocKind],
        Field(
            description=(
                '[OPTIONAL - use only when location="workspace"] Document kind (public/private/share). Defaults to'
                " public."
            )
        ),
    ] = None
    folder_id: Annotated[
        Optional[float],
        Field(
            description=(
                '[OPTIONAL - use only when location="workspace"] Optional folder ID to place the document inside a'
                " specific folder"
            )
        ),
    ] = None
    item_id: Annotated[
        Optional[float],
        Field(description='[REQUIRED - use only when location="item"] Item ID to attach the new document to'),
    ] = None
    column_id: Annotated[
        Optional[str],
        Field(
            description=(
                '[OPTIONAL - use only when location="item"] ID of an existing "doc" column on the board which contains'
                " the item. If not provided, the tool will create a new doc column automatically when creating a doc on"
                " an item."
            )
        ),
    ] = None


class Operations(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["set_name"]
    name: Annotated[str, Field(description="New document name.", min_length=1)]


class Operations1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["add_markdown_content"]
    markdown: Annotated[str, Field(description="Markdown content to convert and append (or insert) as blocks.")]
    after_block_id: Annotated[
        Optional[str],
        Field(description="Insert after this block ID. Omit to append at end. Block IDs come from read_docs."),
    ] = None


class Insert(BaseModel):
    """
    Content to insert. Use {text: "..."} for plain text, {mention: {id, type}} to tag a user/doc/board,
    or {column_value: {item_id, column_id}} to embed a live column value. The last operation in the array must be {
    text: "\\n"}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    text: str


class Type3(Enum):
    """
    Mention type. USER is most common.
    """

    USER = "USER"
    DOC = "DOC"
    BOARD = "BOARD"


class Mention(BaseModel):
    """
    Mention blot — tags a user, doc, or board inline. Do not set attributes on mention ops.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        Union[str, float], Field(description="User, doc, or board ID. Get user IDs from list_users_and_teams.")
    ]
    type: Annotated[Optional[Type3], Field(description="Mention type. USER is most common.")] = Type3.USER


class Insert1(BaseModel):
    """
    Content to insert. Use {text: "..."} for plain text, {mention: {id, type}} to tag a user/doc/board,
    or {column_value: {item_id, column_id}} to embed a live column value. The last operation in the array must be {
    text: "\\n"}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    mention: Annotated[
        Mention,
        Field(description="Mention blot — tags a user, doc, or board inline. Do not set attributes on mention ops."),
    ]


class ColumnValue(BaseModel):
    """
    Column value blot — embeds a live board column value inline in the doc.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    item_id: Annotated[Union[str, float], Field(description="The board item ID.")]
    column_id: Annotated[
        str, Field(description='The column ID (e.g. "status", "date4"). Get column IDs from get_board_schema.')
    ]


class Insert2(BaseModel):
    """
    Content to insert. Use {text: "..."} for plain text, {mention: {id, type}} to tag a user/doc/board,
    or {column_value: {item_id, column_id}} to embed a live column value. The last operation in the array must be {
    text: "\\n"}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    column_value: Annotated[
        ColumnValue, Field(description="Column value blot — embeds a live board column value inline in the doc.")
    ]


class Attributes(BaseModel):
    """
    Optional formatting: bold, italic, underline, strike, code, link, color, background. Not applicable to mention or
    column_value ops.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    strike: Optional[bool] = None
    code: Optional[bool] = None
    link: Optional[str] = None
    color: Optional[str] = None
    background: Optional[str] = None


class DeltaFormatItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    insert: Annotated[
        Union[str, Insert, Insert1, Insert2],
        Field(
            description=(
                'Content to insert. Use {text: "..."} for plain text, {mention: {id, type}} to tag a user/doc/board, or'
                " {column_value: {item_id, column_id}} to embed a live column value. The last operation in the array"
                ' must be {text: "\\n"}.'
            )
        ),
    ]
    attributes: Annotated[
        Optional[Attributes],
        Field(
            description=(
                "Optional formatting: bold, italic, underline, strike, code, link, color, background. Not applicable to"
                " mention or column_value ops."
            )
        ),
    ] = None


class Alignment1(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


class Direction2(Enum):
    LTR = "LTR"
    RTL = "RTL"


class Content(BaseModel):
    """
    New content for the block. Use block_content_type to select: text (updates text/heading/quote content),
    code (updates code content), list_item (updates bullets/numbered/todo content). Cannot change block subtype — use
    replace_block for that.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_content_type: Literal["text"]
    delta_format: Annotated[
        list[DeltaFormatItem],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    alignment: Optional[Alignment1] = None
    direction: Optional[Direction2] = None


class TextBlockType(Enum):
    """
    Block subtype. LARGE_TITLE=H1, MEDIUM_TITLE=H2, SMALL_TITLE=H3.
    """

    NORMAL_TEXT = "NORMAL_TEXT"
    LARGE_TITLE = "LARGE_TITLE"
    MEDIUM_TITLE = "MEDIUM_TITLE"
    SMALL_TITLE = "SMALL_TITLE"
    QUOTE = "QUOTE"


class ListBlockType(Enum):
    """
    List type. Defaults to BULLETED_LIST.
    """

    BULLETED_LIST = "BULLETED_LIST"
    NUMBERED_LIST = "NUMBERED_LIST"
    CHECK_LIST = "CHECK_LIST"


class Block3(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["divider"]


class Block4(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["page_break"]


class AssetId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description=(
                "monday.com asset ID for the image. The image block will reference the asset directly. Provide either"
                " public_url or asset_id."
            ),
            pattern="^\\d+$",
        ),
    ]


class Block5(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["image"]
    public_url: Annotated[
        Optional[AnyUrl], Field(description="Publicly accessible image URL. Provide either public_url or asset_id.")
    ] = None
    asset_id: Annotated[
        Optional[Union[int, AssetId]],
        Field(
            description=(
                "monday.com asset ID for the image. The image block will reference the asset directly. Provide either"
                " public_url or asset_id."
            )
        ),
    ] = None
    width: Annotated[Optional[int], Field(description="Width in pixels.", ge=1)] = None


class Block6(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["video"]
    raw_url: Annotated[AnyUrl, Field(description="Video URL (YouTube, Vimeo, or direct video URL).")]
    width: Annotated[Optional[int], Field(description="Width in pixels.", ge=1)] = None


class Theme(Enum):
    """
    Visual style of the notice box.
    """

    INFO = "INFO"
    TIPS = "TIPS"
    WARNING = "WARNING"
    GENERAL = "GENERAL"


class Block7(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["notice_box"]
    theme: Annotated[Theme, Field(description="Visual style of the notice box.")]


class ColumnStyleItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    width: int


class Block8(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["table"]
    row_count: Annotated[int, Field(description="Number of rows (1–25).", ge=1, le=25)]
    column_count: Annotated[int, Field(description="Number of columns (1–10).", ge=1, le=10)]
    width: Annotated[Optional[int], Field(description="Table width in pixels.")] = None
    column_style: Annotated[
        Optional[list[ColumnStyleItem]],
        Field(description="Column widths. Array length must match column_count. Widths must sum to 100."),
    ] = None


class Block9(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["layout"]
    column_count: Annotated[int, Field(description="Number of columns (2–6).", ge=2, le=6)]
    column_style: Annotated[
        Optional[list[ColumnStyleItem]],
        Field(description="Column widths. Array length must match column_count. Widths must sum to 100."),
    ] = None


class Operations4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["delete_block"]
    block_id: Annotated[
        str,
        Field(
            description=(
                "ID of the block to permanently delete. Works for all block types including BOARD, WIDGET, DOC embed,"
                " GIPHY."
            )
        ),
    ]


class BlockId(RootModel[list[str]]):
    root: Annotated[
        list[str],
        Field(
            description=(
                "Block ID (string) or array of block IDs to anchor the comment to. When an array is provided, the same"
                " comment highlights all specified blocks. Only works on text-content blocks (text, code, list_item,"
                " title, quote) — not on divider, table, layout, notice_box, image, video, or giphy. Get block IDs from"
                " read_docs with include_blocks: true. Omit to create a general doc-level comment. Pair with"
                " selection_from + selection_length (single block_id only) to comment on a specific text range."
            ),
            min_length=1,
        ),
    ]


class Operations6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["add_comment"]
    body: Annotated[
        str,
        Field(
            description=(
                "The comment text. Use HTML tags for formatting (not markdown). Do not use @ to mention users — use"
                " mentions_list instead."
            ),
            min_length=1,
        ),
    ]
    parent_update_id: Annotated[
        Optional[float],
        Field(
            description=(
                "The ID of an existing comment (update) to reply to. Omit to create a new top-level comment. Get"
                " comment IDs from read_docs with include_comments: true."
            )
        ),
    ] = None
    mentions_list: Annotated[
        Optional[str],
        Field(
            description=(
                'Optional JSON array of mentions: [{"id": "123", "type": "User"}, {"id": "456", "type": "Team"}]. Valid'
                " types: User, Team, Board, Project."
            )
        ),
    ] = None
    block_id: Annotated[
        Optional[Union[str, BlockId]],
        Field(
            description=(
                "Block ID (string) or array of block IDs to anchor the comment to. When an array is provided, the same"
                " comment highlights all specified blocks. Only works on text-content blocks (text, code, list_item,"
                " title, quote) — not on divider, table, layout, notice_box, image, video, or giphy. Get block IDs from"
                " read_docs with include_blocks: true. Omit to create a general doc-level comment. Pair with"
                " selection_from + selection_length (single block_id only) to comment on a specific text range."
            )
        ),
    ] = None
    selection_from: Annotated[
        Optional[int],
        Field(
            description=(
                "Start character offset (0-indexed) of the selected text within the block. Requires block_id. Omit to"
                " comment on the entire block."
            ),
            ge=0,
        ),
    ] = None
    selection_length: Annotated[
        Optional[int],
        Field(
            description=(
                "Number of characters in the text selection. Requires block_id and selection_from. Only works for text,"
                " code, and list_item blocks that have a delta format."
            ),
            ge=1,
        ),
    ] = None


class AttributeKind(Enum):
    """
    The kind of the workspace to update (open / closed / template)
    """

    CLOSED = "closed"
    OPEN = "open"
    TEMPLATE = "template"


class UpdateWorkspaceInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="The ID of the workspace to update")]
    attributeAccountProductId: Annotated[
        Optional[float], Field(description="The target account product's ID to move the workspace to")
    ] = None
    attributeDescription: Annotated[Optional[str], Field(description="The description of the workspace to update")] = (
        None
    )
    attributeKind: Annotated[
        Optional[AttributeKind], Field(description="The kind of the workspace to update (open / closed / template)")
    ] = None
    attributeName: Annotated[Optional[str], Field(description="The name of the workspace to update")] = None


class Color(Enum):
    """
    The new color of the folder
    """

    AQUAMARINE = "AQUAMARINE"
    BRIGHT_BLUE = "BRIGHT_BLUE"
    BRIGHT_GREEN = "BRIGHT_GREEN"
    CHILI_BLUE = "CHILI_BLUE"
    DARK_ORANGE = "DARK_ORANGE"
    DARK_PURPLE = "DARK_PURPLE"
    DARK_RED = "DARK_RED"
    DONE_GREEN = "DONE_GREEN"
    INDIGO = "INDIGO"
    LIPSTICK = "LIPSTICK"
    NULL = "NULL"
    PURPLE = "PURPLE"
    SOFIA_PINK = "SOFIA_PINK"
    STUCK_RED = "STUCK_RED"
    SUNSET = "SUNSET"
    WORKING_ORANGE = "WORKING_ORANGE"


class FontWeight(Enum):
    """
    The new font weight of the folder
    """

    FONT_WEIGHT_BOLD = "FONT_WEIGHT_BOLD"
    FONT_WEIGHT_LIGHT = "FONT_WEIGHT_LIGHT"
    FONT_WEIGHT_NORMAL = "FONT_WEIGHT_NORMAL"
    FONT_WEIGHT_VERY_LIGHT = "FONT_WEIGHT_VERY_LIGHT"
    NULL = "NULL"


class CustomIcon(Enum):
    """
    The new custom icon of the folder
    """

    FOLDER = "FOLDER"
    MOREBELOW = "MOREBELOW"
    MOREBELOWFILLED = "MOREBELOWFILLED"
    NULL = "NULL"
    WORK = "WORK"


class PositionObjectType(Enum):
    """
    The type of object to position the folder relative to. If this parameter is provided, position_object_id must be
    also provided.
    """

    BOARD = "Board"
    FOLDER = "Folder"
    OVERVIEW = "Overview"


class UpdateFolderInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    folderId: Annotated[str, Field(description="The ID of the folder to update")]
    name: Annotated[Optional[str], Field(description="The new name of the folder")] = None
    color: Annotated[Optional[Color], Field(description="The new color of the folder")] = None
    fontWeight: Annotated[Optional[FontWeight], Field(description="The new font weight of the folder")] = None
    customIcon: Annotated[Optional[CustomIcon], Field(description="The new custom icon of the folder")] = None
    parentFolderId: Annotated[Optional[str], Field(description="The ID of the new parent folder")] = None
    workspaceId: Annotated[Optional[str], Field(description="The ID of the workspace containing the folder")] = None
    accountProductId: Annotated[
        Optional[str], Field(description="The account product ID associated with the folder")
    ] = None
    position_object_id: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of the object to position the folder relative to. If this parameter is provided,"
                " position_object_type must be also provided."
            )
        ),
    ] = None
    position_object_type: Annotated[
        Optional[PositionObjectType],
        Field(
            description=(
                "The type of object to position the folder relative to. If this parameter is provided,"
                " position_object_id must be also provided."
            )
        ),
    ] = None
    position_is_after: Annotated[
        Optional[bool], Field(description="Whether to position the folder after the object")
    ] = None


class WorkspaceKind(Enum):
    """
    The kind of workspace to create
    """

    CLOSED = "closed"
    OPEN = "open"
    TEMPLATE = "template"


class CreateWorkspaceInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(description="The name of the new workspace to be created")]
    workspaceKind: Annotated[WorkspaceKind, Field(description="The kind of workspace to create")]
    description: Annotated[Optional[str], Field(description="The description of the new workspace")] = None
    accountProductId: Annotated[
        Optional[str], Field(description="The account product ID associated with the workspace")
    ] = None


class Color1(Enum):
    """
    The color of the folder
    """

    AQUAMARINE = "AQUAMARINE"
    BRIGHT_BLUE = "BRIGHT_BLUE"
    BRIGHT_GREEN = "BRIGHT_GREEN"
    CHILI_BLUE = "CHILI_BLUE"
    DARK_ORANGE = "DARK_ORANGE"
    DARK_PURPLE = "DARK_PURPLE"
    DARK_RED = "DARK_RED"
    DONE_GREEN = "DONE_GREEN"
    INDIGO = "INDIGO"
    LIPSTICK = "LIPSTICK"
    NULL = "NULL"
    PURPLE = "PURPLE"
    SOFIA_PINK = "SOFIA_PINK"
    STUCK_RED = "STUCK_RED"
    SUNSET = "SUNSET"
    WORKING_ORANGE = "WORKING_ORANGE"


class FontWeight1(Enum):
    """
    The font weight of the folder
    """

    FONT_WEIGHT_BOLD = "FONT_WEIGHT_BOLD"
    FONT_WEIGHT_LIGHT = "FONT_WEIGHT_LIGHT"
    FONT_WEIGHT_NORMAL = "FONT_WEIGHT_NORMAL"
    FONT_WEIGHT_VERY_LIGHT = "FONT_WEIGHT_VERY_LIGHT"
    NULL = "NULL"


class CustomIcon1(Enum):
    """
    The custom icon of the folder
    """

    FOLDER = "FOLDER"
    MOREBELOW = "MOREBELOW"
    MOREBELOWFILLED = "MOREBELOWFILLED"
    NULL = "NULL"
    WORK = "WORK"


class CreateFolderInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workspaceId: Annotated[str, Field(description="The ID of the workspace where the folder will be created")]
    name: Annotated[str, Field(description="The name of the folder to be created")]
    color: Annotated[Optional[Color1], Field(description="The color of the folder")] = None
    fontWeight: Annotated[Optional[FontWeight1], Field(description="The font weight of the folder")] = None
    customIcon: Annotated[Optional[CustomIcon1], Field(description="The custom icon of the folder")] = None
    parentFolderId: Annotated[Optional[str], Field(description="The ID of the parent folder")] = None


class ObjectType1(Enum):
    """
    The type of object to move
    """

    BOARD = "Board"
    FOLDER = "Folder"
    OVERVIEW = "Overview"


class PositionObjectType1(Enum):
    """
    The type of object to position the object relative to. If this parameter is provided, position_object_id must be
    also provided.
    """

    BOARD = "Board"
    FOLDER = "Folder"
    OVERVIEW = "Overview"


class MoveObjectInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    objectType: Annotated[ObjectType1, Field(description="The type of object to move")]
    id: Annotated[str, Field(description="The ID of the object to move")]
    position_object_id: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of the object to position the object relative to. If this parameter is provided,"
                " position_object_type must be also provided."
            )
        ),
    ] = None
    position_object_type: Annotated[
        Optional[PositionObjectType1],
        Field(
            description=(
                "The type of object to position the object relative to. If this parameter is provided,"
                " position_object_id must be also provided."
            )
        ),
    ] = None
    position_is_after: Annotated[
        Optional[bool], Field(description="Whether to position the object after the object")
    ] = None
    parentFolderId: Annotated[
        Optional[str], Field(description="The ID of the new parent folder. Required if moving to a different folder.")
    ] = None
    workspaceId: Annotated[
        Optional[str],
        Field(
            description="The ID of the workspace containing the object. Required if moving to a different workspace."
        ),
    ] = None
    accountProductId: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of the account product containing the object. Required if moving to a different account"
                " product."
            )
        ),
    ] = None


class Kind(Enum):
    """
    Visibility level: PUBLIC or PRIVATE
    """

    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class CreateDashboardInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(description="Human-readable dashboard title (UTF-8 chars)", min_length=1)]
    workspace_id: Annotated[str, Field(description="ID of the workspace that will own the dashboard")]
    board_ids: Annotated[
        list[str], Field(description="List of board IDs as strings (min 1 element)", max_length=50, min_length=1)
    ]
    kind: Annotated[Optional[Kind], Field(description="Visibility level: PUBLIC or PRIVATE")] = Kind.PUBLIC
    board_folder_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional folder ID within workspace to place this dashboard (if not provided, dashboard will be placed"
                " in workspace root)"
            )
        ),
    ] = None


class AllWidgetsSchemaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class ParentContainerType(Enum):
    """
    Type of parent container: DASHBOARD or BOARD_VIEW
    """

    BOARD_VIEW = "BOARD_VIEW"
    DASHBOARD = "DASHBOARD"


class WidgetKind(Enum):
    """
    Type of widget to create: i.e CHART, NUMBER, BATTERY
    """

    APP_FEATURE = "APP_FEATURE"
    BATTERY = "BATTERY"
    CALENDAR = "CALENDAR"
    CHART = "CHART"
    GANTT = "GANTT"
    LISTVIEW = "LISTVIEW"
    NUMBER = "NUMBER"


class CreateWidgetInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    parent_container_id: Annotated[str, Field(description="ID of the parent container (dashboard ID or board view ID)")]
    parent_container_type: Annotated[
        ParentContainerType, Field(description="Type of parent container: DASHBOARD or BOARD_VIEW")
    ]
    widget_kind: Annotated[WidgetKind, Field(description="Type of widget to create: i.e CHART, NUMBER, BATTERY")]
    widget_name: Annotated[
        str, Field(description="Widget display name (1-255 UTF-8 chars)", max_length=255, min_length=1)
    ]
    settings: Annotated[
        Optional[dict[str, Any]],
        Field(
            description=(
                "Widget-specific settings as JSON object conforming to widget schema. Use all_widgets_schema tool to"
                " get the required schema for each widget type."
            )
        ),
    ] = None


class Function(Enum):
    """
    The function of the aggregation. For simple column value leave undefined
    """

    AVERAGE = "AVERAGE"
    COLOR = "COLOR"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    COUNT_ITEMS = "COUNT_ITEMS"
    COUNT_SUBITEMS = "COUNT_SUBITEMS"
    DATE = "DATE"
    DATE_TRUNC_DAY = "DATE_TRUNC_DAY"
    DATE_TRUNC_MONTH = "DATE_TRUNC_MONTH"
    DATE_TRUNC_QUARTER = "DATE_TRUNC_QUARTER"
    DATE_TRUNC_WEEK = "DATE_TRUNC_WEEK"
    DATE_TRUNC_YEAR = "DATE_TRUNC_YEAR"
    DURATION_RUNNING = "DURATION_RUNNING"
    END_DATE = "END_DATE"
    EQUALS = "EQUALS"
    FIRST = "FIRST"
    FLATTEN = "FLATTEN"
    HOUR = "HOUR"
    ID = "ID"
    IS_DONE = "IS_DONE"
    LABEL = "LABEL"
    LENGTH = "LENGTH"
    LOWER = "LOWER"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    MIN = "MIN"
    MIN_MAX = "MIN_MAX"
    ORDER = "ORDER"
    PERSON = "PERSON"
    PHONE_COUNTRY_SHORT_NAME = "PHONE_COUNTRY_SHORT_NAME"
    START_DATE = "START_DATE"
    SUM = "SUM"
    TRIM = "TRIM"
    UPPER = "UPPER"


class Aggregation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    function: Annotated[
        Optional[Function],
        Field(description="The function of the aggregation. For simple column value leave undefined"),
    ] = None
    columnId: Annotated[str, Field(description="The id of the column to aggregate")]


class Operator4(Enum):
    """
    The operator to use for the filter
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Filter1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="The id of the column to filter by")]
    compareAttribute: Annotated[
        Optional[str], Field(description="The attribute to compare the value to. This is OPTIONAL property.")
    ] = None
    compareValue: Annotated[
        Union[str, float, bool, list[Union[str, float]]],
        Field(
            description=(
                "The value to compare the attribute to. This can be a string or index value depending on the column"
                " type."
            )
        ),
    ]
    operator: Annotated[Optional[Operator4], Field(description="The operator to use for the filter")] = Operator4.ANY_OF


class Direction4(Enum):
    """
    The direction to order by
    """

    ASC = "asc"
    DESC = "desc"


class OrderByItem1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="The id of the column to order by")]
    direction: Annotated[Optional[Direction4], Field(description="The direction to order by")] = Direction4.ASC


class BoardInsightsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[float, Field(description="The id of the board to get insights for")]
    aggregations: Annotated[
        Optional[list[Aggregation]],
        Field(
            description=(
                "The aggregations to get. Before sending the aggregations, read guidelines.aggregation from"
                ' get_column_type_info with fetchMode "guidelines" for a relevant column type on this board.'
                " Transformative functions and plain columns (no function) must be in group by."
            )
        ),
    ] = None
    groupBy: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The columns to group by. All columns in the group by must be in the aggregations as well without a"
                " function."
            )
        ),
    ] = None
    limit: Annotated[Optional[float], Field(description="The limit of the results", le=1000.0)] = 1000
    filters: Annotated[
        Optional[list[Filter1]],
        Field(
            description=(
                "The configuration of filters to apply on the items. Use get_board_info for column ids and types on the"
                ' board. Before sending the filters, use get_column_type_info with fetchMode "guidelines" and use'
                " data.guidelines.filter (null if that type has no documented rules)."
            )
        ),
    ] = None
    filtersOperator: Annotated[Optional[FiltersOperator], Field(description="The operator to use for the filters")] = (
        FiltersOperator.AND
    )
    orderBy: Annotated[
        Optional[list[OrderByItem1]],
        Field(description="The columns to order by, will control the order of the items in the response"),
    ] = None


class SearchType(Enum):
    """
    The type of search to perform.
    """

    BOARD = "BOARD"
    DOCUMENTS = "DOCUMENTS"
    FOLDERS = "FOLDERS"
    WORKSPACES = "WORKSPACES"
    UPDATES = "UPDATES"
    ITEMS = "ITEMS"


class SearchInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    searchTerm: Annotated[Optional[str], Field(description="The search term to use for the search.")] = None
    searchType: Annotated[SearchType, Field(description="The type of search to perform.")]
    limit: Annotated[
        Optional[float], Field(description="The number of items to get. The max and default value is 20.", le=20.0)
    ] = 20
    page: Annotated[Optional[float], Field(description="The page number to get. The default value is 1.")] = 1
    workspaceIds: Annotated[
        Optional[list[float]],
        Field(
            description=(
                "The ids of the workspaces to search in. [IMPORTANT] Only pass this param if user explicitly asked to"
                " search within specific workspaces."
            )
        ),
    ] = None
    boardIds: Annotated[
        Optional[list[float]],
        Field(
            description=(
                "The ids of the boards to scope the search to. [IMPORTANT] Only applies to UPDATES search, and only"
                " pass it if the user explicitly asked to search within specific boards."
            )
        ),
    ] = None
    creatorIds: Annotated[
        Optional[list[float]],
        Field(
            description=(
                "The ids of the users whose updates to search. [IMPORTANT] Only applies to UPDATES search, and only"
                " pass it if the user explicitly asked to search updates by specific authors."
            )
        ),
    ] = None


class GetUserContextInput(BaseModel):
    pass


class GetAssetsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    ids: Annotated[list[str], Field(description="Array of asset IDs to fetch", min_length=1)]


class Access(Enum):
    """
    Filter meetings by access level. OWN: meetings the user participated in or invited the bot to. SHARED_WITH_ME:
    meetings shared with the user or their team. SHARED_WITH_ACCOUNT: meetings shared with the entire account. ALL:
    all meetings the user has access to.
    """

    OWN = "OWN"
    SHARED_WITH_ME = "SHARED_WITH_ME"
    SHARED_WITH_ACCOUNT = "SHARED_WITH_ACCOUNT"
    ALL = "ALL"


class GetNotetakerMeetingsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    ids: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Filter by specific meeting IDs. Use this to fetch one or more specific meetings in a single call."
            )
        ),
    ] = None
    access: Annotated[
        Optional[Access],
        Field(
            description=(
                "Filter meetings by access level. OWN: meetings the user participated in or invited the bot to."
                " SHARED_WITH_ME: meetings shared with the user or their team. SHARED_WITH_ACCOUNT: meetings shared"
                " with the entire account. ALL: all meetings the user has access to."
            )
        ),
    ] = Access.OWN
    limit: Annotated[
        Optional[float],
        Field(description="Maximum number of notetaker meetings to return per page (1-100).", ge=1.0, le=100.0),
    ] = 25
    cursor: Annotated[
        Optional[str],
        Field(description="Cursor for pagination. Use cursor from the previous page_info to fetch the next page."),
    ] = None
    search: Annotated[
        Optional[str], Field(description="Search notetaker meetings by title, participant name, or email.")
    ] = None
    include_summary: Annotated[
        Optional[bool], Field(description="Whether to include the AI-generated summary for each meeting.")
    ] = False
    include_topics: Annotated[
        Optional[bool], Field(description="Whether to include discussion topics and talking points for each meeting.")
    ] = False
    include_action_items: Annotated[
        Optional[bool], Field(description="Whether to include action items for each meeting.")
    ] = False
    include_transcript: Annotated[
        Optional[bool],
        Field(description="Whether to include the full transcript for each meeting. Transcripts can be very large."),
    ] = False


class Type4(Enum):
    """
    The type of board view to create. Use TABLE for standard board views.
    """

    APP = "APP"
    DASHBOARD = "DASHBOARD"
    FORM = "FORM"
    TABLE = "TABLE"


class Operator5(Enum):
    """
    The comparison operator (defaults to any_of)
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Rule1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to filter by")]
    compare_value: Annotated[Optional[Any], Field(description="The value(s) to compare against")] = []
    operator: Annotated[Optional[Operator5], Field(description="The comparison operator (defaults to any_of)")] = None


class Operator6(Enum):
    """
    Logical operator between rules (defaults to and)
    """

    AND = "and"
    OR = "or"


class Filter2(BaseModel):
    """
    Filter configuration for the view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    rules: Annotated[Optional[list[Rule1]], Field(description="Filter rules")] = None
    operator: Annotated[Optional[Operator6], Field(description="Logical operator between rules (defaults to and)")] = (
        None
    )


class Direction5(Enum):
    """
    Sort direction (defaults to asc)
    """

    ASC = "asc"
    DESC = "desc"


class SortItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to sort by")]
    direction: Annotated[Optional[Direction5], Field(description="Sort direction (defaults to asc)")] = None


class CreateViewInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[str, Field(description="The board ID to create the view on")]
    type: Annotated[
        Optional[Type4], Field(description="The type of board view to create. Use TABLE for standard board views.")
    ] = Type4.TABLE
    name: Annotated[
        Optional[str], Field(description='The name of the view (e.g. "High Priority Items", "My Tasks")')
    ] = None
    filter: Annotated[Optional[Filter2], Field(description="Filter configuration for the view")] = None
    sort: Annotated[Optional[list[SortItem]], Field(description="Sort configuration for the view")] = None
    settings: Annotated[
        Optional[Any],
        Field(
            description=(
                "Type-specific view settings as a JSON object (e.g. column visibility, group_by for TABLE). The shape"
                " varies by view type — call get_view_schema_by_type with the same ViewKind to discover the supported"
                " structure. For TABLE views, prefer the dedicated create_view_table tool which exposes a"
                " strongly-typed settings field."
            )
        ),
    ] = None


class Type5(Enum):
    """
    The type of the board view being updated. Use TABLE for standard board views.
    """

    APP = "APP"
    DASHBOARD = "DASHBOARD"
    FORM = "FORM"
    TABLE = "TABLE"


class Operator7(Enum):
    """
    The comparison operator (defaults to any_of)
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Rule2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to filter by")]
    compare_value: Annotated[Optional[Any], Field(description="The value(s) to compare against")] = []
    operator: Annotated[Optional[Operator7], Field(description="The comparison operator (defaults to any_of)")] = None


class Operator8(Enum):
    """
    Logical operator between rules (defaults to and)
    """

    AND = "and"
    OR = "or"


class Filter3(BaseModel):
    """
    Filter configuration to apply to the view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    rules: Annotated[Optional[list[Rule2]], Field(description="Filter rules")] = None
    operator: Annotated[Optional[Operator8], Field(description="Logical operator between rules (defaults to and)")] = (
        None
    )


class SortItem1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to sort by")]
    direction: Annotated[Optional[Direction5], Field(description="Sort direction (defaults to asc)")] = None


class UpdateViewInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    viewId: Annotated[str, Field(description="The ID of the view to update")]
    boardId: Annotated[str, Field(description="The board ID the view belongs to")]
    type: Annotated[
        Optional[Type5],
        Field(description="The type of the board view being updated. Use TABLE for standard board views."),
    ] = Type5.TABLE
    name: Annotated[Optional[str], Field(description="New name for the view (omit to leave unchanged)")] = None
    filter: Annotated[Optional[Filter3], Field(description="Filter configuration to apply to the view")] = None
    sort: Annotated[Optional[list[SortItem1]], Field(description="Sort configuration for the view")] = None
    settings: Annotated[
        Optional[Any],
        Field(
            description=(
                "Type-specific view settings as a JSON object (e.g. column visibility, group_by for TABLE). The shape"
                " varies by view type — call get_view_schema_by_type with the same ViewKind to discover the supported"
                " structure. For TABLE views, prefer the dedicated update_view_table tool which exposes a"
                " strongly-typed settings field."
            )
        ),
    ] = None


class Operator9(Enum):
    """
    The comparison operator (defaults to any_of)
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Rule3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to filter by")]
    compare_value: Annotated[Optional[Any], Field(description="The value(s) to compare against")] = []
    operator: Annotated[Optional[Operator9], Field(description="The comparison operator (defaults to any_of)")] = None


class Operator10(Enum):
    """
    Logical operator between rules (defaults to and)
    """

    AND = "and"
    OR = "or"


class Filter4(BaseModel):
    """
    Filter configuration for the view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    rules: Annotated[Optional[list[Rule3]], Field(description="Filter rules")] = None
    operator: Annotated[Optional[Operator10], Field(description="Logical operator between rules (defaults to and)")] = (
        None
    )


class SortItem2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to sort by")]
    direction: Annotated[Optional[Direction5], Field(description="Sort direction (defaults to asc)")] = None


class ColumnProperty(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The ID of the column")]
    visible: Annotated[bool, Field(description="Whether the column is visible")]


class Direction8(Enum):
    """
    Sort direction (ASC or DESC)
    """

    ASC = "ASC"
    DESC = "DESC"


class SortSettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    direction: Annotated[Direction8, Field(description="Sort direction (ASC or DESC)")]
    type: Annotated[Optional[str], Field(description="Type of sorting to apply")] = None


class Config(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sortSettings: Optional[SortSettings] = None


class Condition1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="ID of the column to group by")]
    config: Optional[Config] = None


class GroupBy(BaseModel):
    """
    Group-by configuration for the table view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    conditions: Annotated[list[Condition1], Field(description="Group-by conditions")]
    hideEmptyGroups: Annotated[Optional[bool], Field(description="Whether to hide groups with no items")] = None


class Operator11(Enum):
    """
    The comparison operator (defaults to any_of)
    """

    ANY_OF = "any_of"
    BETWEEN = "between"
    CONTAINS_TERMS = "contains_terms"
    CONTAINS_TEXT = "contains_text"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    NOT_ANY_OF = "not_any_of"
    NOT_CONTAINS_TEXT = "not_contains_text"
    STARTS_WITH = "starts_with"
    WITHIN_THE_LAST = "within_the_last"
    WITHIN_THE_NEXT = "within_the_next"


class Rule4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to filter by")]
    compare_value: Annotated[Optional[Any], Field(description="The value(s) to compare against")] = []
    operator: Annotated[Optional[Operator11], Field(description="The comparison operator (defaults to any_of)")] = None


class Operator12(Enum):
    """
    Logical operator between rules (defaults to and)
    """

    AND = "and"
    OR = "or"


class Filter5(BaseModel):
    """
    Filter configuration to apply to the view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    rules: Annotated[Optional[list[Rule4]], Field(description="Filter rules")] = None
    operator: Annotated[Optional[Operator12], Field(description="Logical operator between rules (defaults to and)")] = (
        None
    )


class Direction9(Enum):
    """
    Sort direction (defaults to asc)
    """

    ASC = "asc"
    DESC = "desc"


class SortItem3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    column_id: Annotated[str, Field(description="The column ID to sort by")]
    direction: Annotated[Optional[Direction9], Field(description="Sort direction (defaults to asc)")] = None


class Direction10(Enum):
    """
    Sort direction (ASC or DESC)
    """

    ASC = "ASC"
    DESC = "DESC"


class SortSettings1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    direction: Annotated[Direction10, Field(description="Sort direction (ASC or DESC)")]
    type: Annotated[Optional[str], Field(description="Type of sorting to apply")] = None


class Config1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sortSettings: Optional[SortSettings1] = None


class Condition2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="ID of the column to group by")]
    config: Optional[Config1] = None


class GroupBy1(BaseModel):
    """
    Group-by configuration for the table view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    conditions: Annotated[list[Condition2], Field(description="Group-by conditions")]
    hideEmptyGroups: Annotated[Optional[bool], Field(description="Whether to hide groups with no items")] = None


class GetAssetUploadUrlInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fileName: Annotated[
        str, Field(description='The name of the file to upload, including extension (e.g. "report.pdf")')
    ]
    contentType: Annotated[
        str, Field(description='The MIME type of the file (e.g. "application/pdf", "image/png", "text/plain")')
    ]
    fileSize: Annotated[
        int, Field(description="The file size in bytes. Maximum 500MB (524288000 bytes)", gt=0, le=524288000)
    ]


class FinalizeAssetUploadInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uploadId: Annotated[str, Field(description="The upload_id returned by get_asset_upload_url")]
    etag: Annotated[
        str, Field(description="The ETag header value from the PUT response when uploading to the presigned URL")
    ]
    boardId: Annotated[str, Field(description="The board's unique identifier")]
    itemId: Annotated[str, Field(description="The item's unique identifier")]
    columnId: Annotated[
        str, Field(description="The file or doc column's unique identifier to attach the uploaded asset to")
    ]


class Action2(Enum):
    """
    "create" — create a new agent via AI (pass prompt). "create_blank" — create a new agent manually (pass
    name/role/etc). "get" — fetch one agent by agent_id or list owned agents. "update" — modify mutable fields on an
    existing agent. "delete" — permanently delete an agent (irreversible). "activate" — transition agent to ACTIVE.
    "deactivate" — transition agent to INACTIVE. "run" — manually enqueue an agent run (fire-and-forget).
    """

    CREATE = "create"
    CREATE_BLANK = "create_blank"
    GET = "get"
    UPDATE = "update"
    DELETE = "delete"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    RUN = "run"


class AgentModel(Enum):
    """
    Used with action:"create" or action:"update". Omit unless the user explicitly names a valid monday-supported model.
    """

    CLAUDE_FABLE_5 = "CLAUDE_FABLE_5"
    CLAUDE_OPUS_4_7 = "CLAUDE_OPUS_4_7"
    CLAUDE_SONNET_4_6 = "CLAUDE_SONNET_4_6"
    GEMINI_2_5_FLASH = "GEMINI_2_5_FLASH"
    GPT_5_2 = "GPT_5_2"


class Gender(Enum):
    """
    Used with action:"create_blank". Hint for generated avatar/name when profile fields are omitted.
    """

    MALE = "male"
    FEMALE = "female"


class ManageAgentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action2,
        Field(
            description=(
                '"create" — create a new agent via AI (pass prompt). "create_blank" — create a new agent manually (pass'
                ' name/role/etc). "get" — fetch one agent by agent_id or list owned agents. "update" — modify mutable'
                ' fields on an existing agent. "delete" — permanently delete an agent (irreversible). "activate" —'
                ' transition agent to ACTIVE. "deactivate" — transition agent to INACTIVE. "run" — manually enqueue an'
                " agent run (fire-and-forget)."
            )
        ),
    ]
    agent_id: Annotated[
        Optional[str],
        Field(
            description=(
                'Used with action:"get" to fetch a specific agent. Required for action:"update", "delete", "activate",'
                ' "deactivate", "run". Omit for action:"create", "create_blank", or action:"get" (to list owned'
                " agents)."
            ),
            min_length=1,
        ),
    ] = None
    prompt: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"create". Plain-language description of what the agent should do. Platform'
                " generates profile, goal, and plan via AI."
            ),
            min_length=1,
        ),
    ] = None
    agent_model: Annotated[
        Optional[AgentModel],
        Field(
            description=(
                'Used with action:"create" or action:"update". Omit unless the user explicitly names a valid'
                " monday-supported model."
            )
        ),
    ] = None
    name: Annotated[
        Optional[str],
        Field(
            description='Used with action:"create_blank" or action:"update". Display name of the agent.', min_length=1
        ),
    ] = None
    role: Annotated[
        Optional[str],
        Field(
            description=(
                'Used with action:"create_blank" or action:"update". Short role title (e.g. "Customer Success Bot").'
            ),
            min_length=1,
        ),
    ] = None
    role_description: Annotated[
        Optional[str],
        Field(
            description='Used with action:"create_blank" or action:"update". Detailed description of the agent role.',
            min_length=1,
        ),
    ] = None
    avatar_url: Annotated[
        Optional[str],
        Field(
            description=(
                'Used with action:"create_blank". HTTPS URL of the avatar. Prefer dapulse-res.cloudinary.com or'
                " cdn.monday.com."
            ),
            min_length=1,
        ),
    ] = None
    gender: Annotated[
        Optional[Gender],
        Field(
            description=(
                'Used with action:"create_blank". Hint for generated avatar/name when profile fields are omitted.'
            )
        ),
    ] = None
    background_color: Annotated[
        Optional[str],
        Field(description='Used with action:"create_blank". Lowercase hex, e.g. "#9450fd".', min_length=1),
    ] = None
    user_prompt: Annotated[
        Optional[str],
        Field(
            description='Used with action:"create_blank". Stored as metadata. Not used for AI generation.', min_length=1
        ),
    ] = None
    plan: Annotated[
        Optional[str],
        Field(description='Used with action:"update". New step-by-step execution plan in markdown.', min_length=1),
    ] = None


class Action3(Enum):
    """
    "list" — returns all triggers currently attached to this agent (includes node_id needed for remove). "add" —
    attaches a new trigger by block_reference_id. "remove" — detaches a trigger instance by node_id.
    """

    LIST = "list"
    ADD = "add"
    REMOVE = "remove"


class FieldValues(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    value: str
    label: str


class ManageAgentTriggersInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action3,
        Field(
            description=(
                '"list" — returns all triggers currently attached to this agent (includes node_id needed for remove).'
                ' "add" — attaches a new trigger by block_reference_id. "remove" — detaches a trigger instance by'
                " node_id."
            )
        ),
    ]
    agent_id: Annotated[str, Field(description="Unique identifier of the agent.", min_length=1)]
    block_reference_id: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"add". The block_reference_id from agent_catalog action:"list_triggers"'
                " identifying the trigger type to attach. Never guess this value — look it up in the catalog first."
            ),
            min_length=1,
        ),
    ] = None
    field_values: Annotated[
        Optional[dict[str, Union[str, float, bool, FieldValues]]],
        Field(
            description=(
                'Used with action:"add" when the trigger type has required_fields. Key/value object whose shape is'
                " described by field_schemas in the agent_catalog response. Scalar fields use string/number/boolean"
                ' values. Selection fields use { "value": "<id>", "label": "<name>" }.'
            )
        ),
    ] = None
    node_id: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"remove". The node_id of the trigger instance — get it from action:"list". Each'
                " instance has a unique node_id even if the same trigger type is attached multiple times. Do NOT pass"
                " block_reference_id here."
            ),
            min_length=1,
        ),
    ] = None


class Action4(Enum):
    """
    "create" — author a new custom skill in the account-wide catalog (no agent_id needed). "add" — attach an existing
    skill to this agent by skill_id. "remove" — detach a skill from this agent.
    """

    CREATE = "create"
    ADD = "add"
    REMOVE = "remove"


class ManageAgentSkillsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action4,
        Field(
            description=(
                '"create" — author a new custom skill in the account-wide catalog (no agent_id needed). "add" — attach'
                ' an existing skill to this agent by skill_id. "remove" — detach a skill from this agent.'
            )
        ),
    ]
    agent_id: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"add" and action:"remove". Not used for action:"create" (account-level operation).'
            ),
            min_length=1,
        ),
    ] = None
    name: Annotated[
        Optional[str], Field(description='Required for action:"create". Display name of the new skill.', min_length=1)
    ] = None
    content: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"create". Markdown instructions defining what the skill does and how to execute'
                " it. Be specific and thorough — this is the skill's runtime behavior."
            ),
            min_length=1,
        ),
    ] = None
    description: Annotated[
        Optional[str],
        Field(description='Used with action:"create". Short description shown in the catalog.', min_length=1),
    ] = None
    skill_id: Annotated[
        Optional[str],
        Field(
            description=(
                'Required for action:"add" and action:"remove". The skill id from agent_catalog action:"list_skills",'
                ' or the id returned by action:"create" in this tool. Never guess or invent a skill id.'
            ),
            min_length=1,
        ),
    ] = None


class Action5(Enum):
    """
    "list" — returns all resources the agent currently has access to. "add" — grants access to a board or doc.
    "update" — changes the permission level on an existing resource. "remove" — revokes the agent's access to a board
    or doc.
    """

    LIST = "list"
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


class ScopeType(Enum):
    """
    Required for action:add, action:update, action:remove. The type of resource: "BOARD" or "DOC".
    """

    BOARD = "BOARD"
    DOC = "DOC"


class PermissionType(Enum):
    """
    Required for action:add and action:update. The permission level: "READ" (agent can read the resource) or
    "READ_WRITE" (agent can read and write the resource).
    """

    READ = "READ"
    READ_WRITE = "READ_WRITE"


class ManageAgentKnowledgeInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action5,
        Field(
            description=(
                '"list" — returns all resources the agent currently has access to. "add" — grants access to a board or'
                ' doc. "update" — changes the permission level on an existing resource. "remove" — revokes the agent\'s'
                " access to a board or doc."
            )
        ),
    ]
    agent_id: Annotated[str, Field(description="Unique identifier of the agent.", min_length=1)]
    resource_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Required for action:add, action:update, action:remove. The ID of the board or doc to"
                " grant/update/revoke access to."
            ),
            min_length=1,
        ),
    ] = None
    scope_type: Annotated[
        Optional[ScopeType],
        Field(
            description='Required for action:add, action:update, action:remove. The type of resource: "BOARD" or "DOC".'
        ),
    ] = None
    permission_type: Annotated[
        Optional[PermissionType],
        Field(
            description=(
                'Required for action:add and action:update. The permission level: "READ" (agent can read the resource)'
                ' or "READ_WRITE" (agent can read and write the resource).'
            )
        ),
    ] = None


class Action6(Enum):
    """
    "list_triggers" — fetch available trigger types with block_reference_id, field_schemas, and required_fields. Call
    before using manage_agent_triggers action:"add". "list_skills" — fetch available skills with id, name,
    description. Call before using manage_agent_skills action:"add".
    """

    LIST_TRIGGERS = "list_triggers"
    LIST_SKILLS = "list_skills"


class AgentCatalogInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action6,
        Field(
            description=(
                '"list_triggers" — fetch available trigger types with block_reference_id, field_schemas, and'
                ' required_fields. Call before using manage_agent_triggers action:"add". "list_skills" — fetch'
                ' available skills with id, name, description. Call before using manage_agent_skills action:"add".'
            )
        ),
    ]
    block_reference_ids: Annotated[
        Optional[list[str]],
        Field(
            description=(
                'Used with action:"list_triggers". Fetch specific trigger types by block_reference_id. Omit to return'
                " all trigger types."
            ),
            min_length=1,
        ),
    ] = None


class ListAutomationsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[str, Field(description="The numeric board ID as a string.", min_length=1)]
    limit: Annotated[
        Optional[int], Field(description="Maximum number of automations to return. Default: 100.", ge=1, le=100)
    ] = None
    cursor: Annotated[
        Optional[str],
        Field(description="Pagination cursor from a previous response. Pass to retrieve the next page of automations."),
    ] = None


class Action7(Enum):
    """
    The operation to perform. activate: enables a paused automation so it responds to its trigger. deactivate: pauses
    an automation without deleting it. delete: permanently removes an automation (irreversible).
    """

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    DELETE = "delete"


class ManageAutomationsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    action: Annotated[
        Action7,
        Field(
            description=(
                "The operation to perform. activate: enables a paused automation so it responds to its trigger."
                " deactivate: pauses an automation without deleting it. delete: permanently removes an automation"
                " (irreversible)."
            )
        ),
    ]
    workflowId: Annotated[
        str, Field(description="The automation ID to operate on. Obtain from list_automations.", min_length=1)
    ]


class CreateAutomationInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    userPrompt: Annotated[str, Field(description="Structured description of the automation to create.", min_length=1)]
    boardId: Annotated[str, Field(description="The numeric board ID as a string.", min_length=1)]


class Mode1(Enum):
    """
    history = paginated run feed, detail = single run by triggerUuid
    """

    HISTORY = "history"
    DETAIL = "detail"


class DateRange1(BaseModel):
    """
    Date range filter
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    startDate: Annotated[str, Field(description='Start date (ISO 8601 or date-only, e.g. "2026-05-01")', min_length=1)]
    endDate: Annotated[str, Field(description="End date (ISO 8601 or date-only)", min_length=1)]


class Filters(BaseModel):
    """
    history: run filters
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    dateRange: Annotated[Optional[DateRange1], Field(description="Date range filter")] = None
    stateFilter: Annotated[
        Optional[list[str]], Field(description='Filter by event state (e.g. ["success", "failure"])')
    ] = None
    automationIds: Annotated[Optional[list[int]], Field(description="Filter by automation IDs")] = None
    workflowEntityIds: Annotated[Optional[list[int]], Field(description="Filter by workflow entity IDs")] = None
    itemId: Annotated[Optional[str], Field(description="Filter by item identifier")] = None
    entityKind: Annotated[Optional[str], Field(description="Filter by entity kind")] = None
    hostType: Annotated[Optional[str], Field(description="Filter by host type")] = None


class GetAutomationRunsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Annotated[Mode1, Field(description="history = paginated run feed, detail = single run by triggerUuid")]
    boardId: Annotated[Optional[str], Field(description="Target a specific board by numeric ID", min_length=1)] = None
    accountWide: Annotated[
        Optional[bool], Field(description="Set true to query account-wide (required if no boardId)")
    ] = None
    nextPageOffset: Annotated[
        Optional[int], Field(description="history: page offset (offset-only pagination)", ge=0)
    ] = None
    filters: Annotated[Optional[Filters], Field(description="history: run filters")] = None
    triggerUuid: Annotated[Optional[str], Field(description="detail: required — the run UUID to inspect")] = None
    includeToolEvents: Annotated[Optional[bool], Field(description="detail: include MCP tool calls (default true)")] = (
        None
    )
    blockEventsOffset: Annotated[Optional[int], Field(description="detail: block-events page offset", ge=0)] = None
    toolEventsOffset: Annotated[Optional[int], Field(description="detail: tool-events page offset", ge=0)] = None


class Breakdown(Enum):
    """
    totals = success/failure/total counts, by_entity = per automation/workflow
    """

    TOTALS = "totals"
    BY_ENTITY = "by_entity"


class RunStatus(Enum):
    """
    by_entity: required run status to break down
    """

    SUCCESS = "success"
    FAILURE = "failure"
    EXHAUSTED = "exhausted"


class GetAutomationStatisticsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    breakdown: Annotated[
        Breakdown, Field(description="totals = success/failure/total counts, by_entity = per automation/workflow")
    ]
    boardId: Annotated[Optional[str], Field(description="Target a specific board by numeric ID", min_length=1)] = None
    accountWide: Annotated[
        Optional[bool], Field(description="Set true to query account-wide (required if no boardId)")
    ] = None
    userIds: Annotated[Optional[list[int]], Field(description="Narrow to specific creator user IDs")] = None
    runStatus: Annotated[Optional[RunStatus], Field(description="by_entity: required run status to break down")] = None
    excludeAutomationIds: Annotated[
        Optional[list[int]], Field(description="by_entity: automation IDs to exclude from breakdown")
    ] = None


class PrivacyKind(Enum):
    """
    Workflow visibility: PUBLIC (default), PRIVATE, or SHAREABLE (accessible to guests outside the account).
    """

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    SHAREABLE = "SHAREABLE"


class CreateWorkflowInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workspaceId: Annotated[str, Field(description="The ID of the workspace to create the workflow in.", min_length=1)]
    title: Annotated[
        Optional[str], Field(description='Workflow title. Defaults to "New Workflow" if not provided.')
    ] = None
    privacyKind: Annotated[
        Optional[PrivacyKind],
        Field(
            description=(
                "Workflow visibility: PUBLIC (default), PRIVATE, or SHAREABLE (accessible to guests outside the"
                " account)."
            )
        ),
    ] = None
    description: Annotated[Optional[str], Field(description="Optional workflow description.")] = None
    folderId: Annotated[Optional[str], Field(description="Optional folder ID to place the workflow in.")] = None
    ownerIds: Annotated[
        Optional[list[str]], Field(description="Optional list of user IDs to set as workflow owners.")
    ] = None


class UpdateWorkflowInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workflowObjectId: Annotated[
        float,
        Field(
            description=(
                "The workflow object ID returned by create_workflow. Identifies the workflow across all its drafts and"
                " published versions. Does not change across publishes."
            )
        ),
    ]
    workflowDraftId: Annotated[
        float,
        Field(
            description=(
                "The draft version ID to update. Use the workflowDraftId from the previous create_workflow or"
                " update_workflow response — the agent may return a new draft ID, so always read it from the latest"
                " response rather than reusing an earlier value."
            )
        ),
    ]
    prompt: Annotated[
        str,
        Field(
            description=(
                "Natural-language description of the changes to make. Describe what steps to add, remove, or modify in"
                ' plain English (e.g. "Add a trigger that fires when an item is created on the Marketing board"). The'
                " agent interprets this and applies the right structural changes. Maximum 2000 characters."
            ),
            max_length=2000,
            min_length=1,
        ),
    ]


class PlanWorkflowInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prompt: Annotated[
        str,
        Field(
            description=(
                "Natural-language description of the process to plan. Describe the full end-to-end process in plain"
                ' English (e.g. "When a deal is marked Won, create a task in the onboarding board and notify the'
                ' account manager"). The agent will decompose this into one or more monday.com workflows, identify all'
                " required boards and columns, and return a structured implementation plan. Maximum 2000 characters."
            ),
            max_length=2000,
            min_length=1,
        ),
    ]


class PublishWorkflowInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workflowObjectId: Annotated[
        str,
        Field(
            description=(
                "The workflow object ID returned by create_workflow. Identifies the workflow across all its drafts and"
                " live versions."
            ),
            min_length=1,
        ),
    ]
    workflowDraftId: Annotated[
        str,
        Field(
            description=(
                "The draft version ID returned by create_workflow. Both workflowObjectId and workflowDraftId are"
                " required — together they identify the exact draft to publish."
            ),
            min_length=1,
        ),
    ]
    shouldActivate: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to activate the workflow immediately after publishing so it starts running. Defaults to true —"
                " the workflow is activated immediately after publish."
            )
        ),
    ] = None


class GetMondayDevSprintsBoardsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class GetSprintsMetadataInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sprintsBoardId: Annotated[float, Field(description="The ID of the monday-dev board containing the sprints")]
    limit: Annotated[
        Optional[float],
        Field(description="The number of sprints to retrieve (default: 25, max: 100)", ge=1.0, le=100.0),
    ] = 25


class GetSprintSummaryInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sprintId: Annotated[float, Field(description='The ID of the sprint to get the summary for (e.g., "9123456789")')]


class Datum(BaseModel):
    """
    A single data point representing a named value. MUST include both name and y properties. Optionally include color
    property. Used for all chart types.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str,
        Field(
            description="The name/label of the data point. Displayed in legend for pie charts, on axis for bar charts."
        ),
    ]
    y: Annotated[float, Field(description="The numeric value of the data point.")]
    color: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional color for the data point. Accepts any valid CSS color value (hex, rgb, color name). If not"
                " provided, chart will use default color scheme."
            )
        ),
    ] = None


class Type6(Enum):
    """
    Chart type to render: "pie" (circular chart with segments) or "bar" (horizontal bars).
    """

    PIE = "pie"
    BAR = "bar"


class ShowChartInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    data: Annotated[
        list[Datum],
        Field(
            description=(
                "Array of data points. Each point must have 'name' (label) and 'y' (value) properties, with optional"
                " 'color' property."
            ),
            min_length=1,
        ),
    ]
    type: Annotated[
        Type6,
        Field(description='Chart type to render: "pie" (circular chart with segments) or "bar" (horizontal bars).'),
    ]
    title: Annotated[
        Optional[str],
        Field(description="Optional title text to display above the chart. Leave empty or omit for no title."),
    ] = None


class Operator13(Enum):
    """
    The operator to use for the filter
    """

    ANY_OF = "any_of"
    NOT_ANY_OF = "not_any_of"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUALS = "greater_than_or_equals"
    LOWER_THAN = "lower_than"
    LOWER_THAN_OR_EQUAL = "lower_than_or_equal"
    BETWEEN = "between"
    CONTAINS_TEXT = "contains_text"
    NOT_CONTAINS_TEXT = "not_contains_text"
    CONTAINS_TERMS = "contains_terms"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    WITHIN_THE_NEXT = "within_the_next"
    WITHIN_THE_LAST = "within_the_last"


class Filter6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columnId: Annotated[str, Field(description="The id of the column to filter by")]
    compareAttribute: Annotated[
        Optional[str], Field(description="The attribute to compare the value to. This is OPTIONAL property.")
    ] = None
    compareValue: Annotated[
        Union[str, float, bool, list[Union[str, float]]],
        Field(
            description=(
                "The value to compare the attribute to. This can be a string or index value depending on the column"
                " type."
            )
        ),
    ]
    operator: Annotated[Optional[Operator13], Field(description="The operator to use for the filter")] = (
        Operator13.ANY_OF
    )


class ShowTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[str, Field(description="The ID of the board to display")]
    currentlySelectedItemIdForShowingUpdates: Annotated[
        Optional[str], Field(description="The ID of the item currently displaying its updates in the expanded view")
    ] = None
    filters: Annotated[
        Optional[list[Filter6]],
        Field(
            description=(
                "The configuration of filters to apply on the items. Before sending the filters, use get_board_info"
                ' tool to check "filteringGuidelines" key for filtering by the column.'
            )
        ),
    ] = None
    filtersOperator: Annotated[Optional[FiltersOperator], Field(description="The operator to use for the filters")] = (
        FiltersOperator.AND
    )


class User(BaseModel):
    """
    Assigned user
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        str,
        Field(
            description=(
                "User ID - MUST be a valid, non-empty ID from an actual user in the system. Do NOT use empty strings or"
                " placeholder values."
            ),
            min_length=1,
        ),
    ]
    name: Annotated[
        str,
        Field(
            description=(
                "User name - MUST be the real name of an actual user in the system. Do NOT use empty strings,"
                " placeholder values, or made-up names."
            ),
            min_length=1,
        ),
    ]
    avatarUrl: Annotated[
        Optional[str], Field(description="The user photo (photo_tiny or Photo thumb from the user object)")
    ] = None
    jobTitle: Annotated[Optional[str], Field(description="Job title (title from the user object)")] = None


class Assignment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    itemId: Annotated[str, Field(description="Item ID", min_length=1)]
    itemName: Annotated[str, Field(description="Item name", min_length=1)]
    user: Annotated[User, Field(description="Assigned user")]


class ShowAssignInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title: Annotated[str, Field(description="Board title")]
    assignments: Annotated[list[Assignment], Field(description="Array of item assignments")]


class Datum1(BaseModel):
    """
    A single segment representing a named value. MUST include name, y, and color properties. Used for battery visualization.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str,
        Field(description='The name/label of the segment. Displayed in the legend (e.g., "Done", "In Progress", etc.)'),
    ]
    y: Annotated[float, Field(description="The numeric value of the segment.", ge=0.0)]
    color: Annotated[
        str,
        Field(
            description=(
                "Color for the segment. Accepts any valid CSS color value (hex, rgb, color name). Required for battery"
                " segments."
            )
        ),
    ]


class ShowBatteryInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    data: Annotated[
        list[Datum1],
        Field(
            description=(
                "Array of segments. Each segment must have 'name' (label), 'y' (value), and 'color' properties."
            ),
            min_length=1,
        ),
    ]


class Items(RootModel[Any]):
    root: Any


class Field0(RootModel[Any]):
    root: Any


class Field1(RootModel[Any]):
    root: Any


class Field2(RootModel[Any]):
    root: Any


class Field3(RootModel[Any]):
    root: Any


class Field4(RootModel[Any]):
    root: Any


class Field5(RootModel[Any]):
    root: Any


class Field6(RootModel[Any]):
    root: Any


class Field7(RootModel[Any]):
    root: Any


class Field8(RootModel[Any]):
    root: Any


class Field9(RootModel[Any]):
    root: Any


class Answer(BaseModel):
    """
    An answer for a single form question. Set question_id and exactly one answer field matching the question type.
    Subitems questions are not supported.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    question_id: Annotated[str, Field(description="The ID of the question being answered.")]
    name: Annotated[Optional[str], Field(description="Answer for name questions.")] = None
    email: Annotated[Optional[str], Field(description="Answer for email questions.")] = None
    short_text: Annotated[Optional[str], Field(description="Answer for short text questions.")] = None
    long_text: Annotated[Optional[str], Field(description="Answer for long text questions.")] = None
    link: Annotated[Optional[str], Field(description="Answer for link questions.")] = None
    updates: Annotated[Optional[str], Field(description="Answer for updates questions.")] = None
    boolean: Annotated[Optional[bool], Field(description="Answer for boolean questions.")] = None
    number: Annotated[Optional[float], Field(description="Answer for number questions.")] = None
    rating: Annotated[
        Optional[float],
        Field(
            description=(
                "Answer for rating questions. Must be a positive number within the question's configured limit."
            ),
            ge=1.0,
        ),
    ] = None
    single_select: Annotated[
        Optional[str], Field(description="Answer for single-select questions — the selected option ID.")
    ] = None
    multi_select: Annotated[
        Optional[list[float]], Field(description="Answer for multi-select questions — list of selected option IDs.")
    ] = None
    people: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Answer for people questions — list of user IDs. Obtain user IDs via the list_users_and_teams tool."
            )
        ),
    ] = None
    connected_boards: Annotated[
        Optional[list[str]], Field(description="Answer for connected boards questions — list of connected item IDs.")
    ] = None
    phone: Annotated[Optional[Phone], Field(description="Answer for phone questions.")] = None
    country: Annotated[Optional[Country], Field(description="Answer for country questions.")] = None
    date: Annotated[Optional[Date], Field(description="Answer for date questions.")] = None
    date_range: Annotated[Optional[DateRange], Field(description="Answer for date range questions.")] = None
    location: Annotated[
        Optional[Location],
        Field(
            description=(
                "Answer for location questions. Requires a Google Maps place ID and structured address components."
            )
        ),
    ] = None
    file: Annotated[
        Optional[list[FileItem]],
        Field(
            description=(
                "Answer for file questions. Each file must be uploaded first to obtain a file ID. Up to the question's"
                " configured limit."
            )
        ),
    ] = None
    signature: Annotated[
        Optional[Items],
        Field(description="Answer for signature questions. The file must be uploaded first to obtain a file ID."),
    ] = None


class CreateFormSubmissionInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    form_token: Annotated[
        str,
        Field(
            description=(
                "The unique token identifying the WorkForm. Can be a bare token, a full WorkForm URL (e.g."
                " https://forms.monday.com/forms/abc123?r=use1), or a shortened wkf.ms URL (e.g."
                " https://wkf.ms/4tqP28t). Shortened URLs are automatically resolved by following the redirect."
            )
        ),
    ]
    answers: Annotated[
        list[Answer],
        Field(
            description=(
                "Array of answers to submit. Each answer specifies a question_id and the value for that question type."
            )
        ),
    ]
    form_timezone_offset: Annotated[
        int,
        Field(
            description="The timezone offset of the submitter in minutes (e.g. -120 for UTC-2, 0 for UTC).",
            ge=-840,
            le=840,
        ),
    ]
    password: Annotated[
        Optional[str],
        Field(
            description=(
                "The password for the WorkForm. Only required if the WorkForm has password protection enabled (check"
                " features.password.enabled from get_form). If required, ask the user for the password before"
                " submitting."
            )
        ),
    ] = None
    tags: Annotated[
        Optional[list[Tag1]],
        Field(description="Tags to attach to the submission — each tag maps a value to a specific board column."),
    ] = None


class Content1(BaseModel):
    """
    New content for the block. Use block_content_type to select: text (updates text/heading/quote content),
    code (updates code content), list_item (updates bullets/numbered/todo content). Cannot change block subtype — use
    replace_block for that.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_content_type: Literal["code"]
    delta_format: Annotated[
        list[Items],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    language: Annotated[Optional[str], Field(description='Programming language (e.g. "javascript", "python").')] = None


class Content2(BaseModel):
    """
    New content for the block. Use block_content_type to select: text (updates text/heading/quote content),
    code (updates code content), list_item (updates bullets/numbered/todo content). Cannot change block subtype — use
    replace_block for that.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_content_type: Literal["list_item"]
    delta_format: Annotated[
        list[Items],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    checked: Annotated[Optional[bool], Field(description="Check state for CHECK_LIST items.")] = None
    indentation: Annotated[Optional[int], Field(description="Nesting level (0 = no indent).", ge=0)] = None


class Operations2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["update_block"]
    block_id: Annotated[str, Field(description="ID of the block to update. Get block IDs from read_docs.")]
    content: Annotated[
        Union[Content, Content1, Content2],
        Field(
            description=(
                "New content for the block. Use block_content_type to select: text (updates text/heading/quote"
                " content), code (updates code content), list_item (updates bullets/numbered/todo content). Cannot"
                " change block subtype — use replace_block for that."
            )
        ),
    ]


class Block(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["text"]
    text_block_type: Annotated[
        Optional[TextBlockType], Field(description="Block subtype. LARGE_TITLE=H1, MEDIUM_TITLE=H2, SMALL_TITLE=H3.")
    ] = None
    delta_format: Annotated[
        list[Items],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    alignment: Optional[Alignment1] = None
    direction: Optional[Direction2] = None


class Block1(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["list_item"]
    list_block_type: Annotated[Optional[ListBlockType], Field(description="List type. Defaults to BULLETED_LIST.")] = (
        None
    )
    delta_format: Annotated[
        list[Items],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    indentation: Annotated[Optional[int], Field(description="Nesting level (0 = no indent).", ge=0)] = None


class Block2(BaseModel):
    """
    The block to create. Use block_type to select the block type.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    block_type: Literal["code"]
    delta_format: Annotated[
        list[Items],
        Field(description='Array of delta operations. Last op must be {insert: {text: "\\n"}}.', min_length=1),
    ]
    language: Annotated[Optional[str], Field(description='Programming language (e.g. "javascript", "python").')] = None


class Operations3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["create_block"]
    after_block_id: Annotated[
        Optional[str],
        Field(description="Insert after this block ID. Omit to append at end. Block IDs come from read_docs."),
    ] = None
    parent_block_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Parent block ID for nested blocks. Only works for notice_box containers — use the notice_box block ID"
                " directly. Table/layout cell nesting is NOT supported by the API. IMPORTANT: A notice_box created in"
                " the same call cannot be referenced — use a separate call first to create it, then a second call to"
                " nest content inside it."
            )
        ),
    ] = None
    block: Annotated[
        Union[Block, Block1, Block2, Block3, Block4, Block5, Block6, Block7, Block8, Block9],
        Field(description="The block to create. Use block_type to select the block type."),
    ]


class Operations5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation_type: Literal["replace_block"]
    block_id: Annotated[str, Field(description="ID of the block to delete.")]
    after_block_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Insert replacement after this block ID. Provide the ID of the block that precedes the deleted block."
            )
        ),
    ] = None
    parent_block_id: Annotated[Optional[str], Field(description="Parent block ID for the replacement block.")] = None
    block: Annotated[
        Union[Field0, Field1, Field2, Field3, Field4, Field5, Field6, Field7, Field8, Field9],
        Field(description="The new block to create in place of the deleted one."),
    ]


class UpdateDocInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    doc_id: Annotated[
        Optional[str],
        Field(
            description=(
                "The document ID (the id field from read_docs). Takes priority over object_id if both are provided."
            ),
            min_length=1,
        ),
    ] = None
    object_id: Annotated[
        Optional[str],
        Field(
            description=(
                "The document object ID (the object_id field from read_docs, visible in the document URL). Resolved to"
                " doc_id."
            ),
            min_length=1,
        ),
    ] = None
    operations: Annotated[
        list[Union[Operations, Operations1, Operations2, Operations3, Operations4, Operations5, Operations6]],
        Field(
            description=(
                "Ordered list of operations to perform. Executed sequentially. Stops at first failure.\n\nOperation"
                " types:\n- set_name: Rename the document.\n- add_markdown_content: Append markdown as blocks (simplest"
                " for text/lists/tables).\n- update_block: Change content of an existing text/code/list/divider"
                " block.\n- create_block: Create a new block at a specific position (supports text, list_item, code,"
                " divider, page_break, image, video, notice_box, table, layout).\n- delete_block: Permanently remove a"
                " block. Works for ALL block types including BOARD, WIDGET, DOC embed, GIPHY.\n- replace_block: Delete"
                " a block and create a new one in its place. Use for: changing image/video source, table restructure,"
                " notice_box theme change.\n- add_comment: Create a new comment or reply on the document. Use"
                " parent_update_id to reply to an existing comment. Format text with HTML. Uses the doc's backing"
                " board item.\n\nWHEN TO USE WHICH:\n- Adding new text sections → add_markdown_content\n- Adding"
                ' asset-based images → create_block with block_type "image" and asset_id (add_markdown_content does NOT'
                " support asset images)\n- Mixed content with asset images → alternate add_markdown_content (for text)"
                " and create_block (for each image) in sequence\n- Editing existing text block → update_block\n-"
                " Changing an image URL → replace_block (image URL is immutable after creation)\n- Changing video URL →"
                " replace_block\n- Restructuring a table → replace_block\n- BOARD/WIDGET/DOC/GIPHY blocks →"
                " delete_block only (no public API to create these)\n\nNESTING CONTENT IN CONTAINERS:\n- notice_box:"
                " Fully supported. Create the notice_box first, then in a separate call create child blocks with"
                " parent_block_id set to the notice_box ID. You cannot reference a block ID created in the same"
                " call.\n- table: Cell-level API nesting is NOT supported. To create a table with content, use"
                ' add_markdown_content with a markdown table (e.g. "| H1 | H2 |\\n| --- | --- |\\n| A | B |"). This'
                " creates a pre-populated table in one shot. Empty tables created via create_block cannot have their"
                " cells populated through the API.\n- layout: Cell-level API nesting is NOT supported and there is no"
                " markdown equivalent. Layouts can only be created empty via create_block. No workaround exists to"
                " populate layout columns through the API.\nDeleting a container does NOT delete its children — delete"
                " children first for clean removal.\n\nBlock IDs are available in the blocks array returned by"
                " read_docs."
            ),
            max_length=25,
            min_length=1,
        ),
    ]


class Columns(BaseModel):
    """
    Column visibility and order configuration
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    column_properties: Annotated[
        Optional[list[ColumnProperty]], Field(description="Visibility configuration for main board columns")
    ] = None
    subitems_column_properties: Annotated[
        Optional[list[Items]], Field(description="Visibility configuration for subitem columns")
    ] = None
    floating_columns_count: Annotated[Optional[int], Field(description="Number of floating columns to display")] = None
    column_order: Annotated[Optional[list[str]], Field(description="Ordered list of column IDs")] = None


class Settings1(BaseModel):
    """
    Table-specific view settings (column visibility/order, group-by)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    columns: Annotated[Optional[Columns], Field(description="Column visibility and order configuration")] = None
    group_by: Annotated[Optional[GroupBy], Field(description="Group-by configuration for the table view")] = None


class CreateViewTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    boardId: Annotated[str, Field(description="The board ID to create the table view on")]
    name: Annotated[
        Optional[str], Field(description='The name of the view (e.g. "High Priority Items", "My Tasks")')
    ] = None
    filter: Annotated[Optional[Filter4], Field(description="Filter configuration for the view")] = None
    sort: Annotated[Optional[list[SortItem2]], Field(description="Sort configuration for the view")] = None
    tags: Annotated[Optional[list[str]], Field(description="Tags to apply to the view")] = None
    settings: Annotated[
        Optional[Settings1], Field(description="Table-specific view settings (column visibility/order, group-by)")
    ] = None


class Columns1(BaseModel):
    """
    Column visibility and order configuration
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    column_properties: Annotated[
        Optional[list[ColumnProperty]], Field(description="Visibility configuration for main board columns")
    ] = None
    subitems_column_properties: Annotated[
        Optional[list[Items]], Field(description="Visibility configuration for subitem columns")
    ] = None
    floating_columns_count: Annotated[Optional[int], Field(description="Number of floating columns to display")] = None
    column_order: Annotated[Optional[list[str]], Field(description="Ordered list of column IDs")] = None


class Settings2(BaseModel):
    """
    Table-specific view settings (column visibility/order, group-by)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    columns: Annotated[Optional[Columns1], Field(description="Column visibility and order configuration")] = None
    group_by: Annotated[Optional[GroupBy1], Field(description="Group-by configuration for the table view")] = None


class UpdateViewTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    viewId: Annotated[str, Field(description="The ID of the table view to update")]
    boardId: Annotated[str, Field(description="The board ID the view belongs to")]
    name: Annotated[Optional[str], Field(description="New name for the view (omit to leave unchanged)")] = None
    filter: Annotated[Optional[Filter5], Field(description="Filter configuration to apply to the view")] = None
    sort: Annotated[Optional[list[SortItem3]], Field(description="Sort configuration for the view")] = None
    tags: Annotated[Optional[list[str]], Field(description="Tags to apply to the view")] = None
    settings: Annotated[
        Optional[Settings2], Field(description="Table-specific view settings (column visibility/order, group-by)")
    ] = None
