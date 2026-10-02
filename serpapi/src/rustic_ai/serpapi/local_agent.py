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
import dataclasses
from enum import StrEnum
import random
import time
from typing import List, Optional, Set, Tuple

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
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
from rustic_ai.serpapi.local_browser import BrowserOptions, LocalBrowser, PageContent
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
        self._browser: Optional[LocalBrowser] = None
        self._search_lock = asyncio.Lock()
        self._loop_thread = get_playwright_loop_thread()

    @agent.processor(SERPQuery)
    def search(self, ctx: agent.ProcessContext[SERPQuery]) -> None:
        query = ctx.payload
        self.logger.debug(f"Received local search query: {query.query} for engine: {query.engine}")
        try:
            results, total_results = self._loop_thread.run_coroutine(
                self._run_search(self._engine_for(query), query), timeout=self._deadline_s() + _DEADLINE_SLACK_S
            )
        except Exception as e:
            failure = self._as_failure(e)
            self.logger.warning(f"Local search on {query.engine} failed ({failure.reason.value}): {failure}")
            ctx.send(self._error_message(query, failure))
            return
        ctx.send(self._results_message(query, results, total_results), new_thread=True)

    # ------------------------------------------------------------------ messages

    @staticmethod
    def _engine_for(query: SERPQuery) -> LocalSearchEngine:
        engine = ENGINES.get(query.engine)
        if engine is None:
            raise LocalSearchFailure(
                SearchFailureReason.UNSUPPORTED_ENGINE,
                f"Engine '{query.engine}' is not supported; use one of {', '.join(sorted(ENGINES))}",
            )
        return engine

    @staticmethod
    def _as_failure(error: BaseException) -> LocalSearchFailure:
        if isinstance(error, LocalSearchFailure):
            return error
        if isinstance(error, (PlaywrightTimeoutError, TimeoutError)):
            return LocalSearchFailure(SearchFailureReason.TIMEOUT, "The search timed out")
        return LocalSearchFailure(SearchFailureReason.BROWSER_ERROR, str(error) or repr(error))

    @staticmethod
    def _error_message(query: SERPQuery, failure: LocalSearchFailure) -> SearchError:
        return SearchError(
            id=query.id,
            response={"status": "Error", "engine": query.engine, "reason": failure.reason.value, "error": str(failure)},
        )

    @staticmethod
    def _results_message(query: SERPQuery, results: List[RawResult], total_results: Optional[int]) -> SERPResults:
        first_position = (query.start or 0) + 1
        links = [
            build_result_link(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                position=position,
                query_id=query.id,
                date=result.date,
                extra_metadata={"engine": query.engine, "source": "local_browser"},
            )
            for position, result in enumerate(results, start=first_position)
        ]
        return SERPResults(
            count=len(links),
            results=links,
            total_results=total_results,
            id=query.id,
            query=query.query,
            engine=query.engine,
        )

    # ------------------------------------------------------------------ search

    def _create_browser(self) -> LocalBrowser:
        options = BrowserOptions(
            headless=self.config.headless,
            hide_window=self.config.hide_window,
            channel=self.config.browser_channel,
            user_data_dir=self.config.user_data_dir,
            locale=f"{self.config.hl}-{self.config.gl.upper()}",
            navigation_timeout_s=self.config.navigation_timeout_s,
            private_profile_id=self.id,
            headless_without_display=True,
        )
        return LocalBrowser(options, self.logger)

    def _deadline_s(self) -> float:
        user_wait = 0.0 if self.config.headless else self.config.captcha_wait_s
        return self.config.search_timeout_s + user_wait

    async def _run_search(self, engine: LocalSearchEngine, query: SERPQuery) -> Tuple[List[RawResult], Optional[int]]:
        async with self._search_lock:
            if self._browser is None:
                self._browser = self._create_browser()
            try:
                return await asyncio.wait_for(self._collect(self._browser, engine, query), self._deadline_s())
            finally:
                if self.config.close_browser_after_request:
                    await self._browser.close()

    async def _collect(
        self, browser: LocalBrowser, engine: LocalSearchEngine, query: SERPQuery
    ) -> Tuple[List[RawResult], Optional[int]]:
        """Collect `query.num` results starting at `query.start`, page by page."""
        offset = query.start or 0
        wanted = query.num or engine.page_size
        # Click-paginated engines always open on page one, so the results before `offset` are loaded and dropped.
        first_offset = 0 if engine.paginate_by_click else offset
        skip = offset - first_offset
        needed = skip + wanted

        collected: List[RawResult] = []
        seen: Set[str] = set()
        total_results: Optional[int] = None
        pages_read = 0
        asked_user = retried_next = False

        content: Optional[PageContent] = await browser.goto(
            self._search_url(engine, query, first_offset), engine.consent_selectors
        )
        while content is not None:
            parsed = engine.parse(content.html, content.url)

            if parsed.block_reason is not None:
                if not asked_user:
                    asked_user = True  # at most once per search, so an unattended guild is not stalled repeatedly
                    content = await self._wait_for_user(browser, engine, parsed.block_reason)
                    if content is not None:
                        continue
                if collected:
                    self.logger.info(f"{engine.name} blocked after {pages_read} page(s); returning results so far")
                    break
                reason = parsed.block_reason.value
                raise LocalSearchFailure(SearchFailureReason(reason), f"{engine.name} showed a {reason} page")

            pages_read += 1
            if total_results is None:
                total_results = parsed.total_results

            page_results = await self._resolve_links(browser, parsed.results[: needed - len(collected)])
            new_results = [result for result in page_results if result.url not in seen]
            seen.update(result.url for result in new_results)
            collected.extend(new_results)

            if len(collected) >= needed or pages_read >= self.config.max_pages:
                break
            if not new_results:
                if not (engine.next_may_repeat_page and pages_read > 1) or retried_next:
                    break
                retried_next = True

            await asyncio.sleep(random.uniform(self.config.min_delay_s, self.config.max_delay_s))
            content = await self._next_page(browser, engine, query, first_offset + pages_read * engine.page_size)

        return collected[skip:needed], total_results

    def _search_url(self, engine: LocalSearchEngine, query: SERPQuery, offset: int) -> str:
        return engine.search_url(query.query, offset, self.config.hl, self.config.gl)

    async def _next_page(
        self, browser: LocalBrowser, engine: LocalSearchEngine, query: SERPQuery, offset: int
    ) -> Optional[PageContent]:
        if engine.next_page_selector is not None:
            return await browser.click_next(engine.next_page_selector)
        return await browser.goto(self._search_url(engine, query, offset), engine.consent_selectors)

    async def _wait_for_user(
        self, browser: LocalBrowser, engine: LocalSearchEngine, reason: BlockReason
    ) -> Optional[PageContent]:
        """
        Headed mode: show the window and wait for the user to clear a CAPTCHA / consent page.

        Returns the page once it is no longer blocked, or None when waiting is disabled or the user does not respond.
        """
        if browser.headless or self.config.captcha_wait_s <= 0:
            return None

        self.logger.warning(
            f"{engine.name} is showing a {reason.value} page. Please complete it in the browser window within "
            f"{self.config.captcha_wait_s:.0f}s; the search will then continue."
        )
        await browser.show_window()
        try:
            deadline = time.monotonic() + self.config.captcha_wait_s
            while time.monotonic() < deadline:
                await asyncio.sleep(self._user_poll_s)
                snapshot = await browser.snapshot()
                if snapshot is not None and not engine.parse(snapshot.html, snapshot.url).blocked:
                    self.logger.info(f"{engine.name} {reason.value} page completed; continuing the search")
                    return await browser.read()
            return None
        finally:
            if self.config.hide_window:
                await browser.hide_window()

    @staticmethod
    async def _resolve_links(browser: LocalBrowser, results: List[RawResult]) -> List[RawResult]:
        """Replace engine redirect links with their targets; results whose target cannot be resolved are dropped."""
        pending = [result for result in results if result.needs_resolve]
        if not pending:
            return results
        targets = await asyncio.gather(*(browser.resolve_redirect(r.url) for r in pending), return_exceptions=True)
        target_by_link = {r.url: target for r, target in zip(pending, targets) if isinstance(target, str)}

        resolved = []
        for result in results:
            if not result.needs_resolve:
                resolved.append(result)
            elif result.url in target_by_link:
                resolved.append(dataclasses.replace(result, url=target_by_link[result.url], needs_resolve=False))
        return resolved
