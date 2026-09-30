import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import pytest

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.serpapi.agent import SearchError, SERPQuery, SERPResults
from rustic_ai.serpapi.local_agent import LocalSERPAgent
from rustic_ai.serpapi.local_browser import launch_args, resolve_profile_dir

from rustic_ai.testing.helpers import wrap_agent_for_testing

FIXTURES = Path(__file__).parent / "fixtures" / "local_serp"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _google_page(url: str) -> str:
    start = int(parse_qs(urlparse(url).query).get("start", ["0"])[0])
    return "google_page2.html" if start >= 10 else "google_page1.html"


DEFAULT_PAGES = {
    "www.google.com": _google_page,
    "www.bing.com": lambda url: "bing_page1.html",
    "html.duckduckgo.com": lambda url: "ddg_page1.html",
}

GOTO_TARGETS = {
    "https://www.google.com/goto?url=CAESbgHrOzAVTOKENONE": "https://goto-a.example/page",
    # ...TOKENTWO does not resolve, so that result is dropped
}


class FakeBrowser:
    """Serves fixture pages in place of real navigation and records what was requested."""

    def __init__(self):
        self.pages: Dict[str, str] = {}  # host -> fixture name, overriding DEFAULT_PAGES
        self.requests: List[str] = []

    def _page_for(self, host: str, url: str) -> str:
        return fixture(self.pages.get(host) or DEFAULT_PAGES[host](url))

    async def fetch(self, page, url, engine):
        self.requests.append(url)
        return self._page_for(urlparse(url).hostname or "", url), url

    async def next_page(self, page, engine):
        self.requests.append(f"next:{engine.name}")
        host = "www.bing.com" if engine.name == "bing" else "html.duckduckgo.com"
        url = f"https://{host}/next"
        return self._page_for(host, url), url

    async def resolve_url(self, url):
        self.requests.append(f"resolve:{url}")
        return GOTO_TARGETS.get(url)

    async def ensure_page(self):
        return MagicMock()


class FakeWindow:
    """The headed browser window, and a user who solves (or ignores) the CAPTCHA shown in it."""

    def __init__(self, solved_page: Optional[str]):
        self.solved_page = solved_page
        self.states: List[str] = []

    async def set_window_state(self, page, minimized):
        self.states.append("minimized" if minimized else "shown")

    async def snapshot(self, page):
        if self.solved_page is None:
            return fixture("google_captcha.html"), "https://www.google.com/sorry/index"
        return fixture(self.solved_page), "https://www.google.com/search?q=x"


def _patch(name: str, fn):
    return patch.object(LocalSERPAgent, name, lambda _agent, *args, **kwargs: fn(*args, **kwargs))


@pytest.fixture
def browser():
    fake = FakeBrowser()
    with (
        _patch("_fetch", fake.fetch),
        _patch("_next_page", fake.next_page),
        _patch("_resolve_url", fake.resolve_url),
        _patch("_ensure_page", fake.ensure_page),
    ):
        yield fake


@pytest.fixture
def window():
    patches: List[Any] = []

    def make(solved_page: Optional[str]) -> FakeWindow:
        fake = FakeWindow(solved_page)
        patches.extend(
            [
                _patch("_set_window_state", fake.set_window_state),
                _patch("_snapshot", fake.snapshot),
                _patch("_read_page", fake.snapshot),
                patch.object(LocalSERPAgent, "_user_poll_s", 0.01),
            ]
        )
        for p in patches:
            p.start()
        return fake

    yield make
    for p in patches:
        p.stop()


def make_agent(**properties):
    return wrap_agent_for_testing(
        AgentBuilder(LocalSERPAgent)
        .set_name("TestLocalSerpAgent")
        .set_id("local_serp_agent")
        .set_description("Test Local Serp Agent")
        .set_properties({"min_delay_s": 0, "max_delay_s": 0, **properties})
        .build_spec(),
    )


