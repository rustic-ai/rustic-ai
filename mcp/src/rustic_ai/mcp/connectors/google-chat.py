"""
Auto-generated Pydantic models for google-chat's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://chatmcp.googleapis.com/mcp/v1"
   },
   "tools": [
     {
       "name": "list_messages",
       "input_class_name": "rustic_ai.mcp.connectors.google-chat.ListMessagesInput",
       "description": "Retrieves messages from a specified Google Chat conversation (Space, direct message (DM) or group DM). Allows filtering by thread, time range, and number of messages. Additionally, the next page of messages can be retrieved to allow for more context. Private messages (messages only visible to a single user) are filtered out.\n"
     },
     {
       "name": "search_messages",
       "input_class_name": "rustic_ai.mcp.connectors.google-chat.SearchMessagesInput",
       "description": "Searches for Google Chat messages using keywords and filters. Works across all spaces the user has access to, or can be scoped to a specific conversation.\n"
     },
     {
       "name": "search_conversations",
       "input_class_name": "rustic_ai.mcp.connectors.google-chat.SearchConversationsInput",
       "description": "Searches for Google Chat conversations by display name.\n\nIf only participants are provided, this tool finds 1:1 direct messages (if one participant is provided) or group chats (if multiple participants are provided) that include the specified participants and the calling user.\n\nIf only a query is provided, this tool searches for conversations where the query is a case-insensitive substring of the conversation's display name.\n\nIf both participants and query are provided, this tool finds conversations by participants and then filters them by display name.\n\nIf neither participants nor query are provided, this tool lists all conversations the calling user is a member of.\n\nThis tool only lists conversations the calling user is a member of.\n\nIMPORTANT: An empty 'conversations' list does not mean there are no more results overall. If 'next_page_token' is present, more pages can be fetched. If you get an empty list but a 'next_page_token', ask the user if you should continue the searching.\n"
     },
     {
       "name": "send_message",
       "input_class_name": "rustic_ai.mcp.connectors.google-chat.SendMessageInput",
       "description": "Sends a Google Chat message to a conversation with Markdown formatting.\n\nThis tool uses a conversation ID, an optional thread ID, and a message text as inputs.\nConversation ID's can be found using the search_conversations tool.\nIt returns the created message.\n"
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, RootModel


class ListMessagesInput(BaseModel):
    """
    Request to list messages from a specific Google Chat conversation.
    """

    conversationId: Annotated[
        str,
        Field(
            description=(
                "Required. The ID of the conversation. A conversation can either be a space, direct message (DM) or"
                " group DM/Chat. Format: spaces/{space}"
            )
        ),
    ]
    endTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. ISO 8601 timestamp to filter messages. Only messages created before this time will be"
                " returned."
            )
        ),
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. The maximum number of messages to return. The service may return fewer than this value. If"
                " unspecified, defaults to 20. The maximum allowed value is 50."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. A page token, received from a previous list_messages call. Provide this to retrieve the"
                " subsequent page."
            )
        ),
    ] = None
    startTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. ISO 8601 timestamp to filter messages. Only messages created after this time will be"
                " returned."
            )
        ),
    ] = None
    threadId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The ID of a specific thread within the conversation. If provided, only messages from this"
                " thread will be returned. If omitted, messages from all threads in the conversation are considered."
                " Format: spaces/{space}/threads/{thread}"
            )
        ),
    ] = None


class OrderBy(Enum):
    """
    Optional. Specifies the order in which the results should be returned. Supported values: `CREATE_TIME_DESC`,
    `CREATE_TIME_ASC`, or `RELEVANCE_DESC`. NOTE: `RELEVANCE_DESC` cannot be used when the is_unread filter is used.
    By default, `RELEVANCE_DESC` is used if `is_unread` is not set to true, otherwise `CREATE_TIME_DESC` is used.
    """

    ORDER_BY_UNSPECIFIED = "ORDER_BY_UNSPECIFIED"
    CREATE_TIME_DESC = "CREATE_TIME_DESC"
    RELEVANCE_DESC = "RELEVANCE_DESC"


class SearchConversationsInput(BaseModel):
    """
    Request to search Google Chat conversations using filters.
    """

    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. The maximum number of spaces to return. The service may return fewer than this value. If"
                " unspecified, at most 100 spaces will be returned. The maximum value is 1000; values above 1000 will"
                " be coerced to 1000."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. A page token, received from a previous `search_conversations` call. Provide this to retrieve"
                " the subsequent page."
            )
        ),
    ] = None
    participants: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Optional. List of email addresses of the participants to filter the conversations, excluding the"
                " caller."
            )
        ),
    ] = None
    spaceNameQuery: Annotated[
        Optional[str], Field(description="Optional. The text to search for within the space display names.")
    ] = None


class SendMessageInput(BaseModel):
    """
    Request to send a message to a Google Chat conversation.
    """

    conversationId: Annotated[
        str, Field(description="Required. The ID of the conversation (e.g., 'spaces/AAAA...') to send the message to.")
    ]
    messageText: Annotated[
        str,
        Field(
            description=(
                "Required. The main content of the message. Formatting can be added using standard Markdown (note that"
                " tables are NOT supported). The following formatting is supported: * **Bold:** `**text**` *"
                " **Italic:** `*text*` or `_text_` * **Strikethrough:** `~~text~~` * **Monospace:** `text` *"
                " **Monospace block:** ``` line 1 line 2 ``` * **Bulleted list:** * item 1 * item 2 * **Ordered list:**"
                " 1. item 1 2. item 2 * **Block quote:** `> quoted text` * **Hyperlink:** `[label](url)` * **Mention"
                ' user:** Use a self-closing HTML tag `chat-user` with attributes `data-email="user@example.com"` or'
                ' `data-name="USER_ID"`. Prefer the data-name attribute with USER_ID if known and fallback to the'
                " data-email attribute with the user email otherwise. If you use the data-name attribute make sure to"
                " use the raw numeric USER_ID and NOT include the users/ prefix seen in other tool return values. *"
                ' **Custom emoji:** Use a self-closing HTML tag `chat-custom-emoji` with attributes `data-uid="abc"`'
                ' and `data-emoji-name=":xyz:"`.'
            )
        ),
    ]
    threadId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The ID of the thread (e.g., 'spaces/AAAA.../threads/BBBB...') to send the message to. If not"
                " set, the message will be sent to a new thread."
            )
        ),
    ] = None


class SearchParameters(RootModel[Any]):
    root: Any


class SearchMessagesInput(BaseModel):
    """
    Request to search for Google Chat messages using keywords and filters. Works across all spaces the user has
    access to, or can be scoped to a specific conversation.
    """

    orderBy: Annotated[
        Optional[OrderBy],
        Field(
            description=(
                "Optional. Specifies the order in which the results should be returned. Supported values:"
                " `CREATE_TIME_DESC`, `CREATE_TIME_ASC`, or `RELEVANCE_DESC`. NOTE: `RELEVANCE_DESC` cannot be used"
                " when the is_unread filter is used. By default, `RELEVANCE_DESC` is used if `is_unread` is not set to"
                " true, otherwise `CREATE_TIME_DESC` is used."
            )
        ),
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. The maximum number of results to return (max up to 100). If unspecified, at most 25 are"
                " returned."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. A page token, received from a previous `search_messages` call. Provide this to retrieve the"
                " subsequent page."
            )
        ),
    ] = None
    searchParameters: Annotated[
        SearchParameters, Field(description="Required. The search parameters to use for the search.")
    ]
