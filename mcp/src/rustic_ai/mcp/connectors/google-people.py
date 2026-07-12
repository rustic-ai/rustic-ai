"""
Auto-generated Pydantic models for google-people's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://people.googleapis.com/mcp/v1"
   },
   "tools": [
     {
       "name": "search_directory_people",
       "input_class_name": "rustic_ai.mcp.connectors.google-people.SearchDirectoryPeopleInput",
       "description": "Search for people within your organization's Google Workspace directory. This feature is exclusively for Google Workspace accounts (used by businesses, schools, and other organizations) and is not available for personal Google accounts.\n\n**IMPORTANT RULES TO FOLLOW:**\n\n* If this tool returns multiple results, you should present the results to the user and prompt the user for clarification on which result to use before proceeding.\n\n* You are strictly forbidden from passing the output of this tool into another tool (e.g., sending an email, creating a draft, creating an event, etc.) without explicit user confirmation.\n\n* Even if only one person result is found, you must present the found person's details to the user and prompt the user to verify that this is the intended person before proceeding with further steps.\n\n* If this tool returns no results, fall back to using the `search_contacts` tool.\n"
     },
     {
       "name": "search_contacts",
       "input_class_name": "rustic_ai.mcp.connectors.google-people.SearchContactsInput",
       "description": "Search user's contacts.\n\n**IMPORTANT RULES TO FOLLOW:**\n\n* If this tool returns multiple results, you should present the results to the user and prompt the user for clarification on which result to use before proceeding.\n\n* You are strictly forbidden from passing the output of this tool into another tool (e.g., sending an email, creating a draft, creating an event, etc.) without explicit user confirmation.\n\n* Even if only one person result is found, you must present the found person's details to the user and prompt the user to verify that this is the intended person before proceeding with further steps.\n"
     },
     {
       "name": "get_user_profile",
       "input_class_name": "rustic_ai.mcp.connectors.google-people.GetUserProfileInput",
       "description": "Get profile info about yourself (name and email)."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field


class Source(Enum):
    DOMAIN_PROFILE = "DOMAIN_PROFILE"
    DOMAIN_CONTACT = "DOMAIN_CONTACT"


class SearchDirectoryPeopleInput(BaseModel):
    """
    Request message for SearchDirectoryPeople.
    """

    pageSize: Annotated[
        Optional[int], Field(description="Page size. The default is 10 and the maximum allowed value is 500.")
    ] = None
    pageToken: Annotated[Optional[str], Field(description="Page token.")] = None
    query: Annotated[Optional[str], Field(description="Query string to search for.")] = None
    sources: Annotated[
        Optional[list[Source]], Field(description="Directory sources to return. Defaults to DOMAIN_PROFILE if not set.")
    ] = None


class SearchContactsInput(BaseModel):
    """
    Request message for SearchContacts.
    """

    maxResults: Annotated[
        Optional[int],
        Field(description="Max number of results. The default is 10 and the maximum allowed value is 30."),
    ] = None
    query: Annotated[Optional[str], Field(description="Query string to search for.")] = None


class GetUserProfileInput(BaseModel):
    """
    Request message for GetUserProfile.
    """
