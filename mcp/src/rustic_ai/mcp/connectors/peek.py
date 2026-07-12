"""
Auto-generated Pydantic models for peek's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.peek.com"
   },
   "tools": [
     {
       "name": "experience_availability",
       "input_class_name": "rustic_ai.mcp.connectors.peek.ExperienceAvailabilityInput",
       "description": "Get availability information for a specific experience including dates, times, and pricing"
     },
     {
       "name": "experience_details",
       "input_class_name": "rustic_ai.mcp.connectors.peek.ExperienceDetailsInput",
       "description": "Get detailed information about a specific experience by ID"
     },
     {
       "name": "list_tags",
       "input_class_name": "rustic_ai.mcp.connectors.peek.ListTagsInput",
       "description": "List all category tags"
     },
     {
       "name": "render_activity_tiles",
       "input_class_name": "rustic_ai.mcp.connectors.peek.RenderActivityTilesInput",
       "description": "Render activity tiles for a list of activity IDs, returning an embeddable widget URI"
     },
     {
       "name": "search_experiences",
       "input_class_name": "rustic_ai.mcp.connectors.peek.SearchExperiencesInput",
       "description": "Search for travel experiences with comprehensive filtering options. Returns available categories, tags, and regions with IDs for further filtering."
     },
     {
       "name": "search_regions",
       "input_class_name": "rustic_ai.mcp.connectors.peek.SearchRegionsInput",
       "description": "Search for regions by name"
     }
   ]
 }

"""  # noqa

from typing import Annotated, Optional

from pydantic import BaseModel, Field


class ExperienceAvailabilityInput(BaseModel):
    endDate: Annotated[
        str,
        Field(
            description=(
                "End date inclusive in YYYY-MM-DD format (e.g., '2025-06-20' would return things taking place ON or"
                " BEFORE the 20th)"
            )
        ),
    ]
    id: Annotated[str, Field(description="The ID of the experience")]
    quantity: Annotated[int, Field(description="Number of travelers")]
    startDate: Annotated[str, Field(description="Start date inclusive YYYY-MM-DD format (e.g., '2025-06-19')")]


class ExperienceDetailsInput(BaseModel):
    id: Annotated[str, Field(description="The ID of the experience to retrieve")]


class ListTagsInput(BaseModel):
    pass


class RenderActivityTilesInput(BaseModel):
    id: Annotated[str, Field(description="ID or comma separate list of activity IDs to render as tiles")]


class SearchExperiencesInput(BaseModel):
    categoryId: Annotated[Optional[str], Field(description="Limit to only a specific activity category")] = None
    endDate: Annotated[
        Optional[str],
        Field(
            description=(
                "Return experiences that are available on or before this date in YYYY-MM-DD format (e.g., '2025-06-20'"
                " would return things taking place ON or BEFORE the 20th)"
            )
        ),
    ] = None
    latLng: Annotated[
        Optional[str],
        Field(
            description=(
                "When the user wants something NEAR a specific place, but not necessarily IN a specific place, limit to"
                ' only those near a given lat_lng. ex: "37.7799,-122.2822". Don\'t use this for regions, instead use'
                " the search_regions and provide a region id. this is a good fallback if a specific region is lacking"
                " inventory."
            )
        ),
    ] = None
    query: Annotated[
        Optional[str],
        Field(
            description=(
                "When the user wants something w/ a specific keyword (bike, beer, art, etc) limit to experiences whose"
                " title contain a keyword. Never include location information."
            )
        ),
    ] = None
    regionId: Annotated[
        Optional[str],
        Field(
            description=(
                "When you have determined the user wants something in a specific region (found w/ search_regions) limit"
                " to only a specific region ID"
            )
        ),
    ] = None
    startDate: Annotated[
        Optional[str],
        Field(
            description=(
                "Return experiences that are available on or after this date. YYYY-MM-DD format (e.g., '2025-06-19')"
            )
        ),
    ] = None
    tagId: Annotated[
        Optional[str],
        Field(
            description=(
                "When you have determined the user is interest in a specific vibe of activity (family friendly,"
                " romantic, etc) limit to only experiences with a specific tag (single tag ID)"
            )
        ),
    ] = None


class SearchRegionsInput(BaseModel):
    limit: Annotated[Optional[int], Field(description="Maximum number of regions to return (default: 50)")] = None
    query: Annotated[str, Field(description="Search query to match against region names")]
