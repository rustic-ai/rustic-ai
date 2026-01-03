import asyncio
from datetime import datetime
from enum import StrEnum
import hashlib
import logging
import mimetypes
import os
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse, urlsplit

from install_playwright import install
from markdownify import markdownify as md
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright
from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import FileSystem
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.json_utils import JsonDict


class ScrapingOutputFormat(StrEnum):
    TEXT_HTML = "text/html"
    MARKDOWN = "text/markdown"


class BrowserLifecycle(StrEnum):
    PER_REQUEST = "per_request"      # Close after each request
    IDLE_TIMEOUT = "idle_timeout"    # Close after idle period (use browser_idle_timeout_s)
    PERSISTENT = "persistent"        # Keep alive until agent shutdown


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


class PlaywrightScraperConfig(BaseAgentProps):
    headless: bool = Field(
        default=True,
        title="Run browser in headless mode",
        description="If True, the browser will run in headless mode (no GUI).",
    )
    parallel_pages: int = Field(
        default=5,
        title="Number of parallel pages to scrape",
        description="The number of pages to scrape in parallel.",
    )
    browser_lifecycle: BrowserLifecycle = Field(
        default=BrowserLifecycle.PERSISTENT,
        title="Browser lifecycle strategy",
        description=(
            "Strategy for managing browser lifecycle: "
            "PER_REQUEST - close after each request, "
            "IDLE_TIMEOUT - close after idle period, "
            "PERSISTENT - keep alive until shutdown."
        ),
    )
    browser_idle_timeout_s: float = Field(
        default=10.0,
        title="Browser idle close timeout (seconds)",
        description="How long to wait before closing browser when using IDLE_TIMEOUT lifecycle strategy.",
        ge=0.0,
    )


