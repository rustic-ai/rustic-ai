"""NATS test fixtures - expects a running NATS server (start externally before tests).

Set RUN_NATS_TESTS=true to run these tests (they are skipped by default).
Optionally set NATS_URL to override the server address (default: nats://localhost:4222).
"""

import asyncio
import os
import threading

import pytest


def _get_nats_url() -> str:
    """Get the NATS server URL from environment or use default."""
    return os.environ.get("NATS_URL", "nats://localhost:4222")


def pytest_collection_modifyitems(config, items):
    """Skip NATS tests unless RUN_NATS_TESTS=true."""
    if os.environ.get("RUN_NATS_TESTS", "").lower() != "true":
        nats_tests_dir = os.path.dirname(__file__)
        skip = pytest.mark.skip(reason="Set RUN_NATS_TESTS=true to run NATS integration tests")
        for item in items:
            if str(item.fspath).startswith(nats_tests_dir):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def nats_url():
    """Return the NATS server URL."""
    return _get_nats_url()


@pytest.fixture
def nats_client(nats_url):
    """Provide a pre-connected NATS client with its own event loop thread."""
    import nats

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True, name="test-nats-loop")
    thread.start()

    future = asyncio.run_coroutine_threadsafe(nats.connect(nats_url), loop)
    client = future.result(timeout=10)

    yield client

    try:
        asyncio.run_coroutine_threadsafe(client.drain(), loop).result(timeout=5)
    except Exception:
        pass
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
