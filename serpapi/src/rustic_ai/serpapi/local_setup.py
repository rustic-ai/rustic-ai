"""
One-time setup for the LocalSERPAgent browser profile.

Opens the agent's persistent profile in a visible browser so the user can accept consent banners, solve a CAPTCHA and,
optionally, sign in to Google. The session is saved in the profile and reused by the agent in both modes.

    python -m rustic_ai.serpapi.local_setup [--user-data-dir DIR] [--channel chrome|chromium] [URL ...]

Close the browser window when done. Stop running LocalSERPAgent guilds first: a profile can be open in one browser only.
"""

import argparse
import asyncio
from typing import Any, Dict, List, Optional

from install_playwright import install
from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Playwright, async_playwright

from rustic_ai.serpapi.local_browser import (
    default_profile_root,
    is_channel_missing,
    is_profile_locked,
    launch_args,
    resolve_profile_dir,
)

DEFAULT_URLS = ["https://www.google.com/search?q=rustic+ai", "https://www.bing.com/"]


async def _launch(playwright: Playwright, user_data_dir: Optional[str], channel: Optional[str]) -> BrowserContext:
    kwargs: Dict[str, Any] = {
        "headless": False,
        "no_viewport": True,
        "args": launch_args(headless=False, hide_window=False),
    }
    if channel:
        kwargs["channel"] = channel
    return await playwright.chromium.launch_persistent_context(resolve_profile_dir(user_data_dir, channel), **kwargs)


async def open_profile(user_data_dir: Optional[str], channel: Optional[str], urls: List[str]) -> str:
    """Open the profile in a visible browser with `urls` in tabs; returns the profile path once the user closes it."""
    async with async_playwright() as playwright:
        try:
            context = await _launch(playwright, user_data_dir, channel)
        except PlaywrightError as e:
            if is_profile_locked(e):
                raise SystemExit("The search profile is in use. Stop running LocalSERPAgent guilds and try again.")
            if not channel or not is_channel_missing(e):
                raise
            print(f"Browser channel '{channel}' is not installed; using bundled Chromium instead.")
            if not install([playwright.chromium]):
                raise SystemExit("Failed to install Chromium.")
            channel = None
            context = await _launch(playwright, user_data_dir, channel)

        closed = asyncio.Event()
        context.on("close", lambda _: closed.set())
        for i, url in enumerate(urls):
            page = context.pages[0] if i == 0 and context.pages else await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except PlaywrightError as e:
                print(f"Could not open {url}: {e}")

        await closed.wait()
        return resolve_profile_dir(user_data_dir, channel)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare the LocalSERPAgent browser profile.")
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help=f"profile root; must match the agent's user_data_dir (default: {default_profile_root()})",
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help="browser channel; must match the agent's browser_channel ('chromium' for bundled Chromium)",
    )
    parser.add_argument("urls", nargs="*", default=DEFAULT_URLS, help="pages to open (default: Google and Bing)")
    args = parser.parse_args(argv)
    channel = None if args.channel.lower() in ("", "chromium", "none") else args.channel

    print(
        "A browser window will open with the LocalSERPAgent profile:\n"
        "  1. Accept or reject any cookie / consent banners.\n"
        "  2. Solve a CAPTCHA if one is shown.\n"
        "  3. Optionally sign in to your Google account.\n"
        "Close the browser window when you are done."
    )
    profile = asyncio.run(open_profile(args.user_data_dir, channel, args.urls))
    print(f"Profile saved at {profile}")


if __name__ == "__main__":
    main()