class PlaywrightScraperAgent(Agent[PlaywrightScraperConfig]):
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._browser_lock = asyncio.Lock()
        self._scraped_urls_lock = asyncio.Lock()
        self._scraped_urls: Set[str] = set()
        self._initialized = False
        self._chromium_installed = False
        # Shared-browser lifecycle management
        self._active_ops: int = 0

    async def _ensure_browser(self, force: bool = False):
        """Ensure browser is initialized and running."""
        async with self._browser_lock:
            if force or not self._initialized or self._browser is None or not self._browser.is_connected():
                await self._initialize_browser()
            return self._browser

    async def _initialize_browser(self):
        """Initialize or reinitialize the browser."""
        try:
            # Close existing browser if any
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass

            # Close existing playwright if any
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass

            # Start new playwright and browser
            self._playwright = await async_playwright().start()

            # Install chromium if needed (only check once)
            if not self._chromium_installed:
                logging.info("Checking if Chromium is installed...")
                if install(self._playwright.chromium):
                    logging.info("Chromium installation check completed")
                    self._chromium_installed = True
                else:
                    raise RuntimeError("Failed to install Chromium browser")

            # Launch browser
            self._browser = await self._playwright.chromium.launch(headless=self.config.headless)
            self._initialized = True

            logging.info("Browser initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize browser: {e}")
            raise

    async def _extract_links(self, page, base_url: str, request: WebScrapingRequest) -> List[str]:
        """Extract valid links from a page."""
        try:
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
        except Exception as e:
            logging.error(f"Error extracting links from {base_url}: {e}")
            return []

    async def _scrape_page(
        self,
        url: str,
        context: BrowserContext,
        request: WebScrapingRequest,
        ctx: agent.ProcessContext,
        filesystem: FileSystem,
        semaphore: asyncio.Semaphore,
    ):
        """Scrape a single page and return the MediaLink and extracted links."""
        page = None
        try:
            async with semaphore:  # Limit concurrent pages
                page = await context.new_page()
                page.set_default_timeout(30000)  # 30 seconds

                response = await page.goto(url, wait_until="domcontentloaded")

                if not response:
                    logging.error(f"No response received for URL: {url}")
                    return None, []

                if response.status >= 400:
                    ctx.send_error(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type=f"HTTP_ERROR_{response.status}",
                            error_message=f"HTTP error: {response.status} for URL: {url}",
                        )
                    )
                    return None, []

                # Extract content
                title = await page.title()
                content = await page.content()

                # Extract links for recursive scraping
                links = await self._extract_links(page, url, request) if request.depth > 0 else []

                # Process content
                urls = urlsplit(url)
                upath = urls.path
                basename = os.path.basename(upath)
                _, filetype = os.path.splitext(basename)

                if not filetype and request.output_format == ScrapingOutputFormat.TEXT_HTML:
                    filetype = ".html"
                elif request.output_format == ScrapingOutputFormat.MARKDOWN:
                    filetype = ".md"
                elif not filetype:
                    filetype = ".txt"

                filename = hashlib.md5(content.encode("utf-8")).hexdigest() + filetype
                mimetype = mimetypes.guess_type(filename)[0]

                if request.output_format == ScrapingOutputFormat.MARKDOWN:
                    content = md(content, **request.transformer_options)

                # Save to filesystem
                with filesystem.open(f"scraped_data/{filename}", "w") as f:
                    f.write(content)

                hostname = urlparse(response.url).hostname

                metadata = {
                    "scraped_url": url,
                    "title": title,
                    "request_id": request.id,
                    "source_system": f"internet:{hostname}" if hostname else "internet",
                    "was_derived_from": response.url,
                    "was_generated_by": "playwright_scraper_agent",
                    "description": f"Web page scraped from {url}",
                    "tags": ["web", "scraped", hostname] if hostname else ["web", "scraped"],
                    "was_retrieved_at": str(datetime.utcnow()),
                    "created_at": response.headers.get("last-modified", str(datetime.utcnow())),
                    "source_etag": response.headers.get("etag", ""),
                    "source_uri": response.url,
                }

                output = MediaLink(
                    url=f"file:///scraped_data/{filename}",
                    name=filename,
                    metadata=metadata,
                    on_filesystem=True,
                    mimetype=mimetype,
                    encoding="utf-8",
                )

                return output, links

        except asyncio.TimeoutError:
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="TIMEOUT_ERROR",
                    error_message=f"Timeout while scraping URL: {url}",
                )
            )
            return None, []
        except Exception as e:
            logging.error(f"Error scraping {url}: {e}")
            ctx.send_error(
                ErrorMessage(
                    agent_type=self.get_qualified_class_name(),
                    error_type="SCRAPE_ERROR",
                    error_message=f"Error scraping URL {url}: {str(e)}",
                )
            )
            return None, []
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _scrape_url_with_depth(
        self,
        url: str,
        depth: int,
        context: BrowserContext,
        request: WebScrapingRequest,
        ctx: agent.ProcessContext,
        filesystem: FileSystem,
        semaphore: asyncio.Semaphore,
        scraped_docs: List[MediaLink],
    ):
        """Scrape a URL and recursively scrape its links up to the specified depth."""
        # Check if already scraped
        async with self._scraped_urls_lock:
            if url in self._scraped_urls and not request.force:
                return
            self._scraped_urls.add(url)

        # Skip certain file types
        if url.endswith((".zip", ".pdf", ".doc", ".docx", ".xls", ".xlsx")):
            return

        # Scrape the page
        result, links = await self._scrape_page(url, context, request, ctx, filesystem, semaphore)
        if result:
            scraped_docs.append(result)
            ctx.send(result)

            # Recursively scrape links if depth > 0
            if depth > 0 and links:
                tasks = []
                for link in links:
                    task = self._scrape_url_with_depth(
                        link, depth - 1, context, request, ctx, filesystem, semaphore, scraped_docs
                    )
                    tasks.append(task)

                # Process in batches
                batch_size = self.config.parallel_pages
                for i in range(0, len(tasks), batch_size):
                    batch = tasks[i : i + batch_size]
                    await asyncio.gather(*batch, return_exceptions=True)

    @agent.processor(
        WebScrapingRequest, depends_on=[agent.AgentDependency(dependency_key="filesystem", guild_level=True)]
    )
    async def scrape(self, ctx: agent.ProcessContext[WebScrapingRequest], filesystem: FileSystem) -> None:
        """Main entry point for scraping requests."""
        # Clear previous state
        async with self._scraped_urls_lock:
            self._scraped_urls.clear()

        # Ensure browser is running; mark operation active and cancel idle close
        self._active_ops += 1
        browser = await self._ensure_browser()

        # Create a new context for this scraping session
        try:
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
        except Exception as e:
            # Check for specific error indicating browser connection loss
            # "WriteUnixTransport closed" or "handler is closed"
            if "closed" in str(e) or "transport" in str(e):
                logging.warning(f"Browser context creation failed, re-initializing browser: {e}")
                browser = await self._ensure_browser(force=True)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
            else:
                raise

        try:
            scraping_request = ctx.payload
            scraped_docs: List[MediaLink] = []
            semaphore = asyncio.Semaphore(self.config.parallel_pages)

            # Create tasks for all initial URLs
            tasks = []
            for link in scraping_request.links:
                task = self._scrape_url_with_depth(
                    link.url,
                    scraping_request.depth,
                    context,
                    scraping_request,
                    ctx,
                    filesystem,
                    semaphore,
                    scraped_docs,
                )
                tasks.append(task)

            # Execute all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    url = scraping_request.links[i].url
                    ctx.send_error(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type="SCRAPE_ENTRY_ERROR",
                            error_message=f"Error scraping entry URL {url}: {str(result)}",
                        )
                    )

            # Get unique documents
            unique_scraped_docs = list({doc.name: doc for doc in scraped_docs}.values())

            # Send completion message
            ctx.send(WebScrapingCompleted(id=scraping_request.id, links=unique_scraped_docs))

        finally:
            # Always close the context
            await context.close()
            self._active_ops -= 1

            # Handle browser lifecycle based on configuration
            if self.config.browser_lifecycle == BrowserLifecycle.PER_REQUEST:
                await self._cleanup()
            elif self.config.browser_lifecycle == BrowserLifecycle.IDLE_TIMEOUT:
                await asyncio.sleep(self.config.browser_idle_timeout_s)
                if self._active_ops == 0:
                    await self._cleanup()
            # PERSISTENT: do nothing, browser stays alive

    async def _cleanup(self):
        """Cleanup method to free up resources."""
        async with self._browser_lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            self._initialized = False
