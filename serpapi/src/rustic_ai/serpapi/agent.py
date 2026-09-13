from collections.abc import Mapping
from enum import Enum
import os
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field
import serpapi
from serpapi.exceptions import (
    HTTPConnectionError,
    HTTPError,
    SerpApiError,
    TimeoutError,
)
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
        self.logger.debug(f"Received search query: {search_query.query} for engine: {search_query.engine}")

        # Use the message.payload as search parameters
        search_params = SearchEngines[search_query.engine].get_query(search_query.query)

        # Execute asynchronous search and add it to the queue
        try:
            results = self.client.search(
                params=search_params,
                engine=search_query.engine,
                num=search_query.num,
                start=search_query.start,
            )
        except TimeoutError:
            self._send_search_error(ctx, "search_timeout")
            return
        except HTTPConnectionError:
            self._send_search_error(ctx, "search_unavailable")
            return
        except (HTTPError, SerpApiError):
            self._send_search_error(ctx, "search_provider_error")
            return

        if not isinstance(results, Mapping):
            self._send_search_error(ctx, "invalid_provider_response")
            return

        provider_results = dict(results)
        metadata = provider_results.get("search_metadata")
        if not isinstance(metadata, Mapping) or not isinstance(metadata.get("status"), str):
            self._send_search_error(ctx, "invalid_provider_response")
            return

        if metadata["status"] == "Success":
            # Get the search results
            search_results = provider_results.get("organic_results", [])
            if not isinstance(search_results, list) or any(
                not isinstance(result, Mapping) for result in search_results
            ):
                self._send_search_error(ctx, "invalid_provider_response")
                return

            result_links = []

            # Publish the message
            for provider_result in search_results:
                result = dict(provider_result)
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
            search_information = provider_results.get("search_information")
            if isinstance(search_information, Mapping) and "total_results" in search_information:
                total_results = search_information["total_results"]

            self.logger.debug(
                f"Publishing {len(result_links)} search results for query: {search_query.query} with total results: {total_results}"
            )

            ctx.send(
                SERPResults(
                    count=len(result_links),
                    results=result_links,
                    total_results=total_results,
                    id=search_query.id,
                    query=search_query.query,
                    engine=search_query.engine,
                ),
                new_thread=True,
            )
        else:
            self._send_search_error(ctx, "search_rejected")

    @staticmethod
    def _send_search_error(ctx: agent.ProcessContext[SERPQuery], code: str) -> None:
        ctx.send_error(
            SearchError(
                id=ctx.payload.id,
                response={
                    "status": "Error",
                    "code": code,
                    "error": "The search provider could not complete the request.",
                },
            )
        )
