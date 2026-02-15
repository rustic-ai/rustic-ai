"""
Tests for plugin dependency injection in LLM Agent.

This module tests the feature that allows LLM Agent plugins (RequestPreprocessor,
LLMCallWrapper, ResponsePostprocessor) to access injected dependencies via self.get_dep(agent, name).
"""

from typing import Any, List, Optional

from pydantic import BaseModel
import pytest
import shortuuid

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.plugins.llm_call_wrapper import LLMCallWrapper
from rustic_ai.llm_agent.plugins.request_preprocessor import RequestPreprocessor
from rustic_ai.llm_agent.plugins.response_postprocessor import ResponsePostprocessor

from rustic_ai.testing.helpers import wrap_agent_for_testing

# =============================================================================
# Test Dependencies and Resolvers
# =============================================================================


class SimpleLogger:
    """A simple logger dependency for testing."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.logs: List[str] = []

    def log(self, message: str) -> None:
        self.logs.append(f"{self.prefix}{message}")


class SimpleLoggerResolver(DependencyResolver[SimpleLogger]):
    """Resolver that creates SimpleLogger instances."""

    def __init__(self, prefix: str = "") -> None:
        super().__init__()
        self.prefix = prefix

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> SimpleLogger:
        return SimpleLogger(prefix=self.prefix)


class SimpleConfig:
    """A simple config dependency for testing."""

    def __init__(self, setting_a: str, setting_b: int):
        self.setting_a = setting_a
        self.setting_b = setting_b


class SimpleConfigResolver(DependencyResolver[SimpleConfig]):
    """Resolver that creates SimpleConfig instances."""

    def __init__(self, setting_a: str = "default", setting_b: int = 42) -> None:
        super().__init__()
        self.setting_a = setting_a
        self.setting_b = setting_b

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> SimpleConfig:
        return SimpleConfig(setting_a=self.setting_a, setting_b=self.setting_b)


# =============================================================================
# Test Plugins with Dependency Injection using self.get_dep()
# =============================================================================


class LoggingPreprocessor(RequestPreprocessor):
    """A request preprocessor that uses a logger dependency via self.get_dep(agent, name)."""

    depends_on: List[str] = ["test_logger"]

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        logger = self.get_dep(agent, "test_logger")
        logger.log("preprocess called")
        return request


class LoggingWrapper(LLMCallWrapper):
    """An LLM call wrapper that uses logger and config dependencies via self.get_dep(agent, name)."""

    depends_on: List[str] = ["test_logger", "test_config"]

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        logger = self.get_dep(agent, "test_logger")
        config = self.get_dep(agent, "test_config")
        logger.log(f"wrapper preprocess with config: {config.setting_a}")
        return request

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        logger = self.get_dep(agent, "test_logger")
        logger.log("wrapper postprocess called")
        return None


class LoggingPostprocessor(ResponsePostprocessor):
    """A response postprocessor that uses a logger dependency via self.get_dep(agent, name)."""

    depends_on: List[str] = ["test_logger"]

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        logger = self.get_dep(agent, "test_logger")
        logger.log("postprocess called")
        return None


class NoDependencyPlugin(LLMCallWrapper):
    """A plugin that doesn't declare any dependencies."""

    preprocess_called: bool = False
    postprocess_called: bool = False

    def preprocess(
        self,
        agent: Agent,
        ctx,
        request: ChatCompletionRequest,
        llm: LLM,
    ) -> ChatCompletionRequest:
        NoDependencyPlugin.preprocess_called = True
        return request

    def postprocess(
        self,
        agent: Agent,
        ctx,
        final_prompt: ChatCompletionRequest,
        llm_response: ChatCompletionResponse,
        llm: LLM,
    ) -> Optional[List[BaseModel]]:
        NoDependencyPlugin.postprocess_called = True
        return None


# =============================================================================
# Mock LLM
# =============================================================================


class MockLLM(LLM):
    """Mock LLM for testing."""

    def completion(self, prompt: ChatCompletionRequest, model: Optional[str] = None) -> ChatCompletionResponse:
        return ChatCompletionResponse(choices=[])

    async def async_completion(
        self, prompt: ChatCompletionRequest, model: Optional[str] = None
    ) -> ChatCompletionResponse:
        return ChatCompletionResponse(choices=[])

    @property
    def model(self) -> str:
        return "mock-model"

    def get_config(self) -> dict:
        return {"model": self.model}


class MockLLMResolver(DependencyResolver[LLM]):
    """Resolver for MockLLM."""

    def resolve(self, org_id: str, guild_id: str, agent_id: Optional[str] = None) -> LLM:
        return MockLLM()


# =============================================================================
# Tests
# =============================================================================


