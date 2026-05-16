import pytest

from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


@pytest.fixture
def generator():
    """Provide a GemstoneGenerator for creating message IDs."""
    return GemstoneGenerator(1)
