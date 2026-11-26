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
