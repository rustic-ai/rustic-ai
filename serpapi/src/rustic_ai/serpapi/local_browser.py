"""Browser helpers shared by `LocalSERPAgent` and the `local_setup` CLI."""

import os
from typing import List, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

_PROFILE_LOCKED = ("ProcessSingleton", "SingletonLock")
_CHANNEL_MISSING = ("is not found", "Executable doesn't exist", "distribution")
_NO_DISPLAY = ("Missing X server", "$DISPLAY", "headed browser without having a XServer")


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


def launch_args(headless: bool, hide_window: bool) -> List[str]:
    args = ["--disable-blink-features=AutomationControlled"]
    if not headless and hide_window:
        # Start minimized; the off-screen position covers window managers that ignore --start-minimized.
        # Wayland ignores both, which is why set_window_state() minimizes over CDP as well.
        args += ["--start-minimized", "--window-position=-32000,-32000"]
    return args


def is_profile_locked(error: PlaywrightError) -> bool:
    return any(marker in str(error) for marker in _PROFILE_LOCKED)


def is_channel_missing(error: PlaywrightError) -> bool:
    return any(marker in str(error) for marker in _CHANNEL_MISSING)


def is_display_missing(error: PlaywrightError) -> bool:
    return any(marker in str(error) for marker in _NO_DISPLAY)


async def set_window_state(page: Page, minimized: bool) -> None:
    """Minimize or restore the page's browser window over CDP (works on X11, Wayland, macOS and Windows)."""
    cdp = await page.context.new_cdp_session(page)
    try:
        window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        if minimized:
            await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "minimized"}})
            return
        # Bounds can only be changed in the normal state; move the window back on screen where the WM allows it.
        await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "normal"}})
        await cdp.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"left": 80, "top": 80, "width": 1280, "height": 900}},
        )
        await page.bring_to_front()
    finally:
        await cdp.detach()
