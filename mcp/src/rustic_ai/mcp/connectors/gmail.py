"""
Auto-generated Pydantic models for gmail's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://gmailmcp.googleapis.com/mcp/v1"
   },
   "tools": [
     {
       "name": "create_draft",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.CreateDraftInput",
       "description": "Creates a new draft email in the authenticated user's Gmail account.\n\nThis tool takes recipient addresses, a subject, and body content as inputs. It returns the ID of the created Gmail draft. If the draft is created as a reply to an existing message, the ID of the original message should be passed to the tool in the replyToMessageId field. Creating drafts with attachments is not supported yet.\n"
     },
     {
       "name": "list_drafts",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.ListDraftsInput",
       "description": "Lists draft emails from the authenticated user's Gmail account.\n\nThis tool can filter drafts based on a query string and supports pagination. It returns a list of drafts, including their IDs and subjects. `page_token` can be used to paginate the results. To retrieve subsequent pages of results, use the `page_token` returned in the previous response. \n"
     },
     {
       "name": "get_thread",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.GetThreadInput",
       "description": "Retrieves a specific email thread from the authenticated user's Gmail account, including a list of its messages.\n"
     },
     {
       "name": "search_threads",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.SearchThreadsInput",
       "description": "Lists email threads from the authenticated user's Gmail account.\n\nThis tool can filter threads based on a query string and supports pagination. It returns a list of threads, including their IDs and related messages. Each related message contains details like a snippet of the message body, the subject, the sender, the recipients etc. Note that the full message bodies are not returned by this tool; use the 'get_thread' tool with a thread ID to fetch the full message body if needed. Threads with excluded criteria may still appear in the results. This occurs because Gmail identifies matching messages first. For example, if you search for -is:starred, Gmail will find an entire thread if it contains at least one unstarred message, even if other emails in that same conversation are starred.\n"
     },
     {
       "name": "label_thread",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.LabelThreadInput",
       "description": "Adds labels to an entire thread in the authenticated user's Gmail account. This operation affects all messages currently in the thread and any future messages added to it.\n\nIf unsure of the thread ID, use the `search_threads` tool first.\n\nIf unsure of a user label's ID, use the `list_labels` tool first to discover available labels and their IDs.\n"
     },
     {
       "name": "unlabel_thread",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.UnlabelThreadInput",
       "description": "Removes labels from an entire thread in the authenticated user's Gmail account. If unsure of the thread ID, use the `search_threads` tool first. If unsure of a user label's ID, use the `list_labels` tool first."
     },
     {
       "name": "list_labels",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.ListLabelsInput",
       "description": "Lists all user-defined labels available in the authenticated user's Gmail account. Use this tool to discover the `id` of a user label before calling `label_thread`, `unlabel_thread`, `label_message`, or `unlabel_message`. System labels are not returned by this tool but can be used with their well-known IDs: 'INBOX', 'TRASH', 'SPAM', 'STARRED', 'UNREAD', 'IMPORTANT', 'CHAT', 'DRAFT', 'SENT'."
     },
     {
       "name": "label_message",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.LabelMessageInput",
       "description": "Adds one or more labels to a specific message in the authenticated user's Gmail account.\n\nTo find the message ID, use tools like `search_threads` or `get_thread`. If unsure of a user label's ID, use the `list_labels` tool first to discover available labels and their IDs.\n"
     },
     {
       "name": "unlabel_message",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.UnlabelMessageInput",
       "description": "Removes one or more labels from a specific message in the authenticated user's Gmail account. To find the message ID, use tools like `search_threads` or `get_thread`. If unsure of a user label's ID, use the `list_labels` tool first to discover available labels and their IDs."
     },
     {
       "name": "create_label",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.CreateLabelInput",
       "description": "Creates a new label in the authenticated user's Gmail account.\nSupports creating nested labels (sub-labels) using a forward slash (e.g., 'Projects/Alpha/Sprint-1').\nBy default, parent labels will be automatically created if they do not exist.\n"
     },
     {
       "name": "update_label",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.UpdateLabelInput",
       "description": "Modifies an existing label's name and color in the user's Gmail account.\n"
     },
     {
       "name": "delete_label",
       "input_class_name": "rustic_ai.mcp.connectors.gmail.DeleteLabelInput",
       "description": "Deletes a label in the authenticated user's Gmail account."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, RootModel


class ListDraftsInput(BaseModel):
    """
    Request message for ListDrafts RPC.
    """

    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. The maximum number of drafts to return. If unspecified, defaults to 20. The maximum allowed"
                " value is 50."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. A token received from a previous list_drafts call to retrieve the next page of results."
                " Leave empty to fetch the first page. This is primarily used for pagination to continue fetching"
                " results from where the previous `ListDraft` call left off, especially when the number of drafts"
                " matching the query exceeds the page_size limit."
            )
        ),
    ] = None
    query: Annotated[
        Optional[str],
        Field(
            description=(
                'Examples: "subject:OneMCP Update" "from:gduser1@workspacesamples.dev" "to:gduser2@workspacesamples.dev'
                ' AND newer_than:7d" "project proposal has:attachment" "is:unread" A space or a dash (`-`) will'
                " separate a number while a dot (`.`) will be a decimal. For example, `01.2047-100` is considered two"
                " numbers: `01.2047` and `100`. Note: If we want to ensure all drafts for the query are returned, we"
                " can paginate the results by making repeated calls to the tool until the response contains an empty"
                " list of drafts."
            )
        ),
    ] = None


class MessageFormat(Enum):
    """
    Optional. Specifies the format of the messages returned within the thread. Defaults to FULL_CONTENT. Note: If you
    need body content or attachments, use FULL_CONTENT. When using MINIMAL, the plaintext_body and attachment_ids
    fields will not be populated. If you are unsure which format to use, rely on the default behavior by using
    FULL_CONTENT.
    """

    MESSAGE_FORMAT_UNSPECIFIED = "MESSAGE_FORMAT_UNSPECIFIED"
    MINIMAL = "MINIMAL"
    FULL_CONTENT = "FULL_CONTENT"


class GetThreadInput(BaseModel):
    """
    Request message for GetThread RPC.
    """

    messageFormat: Annotated[
        Optional[MessageFormat],
        Field(
            description=(
                "Optional. Specifies the format of the messages returned within the thread. Defaults to FULL_CONTENT."
                " Note: If you need body content or attachments, use FULL_CONTENT. When using MINIMAL, the"
                " plaintext_body and attachment_ids fields will not be populated. If you are unsure which format to"
                " use, rely on the default behavior by using FULL_CONTENT."
            )
        ),
    ] = None
    threadId: Annotated[Optional[str], Field(description="Required. The unique identifier of the thread to fetch.")] = (
        None
    )


class SearchThreadsInput(BaseModel):
    """
    Request message for SearchThreads RPC.
    """

    includeTrash: Annotated[
        Optional[bool], Field(description="Optional. Include drafts from TRASH in the results. Defaults to false.")
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. The maximum number of threads to return. If unspecified, defaults to 20. The maximum allowed"
                " value is 50."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Page token to retrieve a specific page of results in the list. Leave empty to fetch the"
                " first page. This is primarily used for pagination to continue fetching results from where the"
                " previous `SearchThreads` call left off, especially when the number of threads matching the query"
                " exceeds the page_size limit."
            )
        ),
    ] = None
    query: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. A query string to filter the threads. Natural language queries must be pre-converted into"
                " Gmail syntax queries to use this tool. If omitted, all threads (excluding spam and trash by default)"
                " are listed. Supported Operators by Category: Sender & Recipient: from: - Sent from a specific person."
                " to: - Sent to a specific person. cc: - Specific people in Cc. bcc: - Specific people in Bcc."
                " deliveredto: - Delivered to a specific address. list: - From a specific mailing list. Time & Date:"
                " after:YYYY/MM/DD / newer:YYYY/MM/DD - Received after a date. before:YYYY/MM/DD / older:YYYY/MM/DD -"
                " Received before a date. older_than: - Older than a duration (e.g., 1y, 2d). newer_than: - Newer than"
                " a duration. Content: subject: - Words in the subject line. has: - Has specific content types"
                ' (attachment, drive, youtube, document). filename: - Attachment with a specific name or type. "" -'
                ' Search for an exact word or phrase. (e.g., "holiday", "holiday vacation"). + - Match a word exactly.'
                " (e.g., +holiday, +unicorn) rfc822msgid: - Specific message ID header. AROUND - Find words near each"
                " other (e.g., holiday AROUND 10 vacation). Labels & Categories: label: - Under a specific label. The"
                " tool accepts label IDs, not display names. Use the list_labels tool to get the ID. category: - In a"
                " category (primary, social, promotions, updates, forums, reservations, purchases). in: - Search in"
                " specific labels (archive, snoozed, trash, sent, inbox). E.g., `in:trash`, `in:inbox`. Archived and"
                " sent messages are included by default; use `-in:archive` and `-in:sent` to exclude them. Drafts are"
                " explicitly excluded by default by the tool. Use `in:inbox` to restrict search to the inbox only."
                " has:userlabels - Has any user labels. has:nouserlabels - Does not have any user labels. has:*-star -"
                " Specific star colors (if enabled, e.g., has:yellow-star). in:draft - Search in drafts. -in:draft"
                " means exclude drafts from the search results. in:sent - Search in sent messages. in:anywhere - Search"
                " in all folders (including spam and trash). Status: is: - Search by status (important, starred,"
                " unread, read, muted). Size: size: - Specific size in bytes. larger: / smaller: - Larger or smaller"
                " than a size (e.g., 10M for 10 MB). Logic & Grouping: AND - Match all criteria (default behavior). OR"
                " or { } - Match one or more criteria (e.g., from:amy OR from:david, {from:amy from:david}). - (minus)"
                " - Exclude criteria (e.g., -movie). ( ) - Group multiple search terms (e.g., subject:(dinner film))."
                ' Examples: "subject:OneMCP Update" "from:user@example.com" "to:user2@example.com AND newer_than:7d"'
                ' "project proposal has:attachment" "is:unread -in:draft"'
            )
        ),
    ] = None


class LabelThreadInput(BaseModel):
    """
    Request message for LabelThread RPC.
    """

    labelIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Required. The unique identifiers of the labels to add. Can be a system label ID (e.g., 'INBOX',"
                " 'TRASH', 'SPAM', 'STARRED', 'UNREAD', 'IMPORTANT') or a user-defined label ID. The tool accepts"
                " `label_ids` and not label names. Use the list_labels tool to get the corresponding label id to a"
                " display name for user-defined labels."
            )
        ),
    ] = None
    threadId: Annotated[
        Optional[str], Field(description="Required. The unique identifier of the thread to add labels to.")
    ] = None


class UnlabelThreadInput(BaseModel):
    """
    Request message for UnlabelThread RPC.
    """

    labelIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Required. The unique identifiers of the labels to remove. Can be a system label ID (e.g., 'INBOX',"
                " 'TRASH', 'SPAM', 'STARRED', 'UNREAD', 'IMPORTANT') or a user-defined label ID. The tool accepts"
                " `label_ids` and not label names. Use the list_labels tool to get the corresponding label id to a"
                " display name for user-defined labels."
            )
        ),
    ] = None
    threadId: Annotated[
        Optional[str], Field(description="Required. The unique identifier of the thread to remove labels from.")
    ] = None


class ListLabelsInput(BaseModel):
    """
    Request message for ListLabels RPC.
    """

    pageSize: Annotated[Optional[int], Field(description="Optional. The maximum number of labels to return.")] = None
    pageToken: Annotated[
        Optional[str], Field(description="Optional. Page token to retrieve a specific page of results in the list.")
    ] = None


class LabelMessageInput(BaseModel):
    """
    Request message for LabelMessage RPC.
    """

    labelIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Required. The IDs of the labels to add. Can be a system label ID (e.g., 'INBOX', 'TRASH', 'SPAM',"
                " 'STARRED', 'UNREAD', 'IMPORTANT') or a user-defined label ID. The tool accepts `label_ids` and not"
                " label names. Use the list_labels tool to get the corresponding label id to a display name for"
                " user-defined labels."
            )
        ),
    ] = None
    messageId: Annotated[Optional[str], Field(description="Required. The ID of the message to add the labels to.")] = (
        None
    )


class UnlabelMessageInput(BaseModel):
    """
    Request message for UnlabelMessage RPC.
    """

    labelIds: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Required. The IDs of the labels to remove. Can be a system label ID (e.g., 'INBOX', 'TRASH', 'SPAM',"
                " 'STARRED', 'UNREAD', 'IMPORTANT') or a user-defined label ID. The tool accepts `label_ids` and not"
                " label names. Use the list_labels tool to get the corresponding label id to a display name for"
                " user-defined labels."
            )
        ),
    ] = None
    messageId: Annotated[
        Optional[str], Field(description="Required. The ID of the message to remove the labels from.")
    ] = None


class DeleteLabelInput(BaseModel):
    """
    Request message for DeleteLabel RPC.
    """

    labelId: Annotated[Optional[str], Field(description="Required. The ID of the label to delete.")] = None


class Attachment(RootModel[Any]):
    root: Any


class LabelColor(RootModel[Any]):
    root: Any


class CreateDraftInput(BaseModel):
    """
    Request message for CreateDraft RPC.
    """

    attachments: Annotated[
        Optional[list[Attachment]],
        Field(
            description=(
                "Optional. The attachments to include in the email. The combined size of attachments in the message"
                " cannot exceed 25MB. If you need to send files larger than 25MB, upload the file to Drive first and"
                " then insert the Drive link into body or html_body."
            )
        ),
    ] = None
    bcc: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Optional. The blind carbon copy recipients of the email draft. Each string MUST be a valid plain email"
                ' address (e.g., "user@example.com"). The "Name " format is NOT supported by this tool.'
            )
        ),
    ] = None
    body: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The main body content of the email draft. If html_body is also provided, this field is"
                " treated as the plain-text alternative."
            )
        ),
    ] = None
    cc: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Optional. The carbon copy recipients of the email draft. Each string MUST be a valid plain email"
                ' address (e.g., "user@example.com"). The "Name " format is NOT supported by this tool.'
            )
        ),
    ] = None
    htmlBody: Annotated[
        Optional[str],
        Field(
            description=(
                "The HTML content of the email draft. If provided, this will be used as the rich-text version of the"
                " email."
            )
        ),
    ] = None
    replyToMessageId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The ID of the message to reply to. If provided, this will be used as the reply-to message ID"
                " for the email draft, and the `body` and `html_body` will be appended to the original message body."
            )
        ),
    ] = None
    subject: Annotated[
        Optional[str], Field(description="Optional. The subject line of the email. Defaults to empty if not provided.")
    ] = None
    to: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Required. The primary recipients of the email draft. Each string MUST be a valid plain email address"
                ' (e.g., "user@example.com"). The "Name " format is NOT supported by this tool.'
            )
        ),
    ] = None


class CreateLabelInput(BaseModel):
    """
    Request message for CreateLabel RPC.
    """

    autoCreateParentLabels: Annotated[
        Optional[bool],
        Field(
            description=(
                "Optional. Whether to automatically create parent labels for nested labels (separated by '/'). Defaults"
                " to true."
            )
        ),
    ] = None
    color: Annotated[Optional[LabelColor], Field(description="Optional. The color of the label.")] = None
    displayName: Annotated[Optional[str], Field(description="Required. The display name of the label to create.")] = (
        None
    )


class UpdateLabelInput(BaseModel):
    """
    Request message for UpdateLabel RPC.
    """

    color: Annotated[Optional[LabelColor], Field(description="Optional. The color of the label.")] = None
    displayName: Annotated[
        Optional[str], Field(description="Optional. The human-readable display name of the label.")
    ] = None
    labelId: Annotated[Optional[str], Field(description="Required. The unique identifier of the label to modify.")] = (
        None
    )
