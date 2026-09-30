import pytest

from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


@pytest.fixture
def generator():
    return GemstoneGenerator(1)
