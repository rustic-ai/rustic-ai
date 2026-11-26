"""Local browser coverage for bounded, independent recursive crawls."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.playwright.agent import PlaywrightScraperAgent, WebScrapingRequest

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.mark.asyncio
async def test_concurrent_crawls_have_independent_caps_and_output_files(tmp_path):
    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                ("<title>Harbor</title>Harbor 42000" + "".join(f'<a href="/{i}">page</a>' for i in range(20))).encode()
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    agent, _ = wrap_agent_for_testing(
        AgentBuilder(PlaywrightScraperAgent)
        .set_id("browser")
        .set_name("Browser")
        .set_description("Local crawler")
        .set_properties({"browser_lifecycle": "per_request"})
        .build_spec(),
        {
            "filesystem": DependencySpec(
                class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
                properties={"path_base": str(tmp_path), "protocol": "file", "storage_options": {"auto_mkdir": True}},
            )
        },
    )
    fs = agent._dependency_resolvers["filesystem"].get_or_resolve(agent.get_organization(), agent.guild_id, None)
    url = f"http://127.0.0.1:{server.server_port}/"
    try:

        def run(id, format):
            return agent._run_in_playwright_loop(
                agent._do_scrape(
                    WebScrapingRequest(id=id, links=[MediaLink(url=url)], depth=3, max_pages=2, output_format=format),
                    fs,
                )
            )

        first, second = await asyncio.gather(
            asyncio.to_thread(run, "one", "text/html"), asyncio.to_thread(run, "two", "text/markdown")
        )
        assert len(first[0]) == len(second[0]) == 2
        assert not first[1] and not second[1]
        assert {doc.url for doc in first[0]}.isdisjoint({doc.url for doc in second[0]})
        for docs, _ in [first, second]:
            for doc in docs:
                path = doc.url.removeprefix("file:///")
                assert fs.cat_file(path)
    finally:
        agent.on_shutdown()
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["startup", "context", "close", "cancel"])
async def test_failed_browser_request_balances_counter_and_allows_cleanup(failure):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from rustic_ai.playwright.agent import BrowserLifecycle

    context = SimpleNamespace(close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    state = SimpleNamespace(
        _active_ops=0,
        _browser_lock=asyncio.Lock(),
        _browser=browser,
        _playwright=None,
        _initialized=True,
        config=SimpleNamespace(parallel_pages=1, browser_lifecycle=BrowserLifecycle.PER_REQUEST),
        logger=Mock(),
        _ensure_browser=AsyncMock(return_value=browser),
        _scrape_url_with_depth=AsyncMock(),
    )

    async def cleanup(only_idle=False):
        await PlaywrightScraperAgent._cleanup(state, only_idle)

    state._cleanup = cleanup
    error = RuntimeError("Transient browser failure")
    if failure == "startup":
        state._ensure_browser.side_effect = [error, browser]
    elif failure == "context":
        browser.new_context.side_effect = [error, context]
    elif failure == "close":
        context.close.side_effect = [error, None]
    else:
        state._ensure_browser.side_effect = [asyncio.CancelledError(), browser]
    request = WebScrapingRequest(links=[MediaLink(url="https://example.test/")], max_pages=1)
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        await PlaywrightScraperAgent._do_scrape(state, request, None)
    assert state._active_ops == 0
    await PlaywrightScraperAgent._do_scrape(state, request, None)
    assert state._active_ops == 0 and browser.close.await_count == 2


@pytest.mark.asyncio
async def test_crawl_filters_visited_and_unsupported_links_before_page_cap():
    from types import MethodType, SimpleNamespace

    root = "https://example.test/"
    child = root + "article"
    state = SimpleNamespace(config=SimpleNamespace(parallel_pages=5))
    fetched = []

    async def page(url, *args):
        fetched.append(url)
        return MediaLink(url=url), [root, root + "download.pdf", child, child] if url == root else [], None

    state._scrape_page = page
    state._scrape_url_with_depth = MethodType(PlaywrightScraperAgent._scrape_url_with_depth, state)
    request = WebScrapingRequest(links=[MediaLink(url=root)], depth=1, max_pages=2)
    docs, errors, visited = [], [], set()
    await state._scrape_url_with_depth(root, 1, None, request, None, asyncio.Semaphore(5), docs, errors, visited)
    assert fetched == [root, child] and len(visited) == 2 and not errors
