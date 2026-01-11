from enum import Enum
import os
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field
import serpapi
import shortuuid

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.messaging.core import JsonDict


class SearchEngines(Enum):
    google = {"key": "q"}
    bing = {"key": "q"}
    baidu = {"key": "q"}
    yahoo = {"key": "p"}
    duckduckgo = {"key": "q"}
    ebay = {"key": "_nkw"}
    yandex = {"key": "text"}
    home_depot = {"key": "keyword"}
    google_scholar = {"key": "q"}
    youtube = {"key": "search_query"}
    walmart = {"key": "query"}
    google_maps = {"key": "query"}
    google_patents = {"key": "q"}

    def get_query(self, query):
        return {self.value["key"]: query}


class SERPQuery(BaseModel):
    """
    A class representing a search query.
    """

    engine: str
    query: str
    id: str = Field(default="")
    num: Optional[int] = Field(default=12)
    start: Optional[int] = Field(default=0)


class SERPResults(BaseModel):
    """
    A class representing a search result.
    """

    engine: str
    query: str
    count: int
    id: str = Field(default="")
    results: List[MediaLink]
    total_results: Optional[int] = Field(default=None)


class SearchError(BaseModel):

    id: str = Field(default="")
    response: JsonDict


class SERPAgent(Agent):
    def __init__(self):
        self.serp_api_key = os.getenv("SERP_API_KEY", "")
        assert self.serp_api_key, "SERP_API_KEY environment variable not set"
        self.client = serpapi.Client(api_key=self.serp_api_key)  # type: ignore

    @agent.processor(SERPQuery)
    def search(self, ctx: agent.ProcessContext[SERPQuery]) -> None:
        """
        Handles the received message.

        Args:
            message (Message): The received message.
        """
        search_query = ctx.payload

        # Use the message.payload as search parameters
        search_params = SearchEngines[search_query.engine].get_query(search_query.query)

        # Execute asynchronous search and add it to the queue
        results = self.client.search(
            params=search_params,
            engine=search_query.engine,
            num=search_query.num,
            start=search_query.start,
        )

        metadata = results["search_metadata"]

        if metadata["status"] == "Success":
            # Get the search results
            search_results = results["organic_results"] if "organic_results" in results else []

            result_links = []

            # Publish the message
            for result in search_results:
                result.update({"search_parameters": search_params})

                filepath = urlparse(result["link"]).path
                filename = os.path.basename(filepath)

                if not filename:
                    filename = f"{shortuuid.uuid()}.html"

                metadata = {
                    "title": result["title"],
                    "favicon": result.get("favicon", ""),
                    "search_position": result["position"],
                    "snippet": result["snippet"],
                    "date": result.get("date", ""),
                    "query_id": search_query.id,
                }

                link = MediaLink(
                    url=result["link"],
                    name=filename,
                    metadata=metadata,
                    mimetype="text/html",
                    encoding="utf-8",
                )

                result_links.append(link)

            total_results = None
            if "search_information" in results and "total_results" in results["search_information"]:
                total_results = results["search_information"]["total_results"]

            ctx.send(
                SERPResults(
                    count=len(result_links),
                    results=result_links,
                    total_results=total_results,
                    id=search_query.id,
                    query=result["search_parameters"]["q"],
                    engine=result["search_parameters"]["engine"],
                ),
                new_thread=True,
            )
        else:
            # Publish the error message
            ctx.send(SearchError(response=results["search_metadata"], id=search_query.id))
