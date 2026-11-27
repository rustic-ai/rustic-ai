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
    docs: list[MediaLink] = []
    errors: list = []
    visited: set[str] = set()
    await state._scrape_url_with_depth(root, 1, None, request, None, asyncio.Semaphore(5), docs, errors, visited)
    assert fetched == [root, child] and len(visited) == 2 and not errors


def test_outer_timeout_cancels_owned_scrape_and_waits_for_cleanup(tmp_path):
    from rustic_ai.playwright.agent import PlaywrightEventLoopThread

    loop = PlaywrightEventLoopThread()
    entered, cleaned = threading.Event(), threading.Event()

    async def work():
        try:
            entered.set()
            await asyncio.sleep(0.2)
            (tmp_path / "late.md").write_text("late source work")
        finally:
            await asyncio.sleep(0.01)
            cleaned.set()

    try:
        with pytest.raises(TimeoutError):
            loop.run_coroutine(work(), timeout=0.05)
        assert entered.is_set() and cleaned.is_set()
        assert not (tmp_path / "late.md").exists()
        assert loop.run_coroutine(asyncio.sleep(0.01, result="healthy")) == "healthy"
    finally:
        loop.stop()


def test_outer_timeout_preserves_another_concurrent_request():
    from concurrent.futures import ThreadPoolExecutor

    from rustic_ai.playwright.agent import PlaywrightEventLoopThread

    loop = PlaywrightEventLoopThread()
    started = threading.Event()

    async def healthy():
        started.set()
        await asyncio.sleep(0.1)
        return "completed"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            other = pool.submit(loop.run_coroutine, healthy(), 1)
            assert started.wait(1)
            with pytest.raises(TimeoutError):
                loop.run_coroutine(asyncio.sleep(2), timeout=0.02)
            assert other.result(timeout=1) == "completed"
    finally:
        loop.stop()


