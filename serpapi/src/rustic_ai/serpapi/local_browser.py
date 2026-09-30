"""
A persistent-profile browser session for `LocalSERPAgent` and the `local_setup` CLI.

`LocalBrowser` owns everything browser-specific: launching Chrome (or bundled Chromium) on a persistent profile,
hiding the headless marker, minimizing / showing the window, navigating, and resolving redirect links. It knows
nothing about search engines or messages.
"""

from dataclasses import dataclass
import logging
import os
from typing import Any, Dict, List, NamedTuple, Optional, Sequence
from urllib.parse import urljoin, urlparse

from install_playwright import install
from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

_HEADLESS_VIEWPORT = {"width": 1366, "height": 768}
_SHOWN_WINDOW_BOUNDS = {"left": 80, "top": 80, "width": 1280, "height": 900}

_PROFILE_LOCKED = ("ProcessSingleton", "SingletonLock")
_CHANNEL_MISSING = ("is not found", "Executable doesn't exist", "distribution")
_NO_DISPLAY = ("Missing X server", "$DISPLAY", "headed browser without having a XServer")


def _matches(error: PlaywrightError, markers: Sequence[str]) -> bool:
    return any(marker in str(error) for marker in markers)


def default_profile_root() -> str:
    return os.path.join(os.path.expanduser("~"), ".rustic_ai", "local_serp", "profile")


def resolve_profile_dir(user_data_dir: Optional[str], channel: Optional[str], suffix: Optional[str] = None) -> str:
    """
    Create and return the persistent profile directory for a browser channel.

    Each channel gets its own directory because Chromium refuses a profile written by a newer Chrome.
    """
    name = channel or "chromium"
    if suffix:
        name = f"{name}-{suffix}"
    path = os.path.join(user_data_dir or default_profile_root(), name)
    os.makedirs(path, exist_ok=True)
    return path


class ProfileInUseError(RuntimeError):
    """The persistent profile is already open in another browser."""


class PageContent(NamedTuple):
    html: str
    url: str


@dataclass(frozen=True)
class BrowserOptions:
    headless: bool = True
    # Headed only: start minimized and stay minimized unless show_window() is called.
    hide_window: bool = True
    channel: Optional[str] = "chrome"
    user_data_dir: Optional[str] = None
    locale: str = "en-US"
    navigation_timeout_s: float = 30.0
    # When set, a shared profile already open in another browser falls back to a profile private to this id.
    private_profile_id: Optional[str] = None
    # Headed only: run headless instead of failing when there is no display.
    headless_without_display: bool = False


