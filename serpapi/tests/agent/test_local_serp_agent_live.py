"""
End-to-end checks of LocalSERPAgent on this machine: no mocks, a real browser, real search engines.

These drive the locally installed Chrome (or bundled Chromium) and hit live search engines, so they are opt-in:

    RUSTIC_LOCAL_SERP_LIVE=1 pytest serpapi/tests/agent/test_local_serp_agent_live.py -v

They use the real browser profile (the one `python -m rustic_ai.serpapi.local_setup` prepares), which only one browser
can open at a time, so they run one at a time even under pytest-xdist. Stop any running LocalSERPAgent guild first.
The headed test opens a minimized Chrome window; if Google shows a CAPTCHA the window pops up for you to solve.
"""

import os
import re
from typing import Iterator

import pytest

from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.serpapi.agent import SERPQuery, SERPResults
from rustic_ai.serpapi.local_agent import LocalSERPAgent
from rustic_ai.serpapi.local_browser import default_profile_root

from rustic_ai.testing.helpers import wrap_agent_for_testing

pytestmark = pytest.mark.skipif(
    os.getenv("RUSTIC_LOCAL_SERP_LIVE") != "1", reason="set RUSTIC_LOCAL_SERP_LIVE=1 to search live engines"
)

try:
    import fcntl
except ImportError:  # Windows: no cross-process lock; run these tests without -n
    fcntl = None  # type: ignore[assignment]

QUERY = "python programming language"


@pytest.fixture(autouse=True)
def one_browser_at_a_time() -> Iterator[None]:
    """Hold a lock for the whole test so parallel workers do not compete for the shared browser profile."""
    if fcntl is None:
        yield
        return
    os.makedirs(default_profile_root(), exist_ok=True)
    with open(os.path.join(default_profile_root(), ".live-tests.lock"), "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)  # released when the file is closed
        yield


@pytest.fixture
def agent_id(request) -> str:
    return "live_" + re.sub(r"\W+", "_", request.node.name).strip("_")


def run_search(generator, agent_id: str, engine: str, num: int = 5, **properties) -> Message:
    """Build a real LocalSERPAgent, send it one query, and return the single message it replies with."""
    agent, results = wrap_agent_for_testing(
        AgentBuilder(LocalSERPAgent)
        .set_name("LiveLocalSerpAgent")
        .set_id(agent_id)
        .set_description("LocalSERPAgent against live search engines")
        # Close the browser after the search so each test starts clean and leaves nothing running.
        .set_properties({"close_browser_after_request": True, **properties})
        .build_spec(),
    )
    query = Message(
        topics="default_topic",
        sender=AgentTag(id="tester", name="tester"),
        format=get_qualified_class_name(SERPQuery),
        payload={"engine": engine, "query": QUERY, "num": num, "id": f"live-{engine}"},
        id_obj=generator.get_id(Priority.NORMAL),
    )
    agent._on_message(query)

    assert len(results) == 1, f"expected one reply, got {len(results)}"
    return results[0]


def assert_found_results(reply: Message, engine: str, num: int) -> SERPResults:
    assert reply.format == get_qualified_class_name(SERPResults), f"{engine} search failed: {reply.payload}"
    result = SERPResults.model_validate(reply.payload)

    assert (result.engine, result.query, result.id) == (engine, QUERY, f"live-{engine}")
    assert 0 < result.count <= num
    assert result.count == len(result.results)

    urls = [link.url for link in result.results]
    assert all(url.startswith(("http://", "https://")) for url in urls), urls
    assert len(set(urls)) == len(urls), f"duplicate results: {urls}"
    assert not [url for url in urls if "google.com/goto" in url], "Google redirect links were not resolved"
    # A query this common should surface python.org among the top results on any engine.
    assert any("python.org" in url for url in urls), urls

    for position, link in enumerate(result.results, start=1):
        assert link.metadata is not None
        assert link.metadata["title"], f"result {position} has no title"
        assert link.metadata["search_position"] == position
        assert link.metadata["engine"] == engine
        assert link.metadata["source"] == "local_browser"
    return result


@pytest.mark.parametrize("engine", ["duckduckgo", "bing"])
def test_headless_search_finds_results(generator, agent_id, engine):
    assert_found_results(run_search(generator, agent_id, engine), engine, num=5)


def test_pagination_collects_more_than_one_page(generator, agent_id):
    result = assert_found_results(run_search(generator, agent_id, "bing", num=15), "bing", num=15)
    assert result.count > 10, f"expected results from a second page, got {result.count}"


def test_headed_google_search_finds_results(generator, agent_id):
    reply = run_search(generator, agent_id, "google", headless=False, captcha_wait_s=60)
    assert_found_results(reply, "google", num=5)
