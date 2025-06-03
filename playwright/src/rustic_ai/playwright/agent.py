from enum import StrEnum
import hashlib
import logging
import mimetypes
import os
from typing import List, Set
from urllib.parse import urljoin, urlsplit

from install_playwright import install
from markdownify import markdownify as md
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import Agent, AgentSpec, agent
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import FileSystem
from rustic_ai.core.utils.json_utils import JsonDict


class ScrapingOutputFormat(StrEnum):
    TEXT_HTML = "text/html"
    MARKDOWN = "text/markdown"


class WebScrapingRequest(BaseModel):
    id: str = Field(default_factory=shortuuid.uuid, title="ID of the request")
    links: List[MediaLink] = Field(..., title="URL to scrape")
    output_format: ScrapingOutputFormat = Field(
        default=ScrapingOutputFormat.TEXT_HTML,
        title="Output format of the scraped content",
        description="The format in which the scraped content will be saved. Default is text/html.",
    )

    transformer_options: JsonDict = Field(
        default={},
        title="Options for the transformer",
        description="Options for the transformer to be applied to the scraped content. Default is an empty dictionary.",
    )

    scrape_nav_links: int = Field(
        default=0,
        title="Number of links to scrape from nav bar",
        description="The number of links to scrape from navigation bar of website, -1 to scrape all",
    )
    force: bool = Field(
        default=False,
        title="Force scrape the url",
        description="Even if the url was scraped earlier will scrape it if force is set to true. This is used to avoid same url to be scrapped multiple times",
    )


class WebScrapingCompleted(BaseModel):
    id: str = Field(..., title="ID of the request")
    links: List[MediaLink] = Field(..., title="URL to scrape")


class PlaywrightScraperAgent(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec)
        self.scraped_urls: Set[str] = set()

    @agent.processor(
        WebScrapingRequest, depends_on=[agent.AgentDependency(dependency_key="filesystem", guild_level=True)]
    )
    async def scrape(self, ctx: agent.ProcessContext[WebScrapingRequest], filesystem: FileSystem) -> None:
        async with async_playwright() as p:
            install(p.chromium)
            browser = await p.chromium.launch()
            page = await browser.new_page()

            scraping_request = ctx.payload

            scraped_docs: List[MediaLink] = []

            for link in scraping_request.links:

                async def scrape_and_store(current_url: str):
                    response = await page.goto(current_url)

                    if response and response.status != 200:
                        ctx.send_error(
                            ErrorMessage(
                                agent_type=self.get_qualified_class_name(),
                                error_type="HTTP_ERROR_{response.status}",
                                error_message=f"HTTP error: {response.status} for URL: {current_url}. Error message: {response.status_text}",
                            )
                        )
                        return

                    title = await page.title()
                    content = await page.content()
                    urls = urlsplit(current_url)
                    upath = urls.path
                    basename = os.path.basename(upath)
                    _, filetype = os.path.splitext(basename)

                    if not filetype and scraping_request.output_format == ScrapingOutputFormat.TEXT_HTML:
                        filetype = ".html"
                    elif scraping_request.output_format == ScrapingOutputFormat.MARKDOWN:
                        filetype = ".md"
                    elif not filetype:
                        filetype = ".txt"

                    filename = hashlib.md5(content.encode("utf-8")).hexdigest() + filetype

                    mimetype = mimetypes.guess_type(filename)[0]

                    try:
                        if scraping_request.output_format == ScrapingOutputFormat.MARKDOWN:
                            content = md(
                                content,
                                **scraping_request.transformer_options,
                            )
                        with filesystem.open(f"scraped_data/{filename}", "w") as f:
                            f.write(content)
                    except Exception as e:
                        logging.error(f"Error writing file: {e}")
                        ctx.send_error(
                            ErrorMessage(
                                agent_type=self.get_qualified_class_name(),
                                error_type="FileWriteError",
                                error_message=str(e),
                            )
                        )

                    meta = link.metadata or {}
                    metadata = meta | {"scraped_url": current_url, "title": title, "request_id": scraping_request.id}

                    output = MediaLink(
                        url=f"scraped_data/{filename}",
                        name=filename,
                        metadata=metadata,
                        on_filesystem=True,
                        mimetype=mimetype,
                        encoding="utf-8",
                    )

                    scraped_docs.append(output)
                    self.scraped_urls.add(current_url)
                    ctx.send(output)

                if link.url not in self.scraped_urls or scraping_request.force:
                    await scrape_and_store(link.url)

                if scraping_request.scrape_nav_links != 0:

                    # Scrape from navigation bar links
                    nav_links = await page.eval_on_selector_all(
                        "nav a[href], header a[href]",  # This targets common nav structures
                        "elements => elements.map(el => el.href)",
                    )

                    unique_links = set()
                    for nav_link in nav_links:
                        full_url = urljoin(link.url, nav_link)
                        if (full_url not in unique_links) and (full_url not in self.scraped_urls):
                            unique_links.add(full_url)

                    count_links = (
                        len(unique_links)
                        if scraping_request.scrape_nav_links == -1
                        else scraping_request.scrape_nav_links
                    )
                    for nav_url in list(unique_links)[:count_links]:
                        try:
                            await scrape_and_store(nav_url)
                        except Exception as e:
                            ctx.send_error(
                                ErrorMessage(
                                    agent_type=self.get_qualified_class_name(),
                                    error_type="SCRAPE_NAV_ERROR",
                                    error_message=f"Error scraping nav URL {nav_url}: {str(e)}",
                                )
                            )

            await browser.close()

            unique_scraped_docs = list({doc.name: doc for doc in scraped_docs}.values())

            ctx.send(WebScrapingCompleted(id=scraping_request.id, links=unique_scraped_docs))
