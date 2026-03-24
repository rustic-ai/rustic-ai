"""Tests for NATSStateManager."""

import os

import pytest

from rustic_ai.core.state.manager.state_manager import StateManager
from rustic_ai.nats.state.manager import NATSStateManager

from rustic_ai.testing.state.base_test_state_mgr import BaseTestStateManager


class TestNATSStateManager(BaseTestStateManager):

    @pytest.fixture
    def state_manager(self, request) -> StateManager:
        nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
        return NATSStateManager(servers=[nats_url])
