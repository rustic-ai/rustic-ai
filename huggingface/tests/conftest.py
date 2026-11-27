import time

import pytest


@pytest.fixture
def wait_for_model_response():
    """Wait for a local model's actual response without a fixed inference sleep."""

    def wait(probe, timeout=600):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages = probe.get_messages()
            if messages:
                return messages
            time.sleep(0.1)
        raise AssertionError(f"No model response received within {timeout} seconds")

    return wait
