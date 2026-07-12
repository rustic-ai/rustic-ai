"""
Auto-generated Pydantic models for godaddy's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://api.godaddy.com/v1/domains/mcp"
   },
   "tools": [
     {
       "name": "domains_suggest",
       "input_class_name": "rustic_ai.mcp.connectors.godaddy.DomainsSuggestInput",
       "description": "Generate domain name suggestions based on keywords, seed domains, or business descriptions. Returns an interactive widget with clickable domain links for clients that support HTML rendering (browsers, web-based AI assistants), with automatic fallback to formatted text for other clients. IMPORTANT: Always display the registration links from the response to the user - each domain has a direct GoDaddy registration URL that must be shown."
     },
     {
       "name": "domains_check_availability",
       "input_class_name": "rustic_ai.mcp.connectors.godaddy.DomainsCheckAvailabilityInput",
       "description": "Check if domain names are available for registration. Works with single domains or lists of multiple domains. Returns formatted results with availability status and registration options ready for display. IMPORTANT: Always display the registration links from the response to the user - each domain has a direct GoDaddy registration URL that must be shown."
     }
   ]
 }

"""  # noqa

from typing import Annotated, Optional

from pydantic import BaseModel, Field


class DomainsSuggestInput(BaseModel):
    query: Annotated[
        str,
        Field(
            description=(
                "Search query for domain suggestions. Can be: 1) Keywords (e.g., 'tech startup', 'coffee shop') 2) Seed"
                " domain name (e.g., 'example') 3) Business description (e.g., 'AI-powered customer service chatbot')."
                " Maximum 300 characters. Longer queries will be optimized using AI."
            ),
            max_length=300,
            min_length=1,
            title="Query",
        ),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            description="Maximum number of domain suggestions to return. Valid range: 1-100. Default: 40.",
            ge=1,
            le=100,
            title="Limit",
        ),
    ] = 40


class DomainsCheckAvailabilityInput(BaseModel):
    domains: Annotated[
        str,
        Field(
            description=(
                "Domain name(s) to check for availability. Single domain: 'example.com' OR Multiple domains"
                " (comma-separated): 'example.com, test.org, mybrand.io'. Each domain must include TLD extension (.com,"
                " .net, .org, etc.). Automatically routes to exact search (1 domain) or bulk search (2+ domains)."
                " Maximum 1000 domains per request."
            ),
            examples=["example.com", "example.com, test.org, mybrand.io"],
            title="Domains",
        ),
    ]