class TestPluginDependencyInjection:
    """Tests for plugin dependency injection functionality."""

    @pytest.fixture(autouse=True)
    def reset_captured_state(self):
        """Reset captured state before each test."""
        NoDependencyPlugin.preprocess_called = False
        NoDependencyPlugin.postprocess_called = False
        yield

    def _create_agent_with_plugins(
        self,
        plugins: dict,
        additional_dependencies: List[str],
        dependency_map: dict,
    ):
        """Helper to create an agent with specified plugins and dependencies."""
        config = LLMAgentConfig(
            model="mock-model",
            **plugins,
        )

        agent_spec = (
            AgentBuilder(LLMAgent)
            .set_id("test-agent")
            .set_name("TestLLMAgent")
            .set_description("Test agent with plugin dependencies")
            .set_properties(config.model_dump())
            .set_additional_dependencies(additional_dependencies)
            .build_spec()
        )

        # Add LLM dependency to the dependency map
        dependency_map["llm"] = DependencySpec(
            class_name=get_qualified_class_name(MockLLMResolver),
        )

        # Add filesystem dependency required by LLMAgent's invoke_llm_with_attachments processor
        dependency_map["filesystem"] = DependencySpec(
            class_name=FileSystemResolver.get_qualified_class_name(),
            properties={
                "path_base": f"/tmp/tests/{shortuuid.uuid()}",
                "protocol": "file",
                "storage_options": {
                    "auto_mkdir": True,
                },
            },
        )

        agent, results = wrap_agent_for_testing(agent_spec, dependency_map)
        return agent, results

    def test_plugin_get_dep_resolves_dependency(self):
        """Test that plugins can resolve dependencies via self.get_dep(agent, name)."""
        dependency_map = {
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
                properties={"prefix": "[TEST] "},
            ),
        }

        agent, _ = self._create_agent_with_plugins(
            plugins={"request_preprocessors": [LoggingPreprocessor()]},
            additional_dependencies=["test_logger"],
            dependency_map=dependency_map,
        )

        # Create a plugin and use get_dep with agent
        plugin = LoggingPreprocessor()

        # Use get_dep to retrieve the dependency
        logger = plugin.get_dep(agent, "test_logger")

        assert isinstance(logger, SimpleLogger)
        assert logger.prefix == "[TEST] "

    def test_plugin_get_dep_multiple_dependencies(self):
        """Test that plugins can resolve multiple dependencies."""
        dependency_map = {
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
                properties={"prefix": "[WRAP] "},
            ),
            "test_config": DependencySpec(
                class_name=get_qualified_class_name(SimpleConfigResolver),
                properties={"setting_a": "custom_value", "setting_b": 100},
            ),
        }

        agent, _ = self._create_agent_with_plugins(
            plugins={"llm_request_wrappers": [LoggingWrapper()]},
            additional_dependencies=["test_logger", "test_config"],
            dependency_map=dependency_map,
        )

        plugin = LoggingWrapper()

        logger = plugin.get_dep(agent, "test_logger")
        config = plugin.get_dep(agent, "test_config")

        assert isinstance(logger, SimpleLogger)
        assert isinstance(config, SimpleConfig)
        assert config.setting_a == "custom_value"
        assert config.setting_b == 100

    def test_plugin_get_dep_caches_via_resolver(self):
        """Test that get_dep returns cached instances from the resolver."""
        dependency_map = {
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
            ),
        }

        agent, _ = self._create_agent_with_plugins(
            plugins={},
            additional_dependencies=["test_logger"],
            dependency_map=dependency_map,
        )

        plugin = LoggingPreprocessor()

        # Call get_dep multiple times
        logger1 = plugin.get_dep(agent, "test_logger")
        logger2 = plugin.get_dep(agent, "test_logger")

        # Should return the same cached instance (resolver caches)
        assert logger1 is logger2

    def test_plugin_get_dep_raises_for_missing_dependency(self):
        """Test that get_dep raises ValueError for missing dependencies."""
        dependency_map: dict[str, Any] = {}  # No dependencies configured

        agent, _ = self._create_agent_with_plugins(
            plugins={},
            additional_dependencies=[],
            dependency_map=dependency_map,
        )

        plugin = LoggingPreprocessor()

        with pytest.raises(ValueError) as exc_info:
            plugin.get_dep(agent, "nonexistent_dep")

        assert "not found in agent's dependency resolvers" in str(exc_info.value)

    def test_additional_dependencies_field_on_agent_spec(self):
        """Test that additional_dependencies field is properly set on AgentSpec."""
        config = LLMAgentConfig(model="mock-model")

        agent_spec = (
            AgentBuilder(LLMAgent)
            .set_id("test-agent")
            .set_name("TestAgent")
            .set_description("Test")
            .set_properties(config.model_dump())
            .set_additional_dependencies(["dep1", "dep2", "dep3"])
            .build_spec()
        )

        assert agent_spec.additional_dependencies == ["dep1", "dep2", "dep3"]

    def test_add_additional_dependency_method(self):
        """Test the add_additional_dependency builder method."""
        config = LLMAgentConfig(model="mock-model")

        agent_spec = (
            AgentBuilder(LLMAgent)
            .set_id("test-agent")
            .set_name("TestAgent")
            .set_description("Test")
            .set_properties(config.model_dump())
            .add_additional_dependency("dep1")
            .add_additional_dependency("dep2")
            .build_spec()
        )

        assert "dep1" in agent_spec.additional_dependencies
        assert "dep2" in agent_spec.additional_dependencies

    def test_dependencies_are_loaded_for_agent(self):
        """Test that additional_dependencies are loaded into agent's resolver map."""
        dependency_map = {
            "test_logger": DependencySpec(
                class_name=get_qualified_class_name(SimpleLoggerResolver),
            ),
            "test_config": DependencySpec(
                class_name=get_qualified_class_name(SimpleConfigResolver),
            ),
        }

        agent, _ = self._create_agent_with_plugins(
            plugins={},
            additional_dependencies=["test_logger", "test_config"],
            dependency_map=dependency_map,
        )

        # Verify that the dependencies are in the agent's resolvers
        assert "test_logger" in agent._dependency_resolvers
        assert "test_config" in agent._dependency_resolvers

    def test_plugin_depends_on_field_default_empty(self):
        """Test that depends_on field defaults to empty list."""
        wrapper = NoDependencyPlugin()
        assert wrapper.depends_on == []


class TestPluginDependencyInjectionEdgeCases:
    """Edge case tests for plugin dependency injection."""

    def test_base_plugin_kind_field(self):
        """Test that the kind field is properly set on plugins."""
        plugin = LoggingPreprocessor()
        expected_kind = f"{LoggingPreprocessor.__module__}.{LoggingPreprocessor.__qualname__}"
        assert plugin.kind == expected_kind
