"""
Auto-generated Pydantic models for google-drive's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://drivemcp.googleapis.com/mcp/v1"
   },
   "tools": [
     {
       "name": "copy_file",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.CopyFileInput",
       "description": "Call this tool to copy an existing File in Google Drive.\nThe tool allows specifying a new title and a parent folder for the copy.\nIf the title is not specified, the copy title will be 'Copy of {original title}'If the parent folder is not specified, the copy will be created in the same folder as the original file, unless the requesting user does not have write access to that folder, in which case the copy will be created in the user's root folder.Returns the newly created File object upon successful copying.\n"
     },
     {
       "name": "create_file",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.CreateFileInput",
       "description": "Call this tool to create or upload a File to Google Drive.\n\nIf uploading content, prefer \"text_content\" for text content. For non-UTF8 contents, use the \"base64_content\" field and base64 encode the data to set on that field.\n\nReturns a single File object upon successful creation.\n\nThe following Google Drive first-party mime types can be created without providing content:\n\n - `application/vnd.google-apps.document` \n - `application/vnd.google-apps.spreadsheet` \n - `application/vnd.google-apps.presentation` \n\nBy default, the following conversions will be made for the following mime types:\n\n - `text/plain` to `application/vnd.google-apps.document` \n - `text/csv` to `application/vnd.google-apps.spreadsheet` \n\nTo disable conversions for first-party mime types, set `disable_conversion_to_google_type` to true.\n\nFolders can be created by setting the mime type to `application/vnd.google-apps.folder`.\n\nWhen uploading content, the `content_mime_type` field is required and should match the type of the content being uploaded.\n"
     },
     {
       "name": "download_file_content",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.DownloadFileContentInput",
       "description": "Call this tool to download the content of a Drive file as a base64 encoded string.\n\nIf the file is a Google Drive first-party mime type, the `exportMimeType` field is required and will determine the format of the downloaded file.\n\nIf the file is not found, try using other tools like `search_files` to find the file the user is requesting.\n\nIf the user wants a natural language representation of their Drive content, use the `read_file_content` tool (`read_file_content` should be smaller and easier to parse).\n"
     },
     {
       "name": "get_file_metadata",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.GetFileMetadataInput",
       "description": "Call this tool to find general metadata about a user's Drive file.\n\nIf the file is not found, try using other tools like `search_files` to find the file the user is requesting.\n"
     },
     {
       "name": "get_file_permissions",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.GetFilePermissionsInput",
       "description": "Call this tool to list the permissions of a Drive File.\n"
     },
     {
       "name": "list_recent_files",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.ListRecentFilesInput",
       "description": "Call this tool to find recent files for a user specified a sort order. Default sort order is `recency`.\n\nSupported sort orders are:\n\n - `recency`: The most recent timestamp from the file's date-time fields.\n - `lastModified`: The last time the file was modified by anyone.\n - `lastModifiedByMe`: The last time the file was modified by the user.\n\nThe default page size is 10. Utilize `next_page_token` to paginate through the results.\n"
     },
     {
       "name": "read_file_content",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.ReadFileContentInput",
       "description": "Call this tool to fetch a natural language representation of a Drive file, and optionally, its comments.\n\nThe file content may be incomplete for very large files. The text representation will change over time, so don't make assumptions about the particular format of the text returned by this tool.If supported, comment tags will be included in the content.\n\nSupported Mime Types:\n\n - `application/vnd.google-apps.document` \n - `application/vnd.google-apps.presentation` \n - `application/vnd.google-apps.spreadsheet` \n - `application/pdf` \n - `application/msword` \n - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` \n - `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` \n - `application/vnd.openxmlformats-officedocument.presentationml.presentation` \n - `application/vnd.oasis.opendocument.spreadsheet` \n - `application/vnd.oasis.opendocument.presentation` \n - `application/x-vnd.oasis.opendocument.text` \n - `image/png` \n - `image/jpeg` \n - `image/jpg` \n\nIf the file is not found, try using other tools like `search_files` to find the file the user is requesting using keywords.\n"
     },
     {
       "name": "search_files",
       "input_class_name": "rustic_ai.mcp.connectors.google-drive.SearchFilesInput",
       "description": "Search for Drive files using a structured query (syntax: `query_term operator values`).\nCombine clauses with `and`, `or`, `not`, and parentheses. String values must be single-quoted; escape embedded quotes as `\\'`. \n\nQuery terms & operators:\n\n - `title` (ops: contains, =, !=) \u2014 file title\n - `fullText` (ops: contains) \u2014 title or body text\n - `mimeType` (ops: contains, =, !=) \u2014 MIME type\n - `modifiedTime`, `viewedByMeTime`, `createdTime` (ops: `<=`, `<`, `=`, `!=`, `>`, `>=`). Use RFC 3339 UTC, e.g., `2012-06-04T12:00:00-08:00`. Date types not comparable.\n - `parentId` (ops: `=`, `!=`). Use `'root'` for the user's \"My Drive\".\n - `owner` (ops: `=`, `!=`). Use `'me'` for the requesting user.\n - `sharedWithMe` (ops: `=`, `!=`). Values: `true` or `false`.\n\nOther operators: `and`, `or`, `not`.\n\nExamples:\n\n - `title contains 'hello' and title contains 'goodbye'`\n - `modifiedTime > '2024-01-01T00:00:00Z' and (mimeType contains 'image/' or mimeType contains 'video/')`\n - `parentId = '1234567'`\n - `fullText contains 'hello'`\n - `owner = 'test@example.org'`\n - `sharedWithMe = true`\n - `owner = 'me'` (for files owned by the user)\n\nUse `next_page_token` to paginate. An empty response means no more results.\n"
     }
   ]
 }

"""  # noqa

