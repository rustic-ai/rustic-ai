"""ArXiv Toolset - Search academic papers on ArXiv.

This toolset provides the SearchArxiv tool for retrieving academic papers
from the ArXiv repository based on search queries.
"""

import json
from typing import List

import arxiv
from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset


class ArxivSearchParams(BaseModel):
    """Parameters for the SearchArxiv tool."""

    query: str = Field(
        description="Search query for ArXiv papers. Can include keywords, author names, "
        "or ArXiv-specific search syntax (e.g., 'au:smith AND ti:neural')"
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return (1-20)",
    )
    sort_by: str = Field(
        default="relevance",
        description="Sort order: 'relevance', 'submitted_date', or 'last_updated'",
    )


class ArxivToolset(ReActToolset):
    """
    A ReActToolset for searching academic papers on ArXiv.

    This toolset exposes a single tool, SearchArxiv, which queries the ArXiv
    repository and returns structured results including titles, abstracts,
    authors, publication dates, and PDF URLs.

    Example usage in guild spec:
        properties:
          toolset:
            kind: rustic_ai.showcase.iterative_studio.toolsets.arxiv_toolset.ArxivToolset
    """

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return the list of tool specifications available in this toolset."""
        return [
            ToolSpec(
                name="SearchArxiv",
                description=(
                    "Search academic papers on ArXiv by topic, author, or keywords. "
                    "Returns paper titles, abstracts, authors, publication dates, and PDF URLs. "
                    "Use this tool to find relevant research papers for academic or technical tasks."
                ),
                parameter_class=ArxivSearchParams,
            )
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """
        Execute a tool by name with the given arguments.

        Args:
            tool_name: The name of the tool to execute.
            args: The parsed arguments as a Pydantic model instance.

        Returns:
            The result of the tool execution as a JSON string.

        Raises:
            ValueError: If the tool name is not recognized.
        """
        if tool_name == "SearchArxiv" and isinstance(args, ArxivSearchParams):
            return self._search_arxiv(args)
        raise ValueError(f"Unknown tool: {tool_name}")

    def _search_arxiv(self, params: ArxivSearchParams) -> str:
        """Execute an ArXiv search and return formatted results."""
        # Map sort_by string to arxiv.SortCriterion
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "submitted_date": arxiv.SortCriterion.SubmittedDate,
            "last_updated": arxiv.SortCriterion.LastUpdatedDate,
        }
        sort_criterion = sort_map.get(params.sort_by, arxiv.SortCriterion.Relevance)

        # Create search query
        search = arxiv.Search(
            query=params.query,
            max_results=min(params.max_results, 20),
            sort_by=sort_criterion,
        )

        # Execute search and format results
        client = arxiv.Client()
        results = []

        try:
            for paper in client.results(search):
                # Truncate abstract if too long
                abstract = paper.summary
                if len(abstract) > 500:
                    abstract = abstract[:497] + "..."

                # Format authors (limit to first 5)
                authors = [a.name for a in paper.authors[:5]]
                if len(paper.authors) > 5:
                    authors.append(f"... and {len(paper.authors) - 5} more")

                results.append(
                    {
                        "title": paper.title,
                        "abstract": abstract,
                        "pdf_url": paper.pdf_url,
                        "authors": authors,
                        "published": paper.published.strftime("%Y-%m-%d"),
                        "arxiv_id": paper.entry_id.split("/")[-1],
                        "primary_category": paper.primary_category,
                    }
                )
        except Exception as e:
            return json.dumps({"error": f"ArXiv search failed: {str(e)}"}, indent=2)

        if not results:
            return json.dumps({"message": "No papers found matching your query."}, indent=2)

        return json.dumps(
            {
                "query": params.query,
                "result_count": len(results),
                "papers": results,
            },
            indent=2,
        )
