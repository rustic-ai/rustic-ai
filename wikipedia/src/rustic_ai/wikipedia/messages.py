from typing import Optional

from pydantic import BaseModel, Field


class WikipediaSearchRequest(BaseModel):
    """Request to search Wikipedia articles."""

    query: str = Field(..., description="Search query")
    results: int = Field(default=10, description="Number of search results to return")


class WikipediaSearchResponse(BaseModel):
    """Response containing Wikipedia search results."""

    query: str
    results: list[str] = Field(default_factory=list, description="List of article titles matching the query")


class WikipediaPageRequest(BaseModel):
    """Request to fetch a Wikipedia page."""

    title: str = Field(..., description="Wikipedia article title")
    auto_suggest: bool = Field(default=True, description="Whether to auto-suggest alternative titles")


class WikipediaPageResponse(BaseModel):
    """Response containing Wikipedia page content."""

    title: str
    summary: str
    content: str
    url: str
    images: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class WikipediaSummaryRequest(BaseModel):
    """Request to fetch a Wikipedia page summary."""

    title: str = Field(..., description="Wikipedia article title")
    sentences: int = Field(default=5, description="Number of sentences in the summary")
    auto_suggest: bool = Field(default=True, description="Whether to auto-suggest alternative titles")


class WikipediaSummaryResponse(BaseModel):
    """Response containing Wikipedia page summary."""

    title: str
    summary: str
    url: str


class WikipediaError(BaseModel):
    """Error response from Wikipedia operations."""

    error_type: str
    message: str
    query: Optional[str] = None
