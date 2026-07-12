"""
Auto-generated Pydantic models for exa's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa,web_search_advanced_exa"
   },
   "tools": [
     {
       "name": "web_search_exa",
       "input_class_name": "rustic_ai.mcp.connectors.exa.WebSearchExaInput",
       "description": "Search the web for any topic and get clean, ready-to-use content.\n\n      Best for: Finding current information, news, facts, people, companies, or answering questions about any topic.\n      Returns: Clean text content from top search results.\n\n      Query tips:\n      describe the ideal page, not keywords. \"blog post comparing React and Vue performance\" not \"React vs Vue\".\n      Use category:people / category:company to search through Linkedin profiles / companies respectively.\n      If highlights are insufficient, follow up with web_fetch_exa on the best URLs."
     },
     {
       "name": "web_search_advanced_exa",
       "input_class_name": "rustic_ai.mcp.connectors.exa.WebSearchAdvancedExaInput",
       "description": "Advanced web search with full control over filters, domains, dates, and content options.\n\nBest for: When you need specific filters like date ranges, domain restrictions, or category filters.\nNot recommended for: Simple searches - use web_search_exa instead.\nReturns: Search results with optional highlights, summaries, and subpage content."
     },
     {
       "name": "web_fetch_exa",
       "input_class_name": "rustic_ai.mcp.connectors.exa.WebFetchExaInput",
       "description": "Read a webpage's full content as clean markdown. Use after web_search_exa when highlights are insufficient or to read any URL.\n\nBest for: Extracting full content from known URLs. Batch multiple URLs in one call.\nReturns: Clean text content and metadata from the page(s)."
     }
   ],
   "auth_header": "x-api-key"
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


class WebSearchExaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[
        str,
        Field(
            description=(
                "Natural language search query. Should be a semantically rich description of the ideal page, not just"
                " keywords. Optionally include category:<type> (company, people) to focus results — e.g."
                " 'category:people John Doe software engineer'."
            ),
            min_length=1,
        ),
    ]
    numResults: Annotated[Optional[float], Field(description="Number of search results to return (default: 10).")] = (
        None
    )


class Type(Enum):
    """
    Search type - 'auto': high quality and works with all filters (recommended), 'fast': quick results, 'instant': fastest results
    """

    AUTO = "auto"
    FAST = "fast"
    INSTANT = "instant"


class Category(Enum):
    """
    Filter results to a specific category
    """

    COMPANY = "company"
    RESEARCH_PAPER = "research paper"
    NEWS = "news"
    PDF = "pdf"
    GITHUB = "github"
    PERSONAL_SITE = "personal site"
    PEOPLE = "people"
    FINANCIAL_REPORT = "financial report"


class WebSearchAdvancedExaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: Annotated[str, Field(description="Search query - can be a question, statement, or keywords", min_length=1)]
    numResults: Annotated[Optional[float], Field(description="Number of results (1-100, default: 10)")] = None
    type: Annotated[
        Optional[Type],
        Field(
            description=(
                "Search type - 'auto': high quality and works with all filters (recommended), 'fast': quick results,"
                " 'instant': fastest results"
            )
        ),
    ] = None
    category: Annotated[Optional[Category], Field(description="Filter results to a specific category")] = None
    includeDomains: Annotated[
        Optional[list[str]],
        Field(description="Only include results from these domains (e.g., ['arxiv.org', 'github.com'])"),
    ] = None
    excludeDomains: Annotated[Optional[list[str]], Field(description="Exclude results from these domains")] = None
    startPublishedDate: Annotated[
        Optional[str], Field(description="Only include results published after this date (ISO 8601: YYYY-MM-DD)")
    ] = None
    endPublishedDate: Annotated[
        Optional[str], Field(description="Only include results published before this date (ISO 8601: YYYY-MM-DD)")
    ] = None
    startCrawlDate: Annotated[
        Optional[str], Field(description="Only include results crawled after this date (ISO 8601: YYYY-MM-DD)")
    ] = None
    endCrawlDate: Annotated[
        Optional[str], Field(description="Only include results crawled before this date (ISO 8601: YYYY-MM-DD)")
    ] = None
    includeText: Annotated[
        Optional[list[str]], Field(description="Only include results containing ALL of these text strings")
    ] = None
    excludeText: Annotated[
        Optional[list[str]], Field(description="Exclude results containing ANY of these text strings")
    ] = None
    userLocation: Annotated[
        Optional[str], Field(description="ISO country code for geo-targeted results (e.g., 'US', 'GB', 'DE')")
    ] = None
    moderation: Annotated[Optional[bool], Field(description="Filter out unsafe/inappropriate content")] = None
    additionalQueries: Annotated[
        Optional[list[str]], Field(description="Additional query variations to expand search coverage")
    ] = None
    textMaxCharacters: Annotated[
        Optional[float], Field(description="Max characters for text extraction per result", ge=1.0)
    ] = None
    contextMaxCharacters: Annotated[
        Optional[float], Field(description="Max characters for context string (not included by default)", ge=1.0)
    ] = None
    enableSummary: Annotated[Optional[bool], Field(description="Enable summary generation for results")] = None
    summaryQuery: Annotated[Optional[str], Field(description="Focus query for summary generation")] = None
    enableHighlights: Annotated[Optional[bool], Field(description="Enable highlights extraction")] = None
    highlightsMaxCharacters: Annotated[
        Optional[float],
        Field(
            description="Maximum total characters across all highlights per URL. Preferred over highlightsNumSentences."
        ),
    ] = None
    highlightsNumSentences: Annotated[
        Optional[float],
        Field(description="Deprecated: mapped to ~1333 chars/sentence. Use highlightsMaxCharacters instead."),
    ] = None
    highlightsPerUrl: Annotated[
        Optional[float],
        Field(description="Deprecated: currently ignored server-side. Use highlightsMaxCharacters instead."),
    ] = None
    highlightsQuery: Annotated[Optional[str], Field(description="Query for highlight relevance")] = None
    maxAgeHours: Annotated[
        Optional[float],
        Field(
            description=(
                "Maximum age of cached content in hours. 0 = always fetch fresh content, omit = use cached content with"
                " fresh fetch fallback"
            )
        ),
    ] = None
    livecrawlTimeout: Annotated[
        Optional[float],
        Field(description="Timeout in milliseconds for fetching fresh content when maxAgeHours triggers a live fetch"),
    ] = None
    subpages: Annotated[Optional[float], Field(description="Number of subpages to crawl from each result (1-10)")] = (
        None
    )
    subpageTarget: Annotated[Optional[list[str]], Field(description="Keywords to target when selecting subpages")] = (
        None
    )


class WebFetchExaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    urls: Annotated[list[str], Field(description="URLs to read. Batch multiple URLs in one call.")]
    maxCharacters: Annotated[
        Optional[float], Field(description="Maximum characters to extract per page (default: 3000)", ge=1.0)
    ] = None
