import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import Error as PlaywrightError
import pytest

from rustic_ai.serpapi.local_browser import (
    BrowserOptions,
    LocalBrowser,
    ProfileInUseError,
    resolve_profile_dir,
)

LOGGER = logging.getLogger(__name__)
NO_DISPLAY = PlaywrightError("Looks like you launched a headed browser without having a XServer running")
PROFILE_LOCKED = PlaywrightError("Failed to create a ProcessSingleton for your profile directory")
CHROME_MISSING = PlaywrightError("Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome")


def launch(browser: LocalBrowser, *errors: Exception):
    """Run the launch-with-fallbacks logic against a fake Playwright that fails with `errors` before succeeding."""
    chromium = MagicMock()
    chromium.launch_persistent_context = AsyncMock(side_effect=[*errors, "context"])
    browser._playwright = MagicMock(chromium=chromium)
    assert asyncio.run(browser._launch_with_fallbacks()) == "context"
    return chromium.launch_persistent_context.call_args_list


class TestLaunchOptions:
    def test_headless(self, tmp_path):
        kwargs = LocalBrowser(BrowserOptions(user_data_dir=str(tmp_path)), LOGGER)._launch_kwargs()
        assert kwargs["headless"] is True
        assert kwargs["viewport"] == {"width": 1366, "height": 768}
        assert kwargs["channel"] == "chrome"
        assert "--start-minimized" not in kwargs["args"]

    def test_headed_hidden(self, tmp_path):
        kwargs = LocalBrowser(BrowserOptions(headless=False), LOGGER)._launch_kwargs()
        assert kwargs["headless"] is False
        assert kwargs["no_viewport"] is True
        assert "viewport" not in kwargs
        assert "--start-minimized" in kwargs["args"]

    def test_headed_visible(self):
        kwargs = LocalBrowser(BrowserOptions(headless=False, hide_window=False), LOGGER)._launch_kwargs()
        assert "--start-minimized" not in kwargs["args"]

    def test_bundled_chromium_has_no_channel(self):
        assert "channel" not in LocalBrowser(BrowserOptions(channel=None), LOGGER)._launch_kwargs()


class TestLaunchFallbacks:
    def test_missing_display_falls_back_to_headless_when_allowed(self, tmp_path):
        browser = LocalBrowser(
            BrowserOptions(headless=False, headless_without_display=True, user_data_dir=str(tmp_path)), LOGGER
        )
        calls = launch(browser, NO_DISPLAY)

        assert browser.headless
        assert calls[1].kwargs["headless"] is True

    def test_missing_display_is_an_error_otherwise(self, tmp_path):
        browser = LocalBrowser(BrowserOptions(headless=False, user_data_dir=str(tmp_path)), LOGGER)
        with pytest.raises(PlaywrightError):
            launch(browser, NO_DISPLAY)

    def test_locked_profile_uses_private_profile_when_allowed(self, tmp_path):
        browser = LocalBrowser(BrowserOptions(private_profile_id="agent1", user_data_dir=str(tmp_path)), LOGGER)
        calls = launch(browser, PROFILE_LOCKED)

        assert calls[0].args[0] == str(tmp_path / "chrome")
        assert calls[1].args[0] == str(tmp_path / "chrome-agent1")
        assert browser.profile_dir == str(tmp_path / "chrome-agent1")

    def test_locked_profile_is_reported_otherwise(self, tmp_path):
        browser = LocalBrowser(BrowserOptions(user_data_dir=str(tmp_path)), LOGGER)
        with pytest.raises(ProfileInUseError):
            launch(browser, PROFILE_LOCKED)

    def test_missing_chrome_installs_and_uses_chromium(self, tmp_path):
        browser = LocalBrowser(BrowserOptions(user_data_dir=str(tmp_path)), LOGGER)
        with patch("rustic_ai.serpapi.local_browser.install", return_value=True) as install:
            calls = launch(browser, CHROME_MISSING)

        install.assert_called_once()
        assert "channel" not in calls[1].kwargs
        assert calls[1].args[0] == str(tmp_path / "chromium")

    def test_other_errors_propagate(self, tmp_path):
        browser = LocalBrowser(BrowserOptions(user_data_dir=str(tmp_path)), LOGGER)
        with pytest.raises(PlaywrightError, match="boom"):
            launch(browser, PlaywrightError("boom"))


def test_profile_dirs(tmp_path):
    assert resolve_profile_dir(str(tmp_path), "chrome") == str(tmp_path / "chrome")
    assert resolve_profile_dir(str(tmp_path), None) == str(tmp_path / "chromium")
    assert resolve_profile_dir(str(tmp_path), "chrome", "agent1") == str(tmp_path / "chrome-agent1")
    assert (tmp_path / "chrome-agent1").is_dir()
