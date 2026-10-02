import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch
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
from rustic_ai.serpapi.local_browser import PageContent

from rustic_ai.testing.helpers import wrap_agent_for_testing

FIXTURES = Path(__file__).parent / "fixtures" / "local_serp"

GOTO_TARGETS = {
    "https://www.google.com/goto?url=CAESbgHrOzAVTOKENONE": "https://goto-a.example/page",
    # ...TOKENTWO does not resolve, so that result is dropped
}


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _default_page(host: str, url: str) -> str:
    if host == "www.google.com":
        start = int(parse_qs(urlparse(url).query).get("start", ["0"])[0])
        return "google_page2.html" if start >= 10 else "google_page1.html"
    return {"www.bing.com": "bing_page1.html", "html.duckduckgo.com": "ddg_page1.html"}[host]


class FakeBrowser:
    """
    Stands in for LocalBrowser: serves fixture pages and records what the agent asked for.

    `solved_page`, when set, is what the page turns into once the "user" solves a CAPTCHA in the window.
    """

    def __init__(self):
        self.headless = True
        self.pages: Dict[str, str] = {}  # host -> fixture name, overriding the defaults
        self.solved_page: Optional[str] = None
        self.requests: List[str] = []
        self.window: List[str] = []
        self.closed = 0
        self._current = PageContent("", "")

    def _load(self, host: str, url: str) -> PageContent:
        self._current = PageContent(fixture(self.pages.get(host) or _default_page(host, url)), url)
        return self._current

    async def goto(self, url: str, consent_selectors: Sequence[str] = ()) -> PageContent:
        self.requests.append(url)
        return self._load(urlparse(url).hostname or "", url)

    async def click_next(self, selector: str) -> Optional[PageContent]:
        host = "www.bing.com" if selector == "a.sb_pagN" else "html.duckduckgo.com"
        self.requests.append(f"next:{host}")
        return self._load(host, f"https://{host}/next")

    async def read(self) -> PageContent:
        return self._current

    async def snapshot(self) -> Optional[PageContent]:
        if self.solved_page is not None:
            self._current = PageContent(fixture(self.solved_page), "https://www.google.com/search?q=x")
        return self._current

    async def resolve_redirect(self, url: str) -> Optional[str]:
        self.requests.append(f"resolve:{url}")
        return GOTO_TARGETS.get(url)

    async def show_window(self) -> None:
        self.window.append("shown")

    async def hide_window(self) -> None:
        self.window.append("minimized")

    async def close(self) -> None:
        self.closed += 1


@pytest.fixture
def browser():
    fake = FakeBrowser()

    def create(agent):
        fake.headless = agent.config.headless
        return fake

    with patch.object(LocalSERPAgent, "_create_browser", create), patch.object(LocalSERPAgent, "_user_poll_s", 0.01):
        yield fake


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


def only_results(results) -> SERPResults:
    assert len(results) == 1
    return SERPResults.model_validate(results[0].payload)


def only_error(results) -> Dict[str, Any]:
    assert len(results) == 1
    error = SearchError.model_validate(results[0].payload)
    assert error.id == "q1"
    assert error.response["status"] == "Error"
    return error.response


class TestSearch:
    def test_google_results(self, generator, browser):
        agent, results = make_agent()
        query = search(generator, agent, engine="google", num=5)

        assert results[0].in_response_to == query.id
        assert results[0].current_thread_id == query.id
        result = only_results(results)
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

        result = only_results(results)
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

        assert "start=10" in browser.requests[0]
        positions = [r.metadata["search_position"] for r in only_results(results).results]  # type: ignore[index]
        assert positions == [11, 12, 13]

    def test_bing_retries_a_repeated_page_once(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="bing", num=12)

        # The "next" fixture repeats page one: Bing's "Next" is retried once, then the search stops with what it has
        result = only_results(results)
        assert result.count == 10
        assert result.results[1].url == "https://example.org/b/2"
        assert browser.requests.count("next:www.bing.com") == 2

    def test_duckduckgo_stops_on_a_repeated_page(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="duckduckgo", num=12)

        assert only_results(results).count == 10
        assert browser.requests.count("next:html.duckduckgo.com") == 1

    def test_no_results_is_an_empty_response(self, generator, browser):
        browser.pages["www.google.com"] = "google_empty.html"
        agent, results = make_agent()
        search(generator, agent, engine="google")

        result = only_results(results)
        assert (result.count, result.results) == (0, [])

    def test_browser_kept_open_between_searches_by_default(self, generator, browser):
        agent, _ = make_agent()
        search(generator, agent, engine="google", num=3)
        assert browser.closed == 0

    def test_close_browser_after_request(self, generator, browser):
        agent, _ = make_agent(close_browser_after_request=True)
        search(generator, agent, engine="google", num=3)
        assert browser.closed == 1


