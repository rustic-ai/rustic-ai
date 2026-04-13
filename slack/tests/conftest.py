"""Pytest configuration for Slack tests"""

from pathlib import Path
import sys

import pytest

# Add src to path so imports work
slack_src = Path(__file__).parent.parent / "src"
if str(slack_src) not in sys.path:
    sys.path.insert(0, str(slack_src))


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "requires_tokens: mark test as requiring Slack tokens"
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy"""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()