class LocalBrowser:
    """One persistent-profile browser with a single long-lived tab; launched lazily, relaunched after it closes."""

    def __init__(self, options: BrowserOptions, logger: logging.Logger):
        self._options = options
        self._logger = logger
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._headless = options.headless
        self._channel = options.channel
        self._profile_suffix: Optional[str] = None
        self._profile_dir: Optional[str] = None
        self._user_agent: Optional[str] = None

    @property
    def headless(self) -> bool:
        """Whether the browser runs headless; can become True after launch when there is no display."""
        return self._headless

    @property
    def profile_dir(self) -> Optional[str]:
        """The profile directory in use, once the browser has launched."""
        return self._profile_dir

    # ------------------------------------------------------------------ navigation

    async def goto(self, url: str, consent_selectors: Sequence[str] = ()) -> PageContent:
        """Navigate to `url`, dismiss a consent banner if one of `consent_selectors` is shown, and read the page."""
        page = await self.page()
        await page.goto(url, wait_until="domcontentloaded")
        await self._dismiss_consent(page, consent_selectors)
        return await self.read()

    async def click_next(self, selector: str) -> Optional[PageContent]:
        """Click a "next page" control and read the page it leads to; None when the control is absent."""
        page = await self.page()
        button = page.locator(selector).first
        if not await button.count():
            return None
        async with page.expect_navigation(wait_until="domcontentloaded"):
            await button.click()
        return await self.read()

    async def read(self) -> PageContent:
        """Read the current page once it has loaded (or once the load times out)."""
        page = await self.page()
        try:
            await page.wait_for_load_state("load", timeout=self._options.navigation_timeout_s * 1000)
        except PlaywrightTimeoutError:
            pass  # use whatever has rendered so far
        try:
            html = await page.content()
        except PlaywrightError as e:
            if "navigating and changing the content" not in str(e):
                raise
            await page.wait_for_load_state("load")
            html = await page.content()
        return PageContent(html, page.url)

    async def snapshot(self) -> Optional[PageContent]:
        """The current page without waiting; None while it is mid-navigation."""
        page = await self.page()
        try:
            return PageContent(await page.content(), page.url)
        except PlaywrightError:
            return None

    async def resolve_redirect(self, url: str) -> Optional[str]:
        """Request `url` with the browser's cookies without following it; return the http(s) redirect target."""
        context = await self._ensure_context()
        response = await context.request.get(url, max_redirects=0, timeout=self._options.navigation_timeout_s * 1000)
        location = response.headers.get("location")
        if not location:
            return None
        target = urljoin(url, location)
        return target if urlparse(target).scheme in ("http", "https") else None

    async def new_tab(self, url: str) -> None:
        """Open `url` in an additional tab."""
        context = await self._ensure_context()
        await (await context.new_page()).goto(url, wait_until="domcontentloaded")

    async def wait_until_closed(self) -> None:
        """Wait until the user closes the browser."""
        context = await self._ensure_context()
        await context.wait_for_event("close", timeout=0)

    # ------------------------------------------------------------------ window

    async def show_window(self) -> None:
        await self._set_window_state(minimized=False)

    async def hide_window(self) -> None:
        await self._set_window_state(minimized=True)

    async def _set_window_state(self, minimized: bool) -> None:
        """Minimize or restore the window over CDP; works on X11, Wayland, macOS and Windows. Best effort."""
        page = await self.page()
        try:
            cdp = await page.context.new_cdp_session(page)
            try:
                window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
                state = "minimized" if minimized else "normal"
                await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": state}})
                if not minimized:
                    # Bounds can only change in the normal state; bring the window back on screen where allowed.
                    await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": _SHOWN_WINDOW_BOUNDS})
                    await page.bring_to_front()
            finally:
                await cdp.detach()
        except PlaywrightError as e:
            self._logger.debug(f"Could not {'minimize' if minimized else 'show'} the browser window: {e}")

    # ------------------------------------------------------------------ lifecycle

    async def page(self) -> Page:
        """The single long-lived tab (closing the last tab of a headed browser would quit it)."""
        context = await self._ensure_context()
        if self._page is None or self._page.is_closed():
            self._page = context.pages[0] if context.pages else await context.new_page()
            self._page.set_default_timeout(self._options.navigation_timeout_s * 1000)
            if not self._headless and self._options.hide_window:
                await self.hide_window()
        return self._page

    async def close(self) -> None:
        """Close the browser; the next call that needs it launches it again."""
        context, playwright = self._context, self._playwright
        self._forget_context()
        self._playwright = None
        try:
            if context is not None:
                await context.close()
            if playwright is not None:
                await playwright.stop()
        except PlaywrightError as e:
            self._logger.debug(f"Error while closing the browser: {e}")

    async def _ensure_context(self) -> BrowserContext:
        if self._context is None:
            self._context = await self._launch()
            self._context.on("close", lambda _: self._forget_context())
            mode = "headless" if self._headless else "headed"
            self._logger.info(f"Local search browser started ({self._channel or 'chromium'}, {mode})")
        return self._context

    def _forget_context(self) -> None:
        self._context = None
        self._page = None

    async def _launch(self) -> BrowserContext:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        context = await self._launch_with_fallbacks()
        if self._headless and self._user_agent is None:
            # Headless Chrome identifies itself as "HeadlessChrome"; relaunch with the marker removed.
            probe = context.pages[0] if context.pages else await context.new_page()
            user_agent = await probe.evaluate("navigator.userAgent")
            if "HeadlessChrome" in user_agent:
                self._user_agent = user_agent.replace("HeadlessChrome", "Chrome")
                await context.close()
                context = await self._launch_with_fallbacks()
        return context

    async def _launch_with_fallbacks(self) -> BrowserContext:
        """Launch, adapting once to each recoverable problem: missing Chrome, missing display, locked profile."""
        assert self._playwright is not None
        while True:
            self._profile_dir = resolve_profile_dir(self._options.user_data_dir, self._channel, self._profile_suffix)
            try:
                return await self._playwright.chromium.launch_persistent_context(
                    self._profile_dir, **self._launch_kwargs()
                )
            except PlaywrightError as e:
                if self._channel and _matches(e, _CHANNEL_MISSING):
                    self._logger.warning(f"Browser channel '{self._channel}' is not installed; using bundled Chromium")
                    if not install([self._playwright.chromium]):
                        raise RuntimeError("Failed to install Chromium") from e
                    self._channel = None
                elif not self._headless and self._options.headless_without_display and _matches(e, _NO_DISPLAY):
                    self._logger.warning("No display available for a headed browser; running headless instead")
                    self._headless = True
                elif _matches(e, _PROFILE_LOCKED):
                    if not self._options.private_profile_id or self._profile_suffix:
                        raise ProfileInUseError(f"The browser profile {self._profile_dir} is in use") from e
                    self._logger.warning("The shared browser profile is in use; using a private profile instead")
                    self._profile_suffix = self._options.private_profile_id
                else:
                    raise

    def _launch_kwargs(self) -> Dict[str, Any]:
        args: List[str] = ["--disable-blink-features=AutomationControlled"]
        kwargs: Dict[str, Any] = {"headless": self._headless, "locale": self._options.locale, "args": args}
        if self._headless:
            kwargs["viewport"] = _HEADLESS_VIEWPORT
            if self._user_agent:
                kwargs["user_agent"] = self._user_agent
        else:
            kwargs["no_viewport"] = True  # size pages to the real window, as a normal browser does
            if self._options.hide_window:
                # Start minimized; the off-screen position covers window managers that ignore --start-minimized.
                # Wayland ignores both, which is why page() also minimizes over CDP.
                args += ["--start-minimized", "--window-position=-32000,-32000"]
        if self._channel:
            kwargs["channel"] = self._channel
        return kwargs

    @staticmethod
    async def _dismiss_consent(page: Page, selectors: Sequence[str]) -> None:
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.count() and await button.is_visible():
                    await button.click()
                    await page.wait_for_load_state("domcontentloaded")
                    return
            except PlaywrightError:
                continue