class TestErrors:
    @pytest.mark.parametrize(
        "engine,host,page",
        [
            ("google", "www.google.com", "google_captcha.html"),
            ("bing", "www.bing.com", "bing_captcha.html"),
            ("duckduckgo", "html.duckduckgo.com", "ddg_anomaly.html"),
        ],
    )
    def test_blocked_engine_returns_error_without_fallback(self, generator, browser, engine, host, page):
        browser.pages[host] = page
        agent, results = make_agent()
        search(generator, agent, engine=engine)

        response = only_error(results)
        assert (response["engine"], response["reason"]) == (engine, "captcha")
        assert len(browser.requests) == 1  # no other engine was tried

    def test_unsupported_engine(self, generator, browser):
        agent, results = make_agent()
        search(generator, agent, engine="ebay")

        response = only_error(results)
        assert response["reason"] == "unsupported_engine"
        assert "ebay" in response["error"]
        assert browser.requests == []

    def test_page_timeout(self, generator, browser):
        async def time_out(url, consent_selectors=()):
            raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

        browser.goto = time_out  # type: ignore[method-assign]
        agent, results = make_agent()
        search(generator, agent, engine="google")

        assert only_error(results)["reason"] == "timeout"

    def test_search_deadline_cancels_and_releases_the_agent(self, generator, browser):
        load_page = browser.goto
        finished: List[str] = []

        async def hang(url, consent_selectors=()):
            await asyncio.sleep(5)
            finished.append(url)  # never reached: the search is cancelled at its deadline
            return await load_page(url)

        browser.goto = hang  # type: ignore[method-assign]
        agent, results = make_agent(search_timeout_s=0.1)
        search(generator, agent, engine="google")
        assert only_error(results)["reason"] == "timeout"

        # The lock was released, so the next search runs normally
        browser.goto = load_page  # type: ignore[method-assign]
        search(generator, agent, engine="bing", num=3)
        assert SERPResults.model_validate(results[1].payload).count == 3
        assert finished == []

    def test_browser_error(self, generator, browser):
        async def crash(url, consent_selectors=()):
            raise PlaywrightError("Target page, context or browser has been closed")

        browser.goto = crash  # type: ignore[method-assign]
        agent, results = make_agent()
        search(generator, agent, engine="google")

        response = only_error(results)
        assert response["reason"] == "browser_error"
        assert "has been closed" in response["error"]


class TestHeadedMode:
    @pytest.fixture(autouse=True)
    def google_captcha(self, browser):
        browser.pages["www.google.com"] = "google_captcha.html"

    def test_user_solves_captcha(self, generator, browser):
        browser.solved_page = "google_page1.html"
        agent, results = make_agent(headless=False, captcha_wait_s=5)
        search(generator, agent, engine="google", num=5)

        assert only_results(results).results[0].url == "https://example.com/g/1"
        assert browser.window == ["shown", "minimized"]

    def test_unsolved_captcha_returns_error(self, generator, browser):
        agent, results = make_agent(headless=False, captcha_wait_s=0.05)
        search(generator, agent, engine="google")

        assert only_error(results)["reason"] == "captcha"
        assert browser.window == ["shown", "minimized"]

    def test_window_left_open_when_not_hiding(self, generator, browser):
        browser.solved_page = "google_page1.html"
        agent, results = make_agent(headless=False, hide_window=False, captcha_wait_s=5)
        search(generator, agent, engine="google", num=5)

        assert only_results(results).count == 5
        assert browser.window == ["shown"]

    def test_waiting_disabled(self, generator, browser):
        browser.solved_page = "google_page1.html"
        agent, results = make_agent(headless=False, captcha_wait_s=0)
        search(generator, agent, engine="google")

        assert only_error(results)["reason"] == "captcha"
        assert browser.window == []

    def test_headless_never_waits_for_user(self, generator, browser):
        browser.solved_page = "google_page1.html"
        agent, results = make_agent(headless=True, captcha_wait_s=5)
        search(generator, agent, engine="google")

        assert only_error(results)["reason"] == "captcha"
        assert browser.window == []


class TestConfig:
    def test_deadline_includes_captcha_wait_only_when_headed(self):
        assert make_agent()[0]._deadline_s() == 120.0
        assert make_agent(headless=False, captcha_wait_s=60)[0]._deadline_s() == 180.0
        assert make_agent(search_timeout_s=30)[0]._deadline_s() == 30.0

    def test_browser_options_follow_config(self, tmp_path):
        agent, _ = make_agent(headless=False, hide_window=False, user_data_dir=str(tmp_path), hl="de", gl="de")
        options = agent._create_browser()._options

        assert (options.headless, options.hide_window) == (False, False)
        assert options.user_data_dir == str(tmp_path)
        assert options.locale == "de-DE"
        assert options.private_profile_id == "local_serp_agent"
        assert options.headless_without_display

    def test_invalid_delays_rejected(self):
        with pytest.raises(Exception, match="max_delay_s"):
            make_agent(min_delay_s=3, max_delay_s=1)