from typing import Annotated, Optional

from pydantic import BaseModel, Field


class CopyFileInput(BaseModel):
    """
    Request to copy a file.
    """

    fileId: Annotated[str, Field(description="Required. The ID of the file to copy.")]
    parentId: Annotated[
        Optional[str],
        Field(
            description=(
                "The parent id of the newly created file. If empty, the file will be created with the same parent as"
                " the original file."
            )
        ),
    ] = None
    title: Annotated[
        Optional[str],
        Field(
            description=(
                "The title of the newly created file. If empty, the title will be 'Copy of [original file title]'."
            )
        ),
    ] = None


class CreateFileInput(BaseModel):
    """
    Request to upload a file.
    """

    base64Content: Annotated[
        Optional[str],
        Field(
            description="Optional. The base64 encoded content to upload. It's an error to set this and text_content."
        ),
    ] = None
    content: Annotated[
        Optional[str],
        Field(
            description=(
                "The content of the file encoded as base64. The content field should always be base64 encoded"
                " regardless of the mime type of the file. DEPRECATED. Use base64_content or text_content instead."
            )
        ),
    ] = None
    contentMimeType: Annotated[
        Optional[str],
        Field(
            description="The mime type of the content being uploaded. Required when any type of content is provided."
        ),
    ] = None
    disableConversionToGoogleType: Annotated[
        Optional[bool],
        Field(
            description=(
                "Set to true to retain the passed in content mime type and not convert to a Google type. For example,"
                " without this a text/plain content mime type will be converted to to an"
                " application/vnd.google-apps.document. Has no effect for types that do not have a Google equivalent."
            )
        ),
    ] = None
    mimeType: Annotated[Optional[str], Field(description="DEPRECATED. DO NOT USE!! Set content_mime_type instead.")] = (
        None
    )
    parentId: Annotated[Optional[str], Field(description="The parent id of the file.")] = None
    textContent: Annotated[
        Optional[str],
        Field(
            description="Optional. The (UTF-8) text content to upload. It's an error to set this and base64_content."
        ),
    ] = None
    title: Annotated[Optional[str], Field(description="The title of the file.")] = None


class DownloadFileContentInput(BaseModel):
    """
    Defines a request to download a file's content.
    """

    exportMimeType: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. For Google native files, the MIME type to export the file to, ignored otherwise. Defaults to"
                " text if not specified."
            )
        ),
    ] = None
    fileId: Annotated[str, Field(description="Required. The ID of the file to retrieve.")]


class GetFileMetadataInput(BaseModel):
    """
    Request to get the file.
    """

    excludeContentSnippets: Annotated[
        Optional[bool], Field(description="If true, the content snippet will be excluded from the response.")
    ] = None
    fileId: Annotated[str, Field(description="Required. The ID of the file to retrieve.")]


class GetFilePermissionsInput(BaseModel):
    """
    Request to get file permissions.
    """

    fileId: Annotated[str, Field(description="Required. The ID of the file to get permissions for.")]


class ListRecentFilesInput(BaseModel):
    """
    Request to list files.
    """

    excludeContentSnippets: Annotated[
        Optional[bool], Field(description="If true, the content snippet will be excluded from the response.")
    ] = None
    orderBy: Annotated[Optional[str], Field(description="The sort order for the files.")] = None
    pageSize: Annotated[Optional[int], Field(description="The maximum number of files to return.")] = None
    pageToken: Annotated[Optional[str], Field(description="The page token to use for pagination.")] = None


class ReadFileContentInput(BaseModel):
    """
    Request to read file content with support for fetching comments.
    """

    fileId: Annotated[str, Field(description="Required. The ID of the file to retrieve.")]
    includeComments: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether to include comments in the response. Comments will be inlined in the text content of the file"
                " with a mapping to the comment threads."
            )
        ),
    ] = None


class SearchFilesInput(BaseModel):
    """
    Request to search files.
    """

    excludeContentSnippets: Annotated[
        Optional[bool], Field(description="If true, the content snippet will be excluded from the response.")
    ] = None
    pageSize: Annotated[Optional[int], Field(description="The maximum number of files to return in each page.")] = None
    pageToken: Annotated[Optional[str], Field(description="The page token to use for pagination.")] = None
    query: Annotated[Optional[str], Field(description="The search query.")] = None
