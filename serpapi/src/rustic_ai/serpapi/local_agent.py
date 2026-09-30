"""
LocalSERPAgent: web search without an API key, by driving a real browser on the user's own machine.

A drop-in replacement for `SERPAgent` (same `SERPQuery` / `SERPResults` / `SearchError` messages) for guilds that run
locally: searches come from the user's own IP, installed Chrome and a persistent browser profile, just like ordinary
browsing. Use `SERPAgent` on shared or hosted infrastructure.

Modes (the `headless` property):

- `headless=True` (default): an invisible browser. Engines, Google especially, challenge headless browsers more often.
- `headless=False`: a real Chrome window kept minimized. Engines trust it more, and when one shows a CAPTCHA the window
  is brought forward so the user can solve it (`captcha_wait_s`). Falls back to headless when there is no display.

When a search cannot be completed, the agent sends a `SearchError` whose `response` holds `engine`, `reason` (see
`SearchFailureReason`) and a human-readable `error`; retrying on another engine is left to the guild.

Run `python -m rustic_ai.serpapi.local_setup` once to accept consent pages / solve a CAPTCHA / sign in on the profile.
"""

import asyncio
from enum import StrEnum
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from install_playwright import install
from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from pydantic import Field, model_validator

from rustic_ai.core.guild import Agent, agent
from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.playwright.agent import get_playwright_loop_thread
from rustic_ai.serpapi.agent import (
    SearchError,
    SERPQuery,
    SERPResults,
    build_result_link,
)
from rustic_ai.serpapi.local_browser import (
    is_channel_missing,
    is_display_missing,
    is_profile_locked,
    launch_args,
    resolve_profile_dir,
    set_window_state,
)
from rustic_ai.serpapi.local_engines import (
    ENGINES,
    BlockReason,
    LocalSearchEngine,
    RawResult,
)

# Extra time the caller waits beyond the search's own deadline, so the search can cancel itself cleanly first.
_DEADLINE_SLACK_S = 15.0


class SearchFailureReason(StrEnum):
    CAPTCHA = BlockReason.CAPTCHA.value  # the engine showed a bot check
    CONSENT = BlockReason.CONSENT.value  # the engine showed a consent wall that could not be dismissed
    TIMEOUT = "timeout"  # a page load or the whole search took too long
    UNSUPPORTED_ENGINE = "unsupported_engine"
    BROWSER_ERROR = "browser_error"  # the browser failed to launch or navigate


class LocalSearchFailure(Exception):
    def __init__(self, reason: SearchFailureReason, message: str):
        super().__init__(message)
        self.reason = reason


class LocalSERPConfig(BaseAgentProps):
    headless: bool = Field(
        default=True,
        description=(
            "True: invisible headless browser. False: real Chrome window, kept minimized (hide_window), that engines "
            "trust more and that is shown to the user when a CAPTCHA needs solving."
        ),
    )
    hide_window: bool = Field(
        default=True,
        description="Headed mode: keep the window minimized except while the user must solve a CAPTCHA.",
    )
    captcha_wait_s: float = Field(
        default=120.0,
        ge=0.0,
        description="Headed mode: seconds to wait for the user to solve a CAPTCHA or consent page; 0 disables waiting.",
    )
    browser_channel: Optional[str] = Field(
        default="chrome",
        description="Playwright channel: 'chrome' uses the installed Google Chrome; None uses bundled Chromium.",
    )
    user_data_dir: Optional[str] = Field(
        default=None,
        description="Persistent browser profile root. Defaults to ~/.rustic_ai/local_serp/profile.",
    )
    hl: str = Field(default="en", description="Interface language.")
    gl: str = Field(default="us", description="Country / region.")
    min_delay_s: float = Field(default=1.0, ge=0.0, description="Minimum pause between result pages.")
    max_delay_s: float = Field(default=3.0, ge=0.0, description="Maximum pause between result pages.")
    max_pages: int = Field(default=5, ge=1, description="Maximum result pages fetched per search.")
    navigation_timeout_s: float = Field(default=30.0, gt=0.0, description="Timeout for a single page load.")
    search_timeout_s: float = Field(
        default=120.0,
        gt=0.0,
        description="Timeout for a whole search, not counting time spent waiting for the user to solve a CAPTCHA.",
    )
    close_browser_after_request: bool = Field(
        default=False, description="Close the browser after every search instead of keeping it open."
    )

    @model_validator(mode="after")
    def _check_delays(self):
        if self.max_delay_s < self.min_delay_s:
            raise ValueError("max_delay_s must be >= min_delay_s")
        return self


