import pytest

# from agents.llm.phi_2.phi_agent import LLMPhiAgent
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.messaging.client.message_tracking_client import (
    MessageTrackingClient,
)
from rustic_ai.core.messaging.core.message import Message
from rustic_ai.core.utils import class_utils
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class TestGetClassUtils:

    # Correctly returns the Agent subclass when given a valid full class name
    def test_get_agent_class_valid(self):
        agent_class = class_utils.get_agent_class(ProbeAgent.get_qualified_class_name())
        assert agent_class == ProbeAgent

    # Error on invalid class
    def test_get_agent_class_invalid(self):
        with pytest.raises(TypeError):
            class_utils.get_agent_class("rustic_ai.core.InvalidClass")

    # Error on non-agent class
    def test_get_agent_class_non_agent(self):
        with pytest.raises(TypeError):
            class_utils.get_agent_class(get_qualified_class_name(Message))

    # Correctly loads an ExecutionEngine subclass
    def test_get_execution_class_valid(self):
        execution_class = class_utils.get_execution_class(
            "rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine"
        )
        assert execution_class == SyncExecutionEngine

    # Error on invalid class
    def test_get_execution_class_invalid(self):
        with pytest.raises(TypeError):
            class_utils.get_execution_class("rustic_ai.core.InvalidClass")

    # Error on non-execution engine class
    def test_get_execution_class_non_execution_engine(self):
        with pytest.raises(TypeError):
            class_utils.get_execution_class(get_qualified_class_name(Message))

    # Correctly loads a Client class
    def test_get_client_class_valid(self):
        client_class = class_utils.get_client_class(MessageTrackingClient.get_qualified_class_name())
        assert client_class == MessageTrackingClient

    # Error on invalid class
    def test_get_client_class_invalid(self):
        with pytest.raises(TypeError):
            class_utils.get_client_class("rustic_ai.core.InvalidClass")

    # Error on non-client class
    def test_get_client_class_non_client(self):
        with pytest.raises(TypeError):
            class_utils.get_client_class(get_qualified_class_name(Message))
