import asyncio
from concurrent.futures import Future
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import mimetypes
import os
import threading
from typing import Any, List, Optional, Set, TypeVar
from urllib.parse import urljoin, urlparse, urlsplit

from install_playwright import install
from markdownify import markdownify as md
from playwright.async_api import Browser, BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Playwright, async_playwright
from pydantic import BaseModel, Field
import shortuuid

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import FileSystem
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.utils.json_utils import JsonDict

T = TypeVar("T")


class ScrapingOutputFormat(StrEnum):
    TEXT_HTML = "text/html"
    MARKDOWN = "text/markdown"


class BrowserLifecycle(StrEnum):
    PER_REQUEST = "per_request"  # Close after each request
    IDLE_TIMEOUT = "idle_timeout"  # Close after idle period (use browser_idle_timeout_s)
    PERSISTENT = "persistent"  # Keep alive until agent shutdown


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


class PlaywrightEventLoopThread:
    """
    A dedicated thread with its own asyncio event loop for running playwright operations.
    This ensures all playwright operations run in the same event loop context.
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._lock = threading.Lock()

    def start(self):
        """Start the event loop thread if not already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._started.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._started.wait(timeout=10.0)

    def _run_loop(self):
        """Run the event loop in this thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def run_coroutine(self, coro) -> Any:
        """
        Run a coroutine in the dedicated event loop thread and wait for the result.
        This method is thread-safe and can be called from any thread.
        """
        if self._loop is None or not self._thread or not self._thread.is_alive():
            self.start()

        if self._loop is None:
            raise RuntimeError("Playwright event loop failed to start")

        future: Future = Future()

        def callback():
            try:
                task = asyncio.ensure_future(coro, loop=self._loop)

                def done_callback(t):
                    try:
                        if t.exception():
                            future.set_exception(t.exception())
                        else:
                            future.set_result(t.result())
                    except asyncio.CancelledError:
                        future.set_exception(asyncio.CancelledError())

                task.add_done_callback(done_callback)
            except Exception as e:
                future.set_exception(e)

        self._loop.call_soon_threadsafe(callback)
        return future.result(timeout=120.0)  # 2 minute timeout

    def stop(self):
        """Stop the event loop and thread."""
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5.0)
                self._thread = None
                self._loop = None


# Global event loop thread for playwright operations
_playwright_loop_thread: Optional[PlaywrightEventLoopThread] = None
_playwright_loop_lock = threading.Lock()


def get_playwright_loop_thread() -> PlaywrightEventLoopThread:
    """Get or create the global playwright event loop thread."""
    global _playwright_loop_thread
    with _playwright_loop_lock:
        if _playwright_loop_thread is None:
            _playwright_loop_thread = PlaywrightEventLoopThread()
            _playwright_loop_thread.start()
        return _playwright_loop_thread


class PlaywrightScraperAgent(Agent[PlaywrightScraperConfig]):
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._browser_lock = asyncio.Lock()
        self._scraped_urls_lock = asyncio.Lock()
        self._scraped_urls: Set[str] = set()
        self._initialized = False
        self._chromium_installed = False
        self._active_ops: int = 0
        self._loop_thread = get_playwright_loop_thread()

    def _run_in_playwright_loop(self, coro):
        """Run a coroutine in the playwright event loop thread."""
        return self._loop_thread.run_coroutine(coro)

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
                self.logger.info("Checking if Chromium is installed...")
                if install([self._playwright.chromium]):
                    self.logger.info("Chromium installation check completed")
                    self._chromium_installed = True
                else:
                    raise RuntimeError("Failed to install Chromium browser")

            # Launch browser
            self._browser = await self._playwright.chromium.launch(headless=self.config.headless)
            self._initialized = True

            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {e}")
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
            self.logger.error(f"Error extracting links from {base_url}: {e}")
            return []

    async def _scrape_page(
        self,
        url: str,
        context: BrowserContext,
        request: WebScrapingRequest,
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
                    self.logger.error(f"No response received for URL: {url}")
                    return None, [], None

                if response.status >= 400:
                    error = ErrorMessage(
                        agent_type=self.get_qualified_class_name(),
                        error_type=f"HTTP_ERROR_{response.status}",
                        error_message=f"HTTP error: {response.status} for URL: {url}",
                    )
                    return None, [], error

                # Extract content. A page can still be mid-navigation (e.g. a client-side
                # redirect firing right after "domcontentloaded") when we read it, which makes
                # page.content() raise transiently; wait for the page to settle and retry once.
                try:
                    title = await page.title()
                    content = await page.content()
                except PlaywrightError as e:
                    if "navigating and changing the content" not in str(e):
                        raise
                    await page.wait_for_load_state("load")
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

                # Save to filesystem. When the filesystem dependency is configured with
                # asynchronous=True (e.g. AsyncFileSystemWrapper-backed), its sync bridge
                # loop is None by design and calling the sync method raises
                # "Loop is not running" -- the async method must be awaited directly instead.
                if getattr(filesystem, "asynchronous", False):
                    await filesystem._pipe_file(f"scraped_data/{filename}", content.encode("utf-8"))
                else:
                    filesystem.pipe_file(f"scraped_data/{filename}", content.encode("utf-8"))

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
                    "was_retrieved_at": str(datetime.now(timezone.utc)),
                    "created_at": response.headers.get("last-modified", str(datetime.now(timezone.utc))),
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

                return output, links, None

        except asyncio.TimeoutError:
            error = ErrorMessage(
                agent_type=self.get_qualified_class_name(),
                error_type="TIMEOUT_ERROR",
                error_message=f"Timeout while scraping URL: {url}",
            )
            return None, [], error
        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            error = ErrorMessage(
                agent_type=self.get_qualified_class_name(),
                error_type="SCRAPE_ERROR",
                error_message=f"Error scraping URL {url}: {str(e)}",
            )
            return None, [], error
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
        filesystem: FileSystem,
        semaphore: asyncio.Semaphore,
        scraped_docs: List[MediaLink],
        errors: List[ErrorMessage],
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
        result, links, error = await self._scrape_page(url, context, request, filesystem, semaphore)
        if error:
            errors.append(error)
        if result:
            scraped_docs.append(result)

            # Recursively scrape links if depth > 0
            if depth > 0 and links:
                tasks = []
                for link in links:
                    task = self._scrape_url_with_depth(
                        link, depth - 1, context, request, filesystem, semaphore, scraped_docs, errors
                    )
                    tasks.append(task)

                # Process in batches
                batch_size = self.config.parallel_pages
                for i in range(0, len(tasks), batch_size):
                    batch = tasks[i : i + batch_size]
                    await asyncio.gather(*batch, return_exceptions=True)

    async def _do_scrape(
        self,
        scraping_request: WebScrapingRequest,
        filesystem: FileSystem,
    ) -> tuple[List[MediaLink], List[ErrorMessage]]:
        """
        Internal async method that performs the actual scraping.
        This runs in the playwright event loop thread.
        """
        # Clear previous state
        async with self._scraped_urls_lock:
            self._scraped_urls.clear()

        # Ensure browser is running
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
            if "closed" in str(e).lower() or "transport" in str(e).lower():
                self.logger.warning(f"Browser context creation failed, re-initializing browser: {e}")
                browser = await self._ensure_browser(force=True)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
            else:
                raise

        scraped_docs: List[MediaLink] = []
        errors: List[ErrorMessage] = []
        semaphore = asyncio.Semaphore(self.config.parallel_pages)

        try:
            self.logger.debug(f"Starting scraping for request: {scraping_request.id}")

            # Create tasks for all initial URLs
            tasks = []
            for link in scraping_request.links:
                task = self._scrape_url_with_depth(
                    link.url,
                    scraping_request.depth,
                    context,
                    scraping_request,
                    filesystem,
                    semaphore,
                    scraped_docs,
                    errors,
                )
                tasks.append(task)

            # Execute all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    url = scraping_request.links[i].url
                    errors.append(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type="SCRAPE_ENTRY_ERROR",
                            error_message=f"Error scraping entry URL {url}: {str(result)}",
                        )
                    )

            self.logger.debug(f"Scraping completed for request: {scraping_request.id}. Total unique documents scraped: {len(scraped_docs)}")

            return scraped_docs, errors

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

    @agent.processor(
        WebScrapingRequest, depends_on=[agent.AgentDependency(dependency_key="filesystem", guild_level=True)]
    )
    def scrape(self, ctx: agent.ProcessContext[WebScrapingRequest], filesystem: FileSystem) -> None:
        """Main entry point for scraping requests."""
        scraping_request = ctx.payload

        # Run the actual scraping in the playwright event loop thread
        scraped_docs, errors = self._run_in_playwright_loop(
            self._do_scrape(scraping_request, filesystem)
        )

        # Send results back through the context (must be done in calling context)
        for doc in scraped_docs:
            ctx.send(doc)

        for error in errors:
            ctx.send_error(error)

        # Get unique documents and send completion message
        unique_scraped_docs = list({doc.name: doc for doc in scraped_docs}.values())
        ctx.send(WebScrapingCompleted(id=scraping_request.id, links=unique_scraped_docs))

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
