import hashlib
import logging
import mimetypes
import os
from enum import StrEnum
from typing import List
from urllib.parse import urlsplit

import shortuuid
from install_playwright import install
from markdownify import markdownify as md
from pydantic import BaseModel, Field

from playwright.async_api import async_playwright
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


class WebScrapingCompleted(BaseModel):
    id: str = Field(..., title="ID of the request")
    links: List[MediaLink] = Field(..., title="URL to scrape")


class PlaywrightScraperAgent(Agent):
    def __init__(self, agent_spec: AgentSpec):
        super().__init__(agent_spec=agent_spec)

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
                url = link.url

                response = await page.goto(url)

                if response and response.status != 200:
                    ctx.send_error(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type="HTTP_ERROR_{response.status}",
                            error_message=f"HTTP error: {response.status} for URL: {url}. Error message: {response.status_text}",
                        )
                    )
                    continue

                title = await page.title()
                content = await page.content()
                urls = urlsplit(url)
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
                metadata = meta | {"scraped_url": url, "title": title, "request_id": scraping_request.id}

                output = MediaLink(
                    url=f"scraped_data/{filename}",
                    name=filename,
                    metadata=metadata,
                    on_filesystem=True,
                    mimetype=mimetype,
                    encoding="utf-8",
                )

                scraped_docs.append(output)
                ctx.send(output)

            await browser.close()

            unique_scraped_docs = list({doc.name: doc for doc in scraped_docs}.values())

            ctx.send(WebScrapingCompleted(id=scraping_request.id, links=unique_scraped_docs))
