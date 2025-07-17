import multiprocessing

import pytest


@pytest.fixture(autouse=True, scope="session")
def configure_multiprocessing():
    """Configure multiprocessing to use spawn method to avoid fork() warnings in tests."""
    # Set spawn method to avoid fork() deprecation warnings in multi-threaded environments
    # This is especially important for multiprocessing tests running under pytest
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method may already be set, which is fine
        pass

    yield


@pytest.fixture
def client_properties():
    return {"client_id": "client1", "name": "client1"}
