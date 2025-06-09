import asyncio
from enum import StrEnum
import hashlib
import logging
import mimetypes
import os
from typing import List, Set
from urllib.parse import urljoin, urlparse, urlsplit

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

    depth: int = Field(
        default=0,
        title="Depth of recursive link scraping",
        description="If 0, only scrape the input page. If 1, also scrape all links on the page. If 2, recurse into those links, and so on.",
    )

    scrape_external_links: bool = Field(
        default=False,
        title="Scrape external links",
        description="If True, allows scraping of links pointing to domains outside the initial one.",
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

    async def _extract_links(self, page, base_url: str, request: WebScrapingRequest) -> List[str]:
        raw_links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        seen = set()
        valid_links = []
        for link in raw_links:
            parsed = urlparse(link)
            if parsed.scheme == "mailto":
                continue
            full_url = link if parsed.scheme and parsed.netloc else urljoin(base_url, link)
            if not request.scrape_external_links and urlparse(base_url).netloc != urlparse(full_url).netloc:
                continue
            if full_url not in seen:
                seen.add(full_url)
                valid_links.append(full_url)
        return valid_links

    async def scrape_and_store(self, current_link, browser, scraping_request, ctx, scraped_docs, filesystem):
        if current_link.url in self.scraped_urls and not scraping_request.force:
            return

        page = await browser.new_page()
        response = await page.goto(current_link.url)

        if response and response.status != 200:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type=f"HTTP_ERROR_{response.status}",
                    error_message=f"HTTP error: {response.status} for URL: {current_link.url}. Error message: {response.status_text}",
                )
            )
            return

        try:
            title = await page.title()
            content = await page.content()
            urls = urlsplit(current_link.url)
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

            if scraping_request.output_format == ScrapingOutputFormat.MARKDOWN:
                content = md(
                    content,
                    **scraping_request.transformer_options,
                )
            with filesystem.open(f"scraped_data/{filename}", "w") as f:
                f.write(content)

            meta = current_link.metadata or {}
            metadata = meta | {"scraped_url": current_link.url, "title": title, "request_id": scraping_request.id}

            output = MediaLink(
                url=f"scraped_data/{filename}",
                name=filename,
                metadata=metadata,
                on_filesystem=True,
                mimetype=mimetype,
                encoding="utf-8",
            )

            scraped_docs.append(output)
            self.scraped_urls.add(current_link.url)
            ctx.send(output)

        except Exception as e:
            logging.error(f"Error writing file: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="FileWriteError",
                    error_message=str(e),
                )
            )

        return page

    async def _scrape_recursive(self, url: str, depth: int, browser, request, ctx, scraped_docs, filesystem):
        if url in self.scraped_urls and not request.force:
            return

        if url.endswith(".zip"):
            return

        page = await self.scrape_and_store(MediaLink(url=url), browser, request, ctx, scraped_docs, filesystem)
        if not page or depth == 0:
            return

        try:
            links = await self._extract_links(page, url, request)
            for link in links:
                await self._scrape_recursive(link, depth - 1, browser, request, ctx, scraped_docs, filesystem)
        except Exception as e:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SCRAPE_RECURSION_ERROR",
                    error_message=f"Failed to recurse into links on {url}: {str(e)}",
                )
            )
        finally:
            await page.close()

    @agent.processor(
        WebScrapingRequest, depends_on=[agent.AgentDependency(dependency_key="filesystem", guild_level=True)]
    )
    async def scrape(self, ctx: agent.ProcessContext[WebScrapingRequest], filesystem: FileSystem) -> None:
        async with async_playwright() as p:
            install(p.chromium)
            browser = await p.chromium.launch()
            scraping_request = ctx.payload
            scraped_docs: List[MediaLink] = []

            for link in scraping_request.links:
                try:
                    await self._scrape_recursive(
                        link.url, scraping_request.depth, browser, scraping_request, ctx, scraped_docs, filesystem
                    )
                except Exception as e:
                    ctx.send_error(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type="SCRAPE_ENTRY_ERROR",
                            error_message=f"Error scraping entry URL {link.url}: {str(e)}",
                        )
                    )

            await browser.close()
            await asyncio.sleep(0.1)

            unique_scraped_docs = list({doc.name: doc for doc in scraped_docs}.values())

            ctx.send(WebScrapingCompleted(id=scraping_request.id, links=unique_scraped_docs))