def search(generator, agent, **payload) -> Message:
    query = Message(
        topics="default_topic",
        sender=AgentTag(id="testerId", name="tester"),
        format=get_qualified_class_name(SERPQuery),
        payload={"query": "multi-agent AI", "id": "q1", **payload},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(query)
    return query


class TestSearch:
    def test_google_results(self, generator, browser):
        agent, results = make_agent()
        query = search(generator, agent, engine="google", num=5)

        assert len(results) == 1
        assert results[0].in_response_to == query.id
        assert results[0].current_thread_id == query.id

        result = SERPResults.model_validate(results[0].payload)
        assert (result.engine, result.query, result.id) == ("google", "multi-agent AI", "q1")
        assert result.count == 5
        assert result.total_results == 1234000

        first = result.results[0]
        assert first.url == "https://example.com/g/1"
        assert first.mimetype == "text/html"
        assert first.metadata == {
            "title": "Google Result 1",
            "favicon": "",
            "search_position": 1,
            "snippet": "Snippet for google result 1.",
            "date": "",
            "query_id": "q1",
            "engine": "google",
            "source": "local_browser",
        }
        # The /goto links on page one are beyond the 5 requested results, so none are resolved
        assert not [r for r in browser.requests if r.startswith("resolve:")]

    def test_google_pagination_and_goto_resolution(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="google", num=15)

        result = SERPResults.model_validate(results[0].payload)
        assert result.count == 15
        assert [r.metadata["search_position"] for r in result.results] == list(range(1, 16))  # type: ignore[index]
        # Page one: 10 direct links + 1 resolved /goto link (the unresolvable one is dropped); page two fills the rest
        assert result.results[10].url == "https://goto-a.example/page"
        assert result.results[10].metadata["date"] == "Apr 1, 2026"  # type: ignore[index]
        assert result.results[14].url == "https://example.com/g/14"
        assert len([r for r in browser.requests if r.startswith("https://www.google.com/search")]) == 2
        assert len([r for r in browser.requests if r.startswith("resolve:")]) == 2

    def test_start_offset_positions_are_absolute(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="google", num=3, start=10)

        result = SERPResults.model_validate(results[0].payload)
        assert "start=10" in browser.requests[0]
        assert [r.metadata["search_position"] for r in result.results] == [11, 12, 13]  # type: ignore[index]

    def test_bing_results(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="bing", num=5)

        result = SERPResults.model_validate(results[0].payload)
        assert result.engine == "bing"
        assert result.results[1].url == "https://example.org/b/2"

    def test_click_pagination_retries_next_once(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="duckduckgo", num=12)

        # The "next" fixture repeats page one: "Next" is retried once, then the search stops with what it has
        result = SERPResults.model_validate(results[0].payload)
        assert result.count == 10
        assert browser.requests.count("next:duckduckgo") == 2

    def test_no_results_is_an_empty_response(self, generator, browser):
        browser.pages["www.google.com"] = "google_empty.html"
        agent, results = make_agent()
        search(generator, agent, engine="google")

        result = SERPResults.model_validate(results[0].payload)
        assert result.count == 0
        assert result.results == []


class TestErrors:
    def _error(self, results) -> Dict[str, Any]:
        assert len(results) == 1
        error = SearchError.model_validate(results[0].payload)
        assert error.id == "q1"
        assert error.response["status"] == "Error"
        return error.response

    @pytest.mark.parametrize(
        "engine,page",
        [("google", "google_captcha.html"), ("bing", "bing_captcha.html"), ("duckduckgo", "ddg_anomaly.html")],
    )
    def test_blocked_engine_returns_error_without_fallback(self, generator, browser, engine, page):
        host = {"google": "www.google.com", "bing": "www.bing.com", "duckduckgo": "html.duckduckgo.com"}[engine]
        browser.pages[host] = page
        agent, results = make_agent()
        search(generator, agent, engine=engine)

        response = self._error(results)
        assert response["engine"] == engine
        assert response["reason"] == "captcha"
        assert len(browser.requests) == 1  # no other engine was tried

    def test_unsupported_engine(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="ebay")

        response = self._error(results)
        assert response["reason"] == "unsupported_engine"
        assert "ebay" in response["error"]
        assert browser.requests == []

    def test_page_timeout(self, generator, browser):
        async def time_out(page, url, engine):
            raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        with _patch("_fetch", time_out):
            agent, results = make_agent()
            search(generator, agent, engine="google")

        assert self._error(results)["reason"] == "timeout"

    def test_search_deadline_cancels_and_releases_the_agent(self, generator, browser):
        slow_fetch_done = []

        async def hang(page, url, engine):
            await asyncio.sleep(5)
            slow_fetch_done.append(url)  # never reached: the search is cancelled at its deadline
            return fixture("google_page1.html"), url

        agent, results = make_agent(search_timeout_s=0.1)
        with _patch("_fetch", hang):
            search(generator, agent, engine="google")
        assert self._error(results)["reason"] == "timeout"

        # The lock was released, so the next search runs normally
        search(generator, agent, engine="bing", num=3)
        assert SERPResults.model_validate(results[1].payload).count == 3
        assert slow_fetch_done == []

    def test_browser_error(self, generator, browser):
        async def crash(page, url, engine):
            raise PlaywrightError("Target page, context or browser has been closed")

        with _patch("_fetch", crash):
            agent, results = make_agent()
            search(generator, agent, engine="google")

        response = self._error(results)
        assert response["reason"] == "browser_error"
        assert "has been closed" in response["error"]


class TestHeadedMode:
    def test_user_solves_captcha(self, generator, browser, window):
        browser.pages["www.google.com"] = "google_captcha.html"
        fake_window = window(solved_page="google_page1.html")
        agent, results = make_agent(headless=False, captcha_wait_s=5)
        search(generator, agent, engine="google", num=5)

        result = SERPResults.model_validate(results[0].payload)
        assert result.results[0].url == "https://example.com/g/1"
        assert fake_window.states == ["shown", "minimized"]

    def test_unsolved_captcha_returns_error(self, generator, browser, window):
        browser.pages["www.google.com"] = "google_captcha.html"
        fake_window = window(solved_page=None)
        agent, results = make_agent(headless=False, captcha_wait_s=0.05)
        search(generator, agent, engine="google")

        assert SearchError.model_validate(results[0].payload).response["reason"] == "captcha"
        assert fake_window.states == ["shown", "minimized"]

    def test_window_left_open_when_not_hiding(self, generator, browser, window):
        browser.pages["www.google.com"] = "google_captcha.html"
        fake_window = window(solved_page="google_page1.html")
        agent, results = make_agent(headless=False, hide_window=False, captcha_wait_s=5)
        search(generator, agent, engine="google", num=5)

        assert SERPResults.model_validate(results[0].payload).count == 5
        assert fake_window.states == ["shown"]

    def test_waiting_disabled(self, generator, browser, window):
        browser.pages["www.google.com"] = "google_captcha.html"
        fake_window = window(solved_page="google_page1.html")
        agent, results = make_agent(headless=False, captcha_wait_s=0)
        search(generator, agent, engine="google")

        assert SearchError.model_validate(results[0].payload).response["reason"] == "captcha"
        assert fake_window.states == []

    def test_headless_never_waits_for_user(self, generator, browser, window):
        browser.pages["www.google.com"] = "google_captcha.html"
        fake_window = window(solved_page="google_page1.html")
        agent, results = make_agent(headless=True, captcha_wait_s=5)
        search(generator, agent, engine="google")

        assert SearchError.model_validate(results[0].payload).response["reason"] == "captcha"
        assert fake_window.states == []


class TestBrowserLaunch:
    def test_launch_kwargs_per_mode(self, tmp_path):
        headless, _ = make_agent(user_data_dir=str(tmp_path))
        kwargs = headless._launch_kwargs("chrome")
        assert kwargs["headless"] is True
        assert kwargs["viewport"] == {"width": 1366, "height": 768}
        assert "--start-minimized" not in kwargs["args"]

        headed, _ = make_agent(headless=False, user_data_dir=str(tmp_path))
        kwargs = headed._launch_kwargs("chrome")
        assert kwargs["headless"] is False
        assert kwargs["no_viewport"] is True
        assert "viewport" not in kwargs
        assert "--start-minimized" in kwargs["args"]
        assert kwargs["channel"] == "chrome"

    def _launch(self, agent, *errors):
        chromium = MagicMock()
        chromium.launch_persistent_context = AsyncMock(side_effect=[*errors, "context"])
        agent._playwright = MagicMock(chromium=chromium)
        assert agent._loop_thread.run_coroutine(agent._launch("chrome")) == "context"
        return chromium.launch_persistent_context.call_args_list

    def test_headed_without_display_falls_back_to_headless(self, tmp_path):
        agent, _ = make_agent(headless=False, user_data_dir=str(tmp_path))
        calls = self._launch(
            agent, PlaywrightError("Looks like you launched a headed browser without having a XServer")
        )

        assert agent._force_headless
        assert calls[1].kwargs["headless"] is True

    def test_locked_profile_uses_private_profile(self, tmp_path):
        agent, _ = make_agent(user_data_dir=str(tmp_path))
        calls = self._launch(agent, PlaywrightError("Failed to create a ProcessSingleton for your profile directory"))

        assert calls[0].args[0] == str(tmp_path / "chrome")
        assert calls[1].args[0] == str(tmp_path / "chrome-local_serp_agent")

    def test_other_launch_errors_propagate(self, tmp_path):
        agent, _ = make_agent(user_data_dir=str(tmp_path))
        chromium = MagicMock()
        chromium.launch_persistent_context = AsyncMock(side_effect=PlaywrightError("boom"))
        agent._playwright = MagicMock(chromium=chromium)
        with pytest.raises(PlaywrightError):
            agent._loop_thread.run_coroutine(agent._launch("chrome"))

    def test_deadline_includes_captcha_wait_only_when_headed(self):
        assert make_agent()[0]._deadline_s() == 120.0
        assert make_agent(headless=False, captcha_wait_s=60)[0]._deadline_s() == 180.0
        assert make_agent(search_timeout_s=30)[0]._deadline_s() == 30.0


class TestBrowserHelpers:
    def test_profile_dirs(self, tmp_path):
        assert resolve_profile_dir(str(tmp_path), "chrome") == str(tmp_path / "chrome")
        assert resolve_profile_dir(str(tmp_path), None) == str(tmp_path / "chromium")
        assert resolve_profile_dir(str(tmp_path), "chrome", "agent1") == str(tmp_path / "chrome-agent1")
        assert (tmp_path / "chrome-agent1").is_dir()

    def test_launch_args(self):
        assert "--start-minimized" in launch_args(headless=False, hide_window=True)
        assert "--start-minimized" not in launch_args(headless=False, hide_window=False)
        assert "--start-minimized" not in launch_args(headless=True, hide_window=True)


@pytest.mark.skipif(
    os.getenv("RUSTIC_LOCAL_SERP_LIVE") != "1", reason="set RUSTIC_LOCAL_SERP_LIVE=1 to hit live engines"
)
class TestLive:
    @pytest.mark.parametrize("engine", ["duckduckgo", "bing"])
    def test_live_search(self, generator, engine):
        agent, results = make_agent()
        search(generator, agent, engine=engine, num=5)

        result = SERPResults.model_validate(results[0].payload)
        assert result.count > 0
        assert result.results[0].url.startswith("http")