@pytest.mark.asyncio
async def test_idle_cleanup_does_not_hold_successful_result():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from rustic_ai.playwright.agent import BrowserLifecycle

    context = SimpleNamespace(close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
    state = SimpleNamespace(
        _active_ops=0,
        _idle_cleanup_task=None,
        config=SimpleNamespace(
            parallel_pages=1, browser_lifecycle=BrowserLifecycle.IDLE_TIMEOUT, browser_idle_timeout_s=0.2
        ),
        logger=Mock(),
        _ensure_browser=AsyncMock(return_value=browser),
        _scrape_url_with_depth=AsyncMock(),
        _cleanup=AsyncMock(),
    )
    state._cleanup_after_idle = lambda: PlaywrightScraperAgent._cleanup_after_idle(state)
    request = WebScrapingRequest(links=[MediaLink(url="https://example.test/")], max_pages=1)
    result = await asyncio.wait_for(PlaywrightScraperAgent._do_scrape(state, request, None), timeout=0.05)
    assert result == ([], []) and state._active_ops == 0
    assert not state._cleanup.called
    await state._idle_cleanup_task
    state._cleanup.assert_awaited_once_with(only_idle=True)


def test_timeout_before_queued_schedule_closes_unstarted_coroutine(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import inspect

    from rustic_ai.playwright.agent import PlaywrightEventLoopThread

    loop = PlaywrightEventLoopThread()
    blocked, unblock, cancellation_queued, entered = (threading.Event() for _ in range(4))

    def hold_loop():
        blocked.set()
        assert unblock.wait(2), "Test did not release the loop callback"

    async def work():
        entered.set()
        return "unexpected"

    coro = work()
    try:
        loop.start()
        event_loop = loop._loop
        assert event_loop is not None
        original_schedule = event_loop.call_soon_threadsafe

        def schedule(callback, *args, **kwargs):
            result = original_schedule(callback, *args, **kwargs)
            if getattr(callback, "__name__", None) == "_cancel_owned_task":
                cancellation_queued.set()
            return result

        monkeypatch.setattr(event_loop, "call_soon_threadsafe", schedule)
        event_loop.call_soon_threadsafe(hold_loop)
        assert blocked.wait(1)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(loop.run_coroutine, coro, 0.02)
            assert cancellation_queued.wait(1)
            unblock.set()
            with pytest.raises(TimeoutError):
                pending.result(timeout=1)
        assert not entered.is_set()
        assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED
        assert loop.run_coroutine(asyncio.sleep(0, result="healthy"), timeout=1) == "healthy"
    finally:
        unblock.set()
        loop.stop()
        if inspect.getcoroutinestate(coro) == inspect.CORO_CREATED:
            coro.close()


@pytest.mark.asyncio
async def test_idle_expiry_during_new_request_and_renewal_shutdown_leave_no_cleanup_tasks(monkeypatch):
    from types import MethodType, SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from rustic_ai.playwright.agent import BrowserLifecycle

    timers: list[tuple[asyncio.Task, asyncio.Event]] = []
    timer_ready: asyncio.Queue[asyncio.Event] = asyncio.Queue()
    request_started, finish_request = asyncio.Event(), asyncio.Event()
    context = SimpleNamespace(close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    driver = SimpleNamespace(stop=AsyncMock())
    state = SimpleNamespace(
        _active_ops=0,
        _browser_lock=asyncio.Lock(),
        _browser=browser,
        _playwright=driver,
        _initialized=True,
        _idle_cleanup_task=None,
        config=SimpleNamespace(
            parallel_pages=1, browser_lifecycle=BrowserLifecycle.IDLE_TIMEOUT, browser_idle_timeout_s=999
        ),
        logger=Mock(),
        _ensure_browser=AsyncMock(return_value=browser),
    )

    async def timer_sleep(duration):
        assert duration == 999
        release = asyncio.Event()
        task = asyncio.current_task()
        assert task is not None
        timers.append((task, release))
        timer_ready.put_nowait(release)
        await release.wait()

    async def scrape(url, depth, context, request, *args):
        if request.id == "second":
            request_started.set()
            await finish_request.wait()

    state._scrape_url_with_depth = scrape
    state._cleanup = MethodType(PlaywrightScraperAgent._cleanup, state)
    state._cleanup_after_idle = MethodType(PlaywrightScraperAgent._cleanup_after_idle, state)
    monkeypatch.setattr(asyncio, "sleep", timer_sleep)

    def request(id):
        return WebScrapingRequest(id=id, links=[MediaLink(url="https://example.test/")], max_pages=1)

    active = None
    try:
        await PlaywrightScraperAgent._do_scrape(state, request("first"), None)
        first_timer = state._idle_cleanup_task
        expire_first = await asyncio.wait_for(timer_ready.get(), 1)
        active = asyncio.create_task(PlaywrightScraperAgent._do_scrape(state, request("second"), None))
        await asyncio.wait_for(request_started.wait(), 1)
        assert state._active_ops == 1
        expire_first.set()
        await asyncio.wait_for(first_timer, 1)
        browser.close.assert_not_awaited()
        driver.stop.assert_not_awaited()
        assert state._initialized

        finish_request.set()
        await asyncio.wait_for(active, 1)
        assert state._active_ops == 0
        await asyncio.wait_for(timer_ready.get(), 1)
        second_timer = state._idle_cleanup_task
        await PlaywrightScraperAgent._do_scrape(state, request("third"), None)
        renewed_timer = state._idle_cleanup_task
        await asyncio.wait_for(timer_ready.get(), 1)
        assert renewed_timer is not second_timer
        with pytest.raises(asyncio.CancelledError):
            await second_timer
        assert state._idle_cleanup_task is renewed_timer and not renewed_timer.done()
        browser.close.assert_not_awaited()

        await PlaywrightScraperAgent._shutdown_browser(state)
        assert state._idle_cleanup_task is None
        assert renewed_timer.cancelled() and all(task.done() for task, _ in timers)
        browser.close.assert_awaited_once()
        driver.stop.assert_awaited_once()
        assert not state._initialized and state._active_ops == 0
    finally:
        finish_request.set()
        if active is not None and not active.done():
            await active
        pending = state._idle_cleanup_task
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
