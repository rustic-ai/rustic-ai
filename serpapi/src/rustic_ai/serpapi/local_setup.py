"""
One-time setup for the LocalSERPAgent browser profile.

Opens the agent's persistent profile in a visible browser so the user can accept consent banners, solve a CAPTCHA and,
optionally, sign in to Google. The session is saved in the profile and reused by the agent in both modes.

    python -m rustic_ai.serpapi.local_setup [--user-data-dir DIR] [--channel chrome|chromium] [URL ...]

Close the browser window when done. Stop running LocalSERPAgent guilds first: a profile can be open in one browser only.
"""

import argparse
import asyncio
import logging
from typing import List, Optional

from playwright.async_api import Error as PlaywrightError

from rustic_ai.serpapi.local_browser import (
    BrowserOptions,
    LocalBrowser,
    ProfileInUseError,
    default_profile_root,
)

DEFAULT_URLS = ["https://www.google.com/search?q=rustic+ai", "https://www.bing.com/"]

INSTRUCTIONS = """\
A browser window will open with the LocalSERPAgent profile:
  1. Accept or reject any cookie / consent banners.
  2. Solve a CAPTCHA if one is shown.
  3. Optionally sign in to your Google account.
Close the browser window when you are done."""

logger = logging.getLogger(__name__)


async def open_profile(user_data_dir: Optional[str], channel: Optional[str], urls: List[str]) -> Optional[str]:
    """Open the profile in a visible browser with `urls` in tabs; returns the profile path once the user closes it."""
    browser = LocalBrowser(
        BrowserOptions(headless=False, hide_window=False, channel=channel, user_data_dir=user_data_dir), logger
    )
    try:
        await browser.page()  # launch first, so launch failures are raised rather than reported as page errors
        for index, url in enumerate(urls):
            try:
                if index == 0:
                    await browser.goto(url)
                else:
                    await browser.new_tab(url)
            except PlaywrightError as e:
                print(f"Could not open {url}: {e}")
        await browser.wait_until_closed()
        return browser.profile_dir
    finally:
        await browser.close()


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

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    print(INSTRUCTIONS)
    try:
        profile = asyncio.run(open_profile(args.user_data_dir, channel, args.urls))
    except ProfileInUseError:
        raise SystemExit("The search profile is in use. Stop running LocalSERPAgent guilds and try again.")
    print(f"Profile saved at {profile}")


if __name__ == "__main__":
    main()