class LocalSERPAgent(Agent[LocalSERPConfig]):
    # Seconds between checks while waiting for the user to solve a CAPTCHA.
    _user_poll_s: float = 1.0

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._user_agent: Optional[str] = None
        self._private_profile = False
        self._force_headless = False
        self._asked_user = False
        self._search_lock = asyncio.Lock()
        self._loop_thread = get_playwright_loop_thread()

    @agent.processor(SERPQuery)
    def search(self, ctx: agent.ProcessContext[SERPQuery]) -> None:
        query = ctx.payload
        self.logger.debug(f"Received local search query: {query.query} for engine: {query.engine}")

        try:
            if query.engine not in ENGINES:
                raise LocalSearchFailure(
                    SearchFailureReason.UNSUPPORTED_ENGINE,
                    f"Engine '{query.engine}' is not supported; use one of {', '.join(sorted(ENGINES))}",
                )
            results, total_results = self._loop_thread.run_coroutine(
                self._search_with_deadline(query), timeout=self._deadline_s() + _DEADLINE_SLACK_S
            )
        except Exception as e:
            failure = self._as_failure(e)
            self.logger.warning(f"Local search on {query.engine} failed ({failure.reason.value}): {failure}")
            ctx.send(
                SearchError(
                    id=query.id,
                    response={
                        "status": "Error",
                        "engine": query.engine,
                        "reason": failure.reason.value,
                        "error": str(failure),
                    },
                )
            )
            return

        offset = query.start or 0
        links = [
            build_result_link(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                position=offset + i + 1,
                query_id=query.id,
                date=result.date,
                extra_metadata={"engine": query.engine, "source": "local_browser"},
            )
            for i, result in enumerate(results)
        ]
        self.logger.debug(f"Publishing {len(links)} local search results for query: {query.query}")
        ctx.send(
            SERPResults(
                count=len(links),
                results=links,
                total_results=total_results,
                id=query.id,
                query=query.query,
                engine=query.engine,
            ),
            new_thread=True,
        )

    @staticmethod
    def _as_failure(error: BaseException) -> LocalSearchFailure:
        if isinstance(error, LocalSearchFailure):
            return error
        if isinstance(error, (PlaywrightTimeoutError, TimeoutError)):
            return LocalSearchFailure(SearchFailureReason.TIMEOUT, "The search timed out")
        return LocalSearchFailure(SearchFailureReason.BROWSER_ERROR, str(error) or repr(error))

    # ------------------------------------------------------------------ search

    @property
    def _headless(self) -> bool:
        return self.config.headless or self._force_headless

    def _deadline_s(self) -> float:
        user_wait = 0.0 if self.config.headless else self.config.captcha_wait_s
        return self.config.search_timeout_s + user_wait

    async def _search_with_deadline(self, query: SERPQuery) -> Tuple[List[RawResult], Optional[int]]:
        async with self._search_lock:
            self._asked_user = False
            try:
                return await asyncio.wait_for(self._search(ENGINES[query.engine], query), self._deadline_s())
            finally:
                if self.config.close_browser_after_request:
                    await self._cleanup()

    async def _search(self, engine: LocalSearchEngine, query: SERPQuery) -> Tuple[List[RawResult], Optional[int]]:
        """Collect `query.num` results starting at `query.start`, paginating as needed."""
        page = await self._ensure_page()
        offset = query.start or 0
        wanted = query.num or engine.page_size
        # Click-paginated engines always start from page one, so collect `offset` extra results and drop them.
        skip = offset if engine.paginate_by_click else 0
        needed = skip + wanted

        collected: List[RawResult] = []
        seen: set = set()
        total: Optional[int] = None
        pages = 0
        retried_next = False

        first_url = engine.search_url(
            query.query, 0 if engine.paginate_by_click else offset, self.config.hl, self.config.gl
        )
        html, url = await self._fetch(page, first_url, engine)

        while True:
            parsed = engine.parse(html, url)
            if parsed.block_reason is not None:
                solved = await self._wait_for_user(page, engine, parsed.block_reason)
                if solved is not None:
                    html, url = solved
                    continue
                if collected:
                    self.logger.info(f"{engine.name} blocked after {pages} page(s); returning the results so far")
                    break
                raise LocalSearchFailure(
                    SearchFailureReason(parsed.block_reason.value),
                    f"{engine.name} showed a {parsed.block_reason.value} page",
                )

            pages += 1
            if total is None:
                total = parsed.total_results

            page_results = await self._resolve_links(parsed.results[: needed - len(collected)])
            new_results = [r for r in page_results if r.url not in seen]
            for result in new_results:
                seen.add(result.url)
                collected.append(result)

            if len(collected) >= needed or pages >= self.config.max_pages:
                break
            if not new_results:
                # Bing's first "Next" click in a fresh session goes through a cookie-setting redirect that serves page
                # one again; clicking once more reaches the real next page. Other engines have simply run out.
                if not (engine.paginate_by_click and pages > 1) or retried_next:
                    break
                retried_next = True

            await asyncio.sleep(random.uniform(self.config.min_delay_s, self.config.max_delay_s))

            if engine.paginate_by_click:
                next_page = await self._next_page(page, engine)
                if next_page is None:
                    break
                html, url = next_page
            else:
                next_offset = offset + pages * engine.page_size
                html, url = await self._fetch(
                    page, engine.search_url(query.query, next_offset, self.config.hl, self.config.gl), engine
                )

        return collected[skip:needed], total

    async def _wait_for_user(
        self, page: Page, engine: LocalSearchEngine, reason: BlockReason
    ) -> Optional[Tuple[str, str]]:
        """
        Headed mode: show the window and wait for the user to clear a CAPTCHA / consent page.

        Returns the page's (html, url) once it is no longer blocked, or None when waiting is disabled or times out.
        Asks at most once per search so an unattended guild is not stalled repeatedly.
        """
        if self._headless or self.config.captcha_wait_s <= 0 or self._asked_user:
            return None
        self._asked_user = True

        self.logger.warning(
            f"{engine.name} is showing a {reason.value} page. Please complete it in the browser window within "
            f"{self.config.captcha_wait_s:.0f}s; the search will then continue."
        )
        await self._set_window_state(page, minimized=False)
        try:
            deadline = time.monotonic() + self.config.captcha_wait_s
            while time.monotonic() < deadline:
                await asyncio.sleep(self._user_poll_s)
                snapshot = await self._snapshot(page)
                if snapshot is not None and not engine.parse(*snapshot).blocked:
                    self.logger.info(f"{engine.name} {reason.value} page completed; continuing the search")
                    return await self._read_page(page)
            return None
        finally:
            if self.config.hide_window:
                await self._set_window_state(page, minimized=True)

    async def _resolve_links(self, results: List[RawResult]) -> List[RawResult]:
        """Replace engine redirect links with their targets; results whose target cannot be resolved are dropped."""
        pending = [r for r in results if r.needs_resolve]
        if not pending:
            return results
        targets = await asyncio.gather(*(self._resolve_url(r.url) for r in pending), return_exceptions=True)
        target_by_link = {r.url: t for r, t in zip(pending, targets) if isinstance(t, str)}

        resolved = []
        for result in results:
            if not result.needs_resolve:
                resolved.append(result)
            elif result.url in target_by_link:
                resolved.append(
                    RawResult(
                        url=target_by_link[result.url], title=result.title, snippet=result.snippet, date=result.date
                    )
                )
        return resolved

    async def _resolve_url(self, url: str) -> Optional[str]:
        """Request one redirect link with the browser's cookies, without following it, and return its target."""
        assert self._context is not None
        response = await self._context.request.get(
            url, max_redirects=0, timeout=self.config.navigation_timeout_s * 1000
        )
        location = response.headers.get("location")
        target = urljoin(url, location) if location else None
        return target if target and urlparse(target).scheme in ("http", "https") else None

    # ------------------------------------------------------------------ page interaction

    async def _fetch(self, page: Page, url: str, engine: LocalSearchEngine) -> Tuple[str, str]:
        """Navigate to `url`, dismiss any consent banner, and return (html, final_url)."""
        await page.goto(url, wait_until="domcontentloaded")
        await self._dismiss_consent(page, engine)
        return await self._read_page(page)

    async def _next_page(self, page: Page, engine: LocalSearchEngine) -> Optional[Tuple[str, str]]:
        """Click the engine's "next page" control; returns (html, final_url), or None when there is no next page."""
        if not engine.next_page_selector:
            return None
        button = page.locator(engine.next_page_selector).first
        if not await button.count():
            return None
        async with page.expect_navigation(wait_until="domcontentloaded"):
            await button.click()
        return await self._read_page(page)

    async def _dismiss_consent(self, page: Page, engine: LocalSearchEngine) -> None:
        for selector in engine.consent_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() and await button.is_visible():
                    await button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    return
            except PlaywrightError:
                continue

    async def _read_page(self, page: Page) -> Tuple[str, str]:
        try:
            await page.wait_for_load_state("load", timeout=self.config.navigation_timeout_s * 1000)
        except PlaywrightTimeoutError:
            pass  # use whatever has rendered so far
        try:
            html = await page.content()
        except PlaywrightError as e:
            if "navigating and changing the content" not in str(e):
                raise
            await page.wait_for_load_state("load")
            html = await page.content()
        return html, page.url

    async def _snapshot(self, page: Page) -> Optional[Tuple[str, str]]:
        """Current (html, url) without waiting; None while the page is mid-navigation."""
        try:
            return await page.content(), page.url
        except PlaywrightError:
            return None

    async def _set_window_state(self, page: Page, minimized: bool) -> None:
        try:
            await set_window_state(page, minimized)
        except Exception as e:
            self.logger.debug(f"Could not {'minimize' if minimized else 'show'} the browser window: {e}")

    # ------------------------------------------------------------------ browser lifecycle

    async def _ensure_page(self) -> Page:
        """The single long-lived tab searches run in (closing the last tab of a headed browser would quit it)."""
        context = await self._ensure_context()
        if self._page is None or self._page.is_closed():
            self._page = context.pages[0] if context.pages else await context.new_page()
            self._page.set_default_timeout(self.config.navigation_timeout_s * 1000)
            if not self._headless and self.config.hide_window:
                await self._set_window_state(self._page, minimized=True)
        return self._page

    async def _ensure_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        channel = self.config.browser_channel
        try:
            context = await self._launch(channel)
        except PlaywrightError as e:
            if not channel or not is_channel_missing(e):
                raise
            self.logger.warning(f"Browser channel '{channel}' is not installed; using bundled Chromium")
            if not install([self._playwright.chromium]):
                raise RuntimeError("Failed to install Chromium") from e
            channel = None
            context = await self._launch(channel)

        if self._headless and self._user_agent is None:
            # Headless Chrome identifies itself as "HeadlessChrome"; relaunch with the marker removed.
            probe = context.pages[0] if context.pages else await context.new_page()
            user_agent = await probe.evaluate("navigator.userAgent")
            if "HeadlessChrome" in user_agent:
                self._user_agent = user_agent.replace("HeadlessChrome", "Chrome")
                await context.close()
                context = await self._launch(channel)

        context.on("close", lambda _: self._forget_browser())
        self._context = context
        self.logger.info(
            f"Local search browser started ({channel or 'chromium'}, {'headless' if self._headless else 'headed'})"
        )
        return context

    async def _launch(self, channel: Optional[str]) -> BrowserContext:
        assert self._playwright is not None
        profile = resolve_profile_dir(self.config.user_data_dir, channel, self.id if self._private_profile else None)
        try:
            return await self._playwright.chromium.launch_persistent_context(profile, **self._launch_kwargs(channel))
        except PlaywrightError as e:
            if not self._headless and is_display_missing(e):
                self.logger.warning("No display available for a headed browser; running headless instead")
                self._force_headless = True
            elif not self._private_profile and is_profile_locked(e):
                # Another browser (e.g. a second LocalSERPAgent) has the shared profile open; use one of our own.
                self.logger.warning("The shared browser profile is in use; using a profile private to this agent")
                self._private_profile = True
            else:
                raise
            return await self._launch(channel)

    def _launch_kwargs(self, channel: Optional[str]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "headless": self._headless,
            "locale": f"{self.config.hl}-{self.config.gl.upper()}",
            "args": launch_args(self._headless, self.config.hide_window),
        }
        if self._headless:
            kwargs["viewport"] = {"width": 1366, "height": 768}
            if self._user_agent:
                kwargs["user_agent"] = self._user_agent
        else:
            kwargs["no_viewport"] = True  # size pages to the real window, as a normal browser does
        if channel:
            kwargs["channel"] = channel
        return kwargs

    def _forget_browser(self) -> None:
        self._context = None
        self._page = None

    async def _cleanup(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
        self._forget_browser()
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
