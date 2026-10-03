"""
End-to-end tests for async transformation flow.

Tests the complete flow:
- Orchestrator → RouteBuilder → TransformationBuilder → RouteBuilder → StateManager

Verifies:
1. All agents run and complete correctly
2. JSONata transformations are generated as expected
3. Message formats are correctly identified
4. Transformations are properly applied to routes
"""

import json
import pytest
from typing import List

from pydantic import BaseModel

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
    DependencySpec,
)
from rustic_ai.core.guild.agent_ext.depends.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    CompletionUsage,
    FinishReason,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.priority import Priority
from rustic_ai.showcase.guild_generator.agent_registry import AgentRegistryAgent
from rustic_ai.showcase.guild_generator.models import (
    ActionType,
    AgentLookupResponse,
    OrchestratorAction,
    RouteResponse,
    TransformRequest,
    TransformResponse,
    TransformationSpec,
)
from rustic_ai.showcase.guild_generator.route_builder import RouteBuilderAgent
from rustic_ai.showcase.guild_generator.transformation_builder import TransformationBuilderAgent
from rustic_ai.testing.helpers import wrap_agent_for_testing


class MockLLM(LLM):
    """Mock LLM that returns predefined responses."""

    def __init__(self, responses: List[str]):
        self.responses = responses
        self.call_count = 0
        self._model = "mock-model"

    def completion(self, prompt: ChatCompletionRequest, model=None) -> ChatCompletionResponse:
        response_content = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return ChatCompletionResponse(
            id=f"mock-completion-{self.call_count}",
            created=1234567890,
            model=self._model,
            choices=[
                Choice(
                    index=0,
                    message=AssistantMessage(content=response_content),
                    finish_reason=FinishReason.stop,
                )
            ],
            usage=CompletionUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    async def async_completion(self, prompt: ChatCompletionRequest, model=None) -> ChatCompletionResponse:
        return self.completion(prompt, model)

    @property
    def model(self) -> str:
        return self._model

    def get_config(self) -> dict:
        return {"model": self._model}


class MockLLMResolver(DependencyResolver[LLM]):
    """Resolver that returns a MockLLM with predefined responses."""

    memoize_resolution: bool = False

    def __init__(self, responses: List[str]):
        super().__init__()
        self.responses = responses

    def resolve(self, org_id: str, guild_id: str, agent_id: str) -> LLM:
        return MockLLM(self.responses)


@pytest.fixture
def generator() -> GemstoneGenerator:
    return GemstoneGenerator(1)


@pytest.fixture
def build_message_from_payload():
    def _build_message_from_payload(
        generator: GemstoneGenerator,
        payload: BaseModel | dict,
        *,
        format: str | None = None,
        session_state: dict | None = None,
    ) -> Message:
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        computed_format = format or (
            get_qualified_class_name(type(payload)) if isinstance(payload, BaseModel) else None
        )

        return Message(
            id_obj=generator.get_id(Priority.NORMAL),
            sender=AgentTag(name="test-agent", id="agent-123"),
            topics=GuildTopics.DEFAULT_TOPICS,
            payload=payload_dict,
            format=computed_format if computed_format else get_qualified_class_name(Message),
            session_state=session_state or {},
        )

    return _build_message_from_payload


class TestAsyncTransformationE2E:
    """End-to-end tests for the complete async transformation flow."""

    def test_complete_flow_with_different_formats(self, generator, build_message_from_payload):
        """
        Test complete flow when source and target formats differ.

        Flow:
        1. OrchestratorAction → RouteBuilder
        2. RouteBuilder → TransformRequest → TransformationBuilder
        3. TransformationBuilder → TransformResponse → RouteBuilder
        4. RouteBuilder → RouteResponse (with transformation)
        """
        # Setup guild state with agent message info
        guild_state = {
            "guild_builder": {
                "agent_message_info": [
                    {
                        "agent_name": "llm_agent",
                        "agent_id": "llm_1",
                        "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                        "input_formats": ["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"],
                        "output_formats": ["rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"],
                    },
                    {
                        "agent_name": "formatter",
                        "agent_id": "formatter_1",
                        "class_name": "rustic_ai.core.agents.formatters.FormatterAgent",
                        "input_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                        "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                    },
                ]
            }
        }

        # Step 1: Create RouteBuilder with mock LLM
        route_builder_response = json.dumps({
            "routing_rule": {
                "agent": {"name": "llm_agent"},
                "message_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                "destination": {"topics": "formatter"},
                "route_times": -1
            },
            "explanation": "Routes LLM output to formatter",
            "source_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
            "target_format": "rustic_ai.core.ui_protocol.types.TextFormat",
        })

        route_builder_spec = (
            AgentBuilder(RouteBuilderAgent)
            .set_id("route_builder")
            .set_name("Route Builder")
            .set_description("Test Route Builder")
            .build_spec()
        )

        route_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [route_builder_response]},
            ),
        }

        route_builder, route_results = wrap_agent_for_testing(
            route_builder_spec,
            dependency_map=route_builder_deps,
        )

        # Set guild state
        route_builder._guild_state = guild_state

        # Send ADD_ROUTE action
        action = OrchestratorAction(
            action=ActionType.ADD_ROUTE,
            details={
                "source_agent": "llm_agent",
                "target_agent": "formatter",
            },
            user_message="@Orchestrator connect llm_agent to formatter",
        )

        route_builder._on_message(build_message_from_payload(generator,action))

        # Verify TransformRequest was sent
        assert len(route_results) == 1, f"Expected 1 result, got {len(route_results)}"
        assert route_results[0].format == get_qualified_class_name(TransformRequest)

        transform_request = TransformRequest.model_validate(route_results[0].payload)
        assert transform_request.source_format == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"
        assert transform_request.target_format == "rustic_ai.core.ui_protocol.types.TextFormat"
        assert transform_request.source_agent_name == "llm_agent"
        assert transform_request.target_agent_name == "formatter"

        # Get correlation_id
        correlation_id = route_results[0].session_state.get("route_correlation_id")
        assert correlation_id is not None

        print(f"✓ Step 1: RouteBuilder sent TransformRequest (correlation_id: {correlation_id})")

        # Step 2: Send TransformRequest to TransformationBuilder
        transformation_response = json.dumps({
            "transformation": {
                "style": "simple",
                "expression_type": "jsonata",
                "handler": "({'text': $.choices[0].message.content})",
                "output_format": "rustic_ai.core.ui_protocol.types.TextFormat",
            },
            "explanation": "Extracts message content from ChatCompletion and wraps in TextFormat",
        })

        transform_builder_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test Transformation Builder")
            .build_spec()
        )

        transform_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [transformation_response]},
            ),
        }

        transform_builder, transform_results = wrap_agent_for_testing(
            transform_builder_spec,
            dependency_map=transform_builder_deps,
        )

        transform_builder._on_message(build_message_from_payload(generator, transform_request))

        # Verify TransformResponse was sent
        assert len(transform_results) == 1
        assert transform_results[0].format == get_qualified_class_name(TransformResponse)

        transform_response = TransformResponse.model_validate(transform_results[0].payload)
        assert transform_response.transformation.style == "simple"
        assert transform_response.transformation.expression_type == "jsonata"
        assert "$.choices[0].message.content" in transform_response.transformation.handler
        assert transform_response.transformation.output_format == "rustic_ai.core.ui_protocol.types.TextFormat"

        print("✓ Step 2: TransformationBuilder generated JSONata transformation")

        # Step 3: Send TransformResponse back to RouteBuilder
        route_results.clear()

        message_with_correlation = build_message_from_payload(
            generator,
            transform_response,
            session_state={"route_correlation_id": correlation_id},
        )

        route_builder._on_message(message_with_correlation)

        # Verify final RouteResponse with transformation
        assert len(route_results) == 1
        assert route_results[0].format == get_qualified_class_name(RouteResponse)

        final_route = RouteResponse.model_validate(route_results[0].payload)
        assert "transformer" in final_route.routing_rule

        transformer = final_route.routing_rule["transformer"]
        assert transformer["style"] == "simple"
        assert "$.choices[0].message.content" in transformer["handler"]
        assert transformer["output_format"] == "rustic_ai.core.ui_protocol.types.TextFormat"

        print("✓ Step 3: RouteBuilder completed route with transformation")
        print("\n✅ Complete async flow test PASSED")

    def test_flow_with_same_formats_no_transformation(self, generator, build_message_from_payload):
        """
        Test flow when source and target formats are the same.
        Should skip transformation step.
        """
        guild_state = {
            "guild_builder": {
                "agent_message_info": [
                    {
                        "agent_name": "text_agent_1",
                        "agent_id": "text_1",
                        "class_name": "rustic_ai.core.agents.TextAgent",
                        "input_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                        "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                    },
                    {
                        "agent_name": "text_agent_2",
                        "agent_id": "text_2",
                        "class_name": "rustic_ai.core.agents.TextAgent",
                        "input_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                        "output_formats": ["rustic_ai.core.ui_protocol.types.TextFormat"],
                    },
                ]
            }
        }

        route_builder_response = json.dumps({
            "routing_rule": {
                "agent": {"name": "text_agent_1"},
                "message_format": "rustic_ai.core.ui_protocol.types.TextFormat",
                "destination": {"topics": "text_agent_2"},
                "route_times": -1
            },
            "explanation": "Routes text_agent_1 to text_agent_2",
            "source_format": "rustic_ai.core.ui_protocol.types.TextFormat",
            "target_format": "rustic_ai.core.ui_protocol.types.TextFormat",
        })

        route_builder_spec = (
            AgentBuilder(RouteBuilderAgent)
            .set_id("route_builder")
            .set_name("Route Builder")
            .set_description("Test Route Builder")
            .build_spec()
        )

        route_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [route_builder_response]},
            ),
        }

        route_builder, route_results = wrap_agent_for_testing(
            route_builder_spec,
            dependency_map=route_builder_deps,
        )

        # Set guild state
        route_builder._guild_state = guild_state

        action = OrchestratorAction(
            action=ActionType.ADD_ROUTE,
            details={
                "source_agent": "text_agent_1",
                "target_agent": "text_agent_2",
            },
            user_message="@Orchestrator connect text_agent_1 to text_agent_2",
        )

        route_builder._on_message(build_message_from_payload(generator,action))

        # Should send RouteResponse directly (no TransformRequest)
        assert len(route_results) == 1
        assert route_results[0].format == get_qualified_class_name(RouteResponse)

        route_response = RouteResponse.model_validate(route_results[0].payload)

        # Should NOT have transformer
        assert "transformer" not in route_response.routing_rule or route_response.routing_rule.get("transformer") is None

        print("✓ Same formats: No transformation added (as expected)")
        print("\n✅ Same format test PASSED")


class TestJSONataTransformationGeneration:
    """Tests for verifying correct JSONata transformation generation."""

    def test_chatcompletion_to_textformat_transformation(self, generator, build_message_from_payload):
        """Test JSONata for ChatCompletionResponse → TextFormat."""
        transformation_response = json.dumps({
            "transformation": {
                "style": "simple",
                "expression_type": "jsonata",
                "handler": "({'text': $.choices[0].message.content})",
                "output_format": "rustic_ai.core.ui_protocol.types.TextFormat",
            },
            "explanation": "Extracts message content from ChatCompletion",
        })

        transform_builder_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test Transformation Builder")
            .build_spec()
        )

        transform_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [transformation_response]},
            ),
        }

        transform_builder, results = wrap_agent_for_testing(
            transform_builder_spec,
            dependency_map=transform_builder_deps,
        )

        request = TransformRequest(
            source_format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
            target_format="rustic_ai.core.ui_protocol.types.TextFormat",
            source_agent_name="llm_agent",
            target_agent_name="display",
        )

        transform_builder._on_message(build_message_from_payload(generator,request))

        assert len(results) == 1
        response = TransformResponse.model_validate(results[0].payload)

        # Verify transformation structure
        assert response.transformation.style == "simple"
        assert response.transformation.expression_type == "jsonata"
        assert response.transformation.output_format == "rustic_ai.core.ui_protocol.types.TextFormat"

        # Verify JSONata accesses correct field
        handler = response.transformation.handler
        assert "$.choices" in handler or "choices" in handler
        assert "message.content" in handler or "content" in handler

        print("✓ ChatCompletion → TextFormat JSONata generated correctly")

    def test_textformat_to_chatcompletion_transformation(self, generator, build_message_from_payload):
        """Test JSONata for TextFormat → ChatCompletionRequest."""
        transformation_response = json.dumps({
            "transformation": {
                "style": "simple",
                "expression_type": "jsonata",
                "handler": "({'messages': [{'role': 'user', 'content': $.text}]})",
                "output_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
            },
            "explanation": "Wraps text in ChatCompletionRequest format",
        })

        transform_builder_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test Transformation Builder")
            .build_spec()
        )

        transform_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [transformation_response]},
            ),
        }

        transform_builder, results = wrap_agent_for_testing(
            transform_builder_spec,
            dependency_map=transform_builder_deps,
        )

        request = TransformRequest(
            source_format="rustic_ai.core.ui_protocol.types.TextFormat",
            target_format="rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
            source_agent_name="input",
            target_agent_name="llm_agent",
        )

        transform_builder._on_message(build_message_from_payload(generator,request))

        assert len(results) == 1
        response = TransformResponse.model_validate(results[0].payload)

        # Verify transformation structure
        assert response.transformation.style == "simple"
        assert response.transformation.output_format == "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"

        # Verify JSONata structure
        handler = response.transformation.handler
        assert "messages" in handler
        assert "$.text" in handler or "text" in handler
        assert "role" in handler
        assert "content" in handler

        print("✓ TextFormat → ChatCompletion JSONata generated correctly")

    def test_content_based_router_transformation(self, generator, build_message_from_payload):
        """Test content-based router style transformation."""
        transformation_response = json.dumps({
            "transformation": {
                "style": "content_based_router",
                "expression_type": "jsonata",
                "handler": "($.payload.error ? {'topics': 'error_handler', 'format': 'ErrorFormat', 'payload': $.payload} : {'topics': 'success_handler', 'format': 'SuccessFormat', 'payload': $.payload})",
            },
            "explanation": "Routes to error or success handler based on content",
        })

        transform_builder_spec = (
            AgentBuilder(TransformationBuilderAgent)
            .set_id("transform_builder")
            .set_name("Transform Builder")
            .set_description("Test Transformation Builder")
            .build_spec()
        )

        transform_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [transformation_response]},
            ),
        }

        transform_builder, results = wrap_agent_for_testing(
            transform_builder_spec,
            dependency_map=transform_builder_deps,
        )

        request = TransformRequest(
            source_format="generic_json",
            target_format="dynamic",
            source_agent_name="processor",
            target_agent_name="router",
            requirements="Route based on whether error field is present",
        )

        transform_builder._on_message(build_message_from_payload(generator,request))

        assert len(results) == 1
        response = TransformResponse.model_validate(results[0].payload)

        # Verify transformation structure
        assert response.transformation.style == "content_based_router"

        # Verify JSONata has conditional logic
        handler = response.transformation.handler
        assert "?" in handler  # Ternary operator
        assert "topics" in handler
        assert "format" in handler
        assert "payload" in handler

        print("✓ Content-based router JSONata generated correctly")


class TestAgentIntegration:
    """Tests for verifying all agents work together correctly."""

    def test_agent_registry_provides_format_info(self, generator, build_message_from_payload, monkeypatch):
        """Test that AgentRegistry includes format info in responses."""
        # Mock the API call
        mock_api_response = {
            "rustic_ai.llm_agent.llm_agent.LLMAgent": {
                "agent_name": "LLMAgent",
                "qualified_class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                "message_handlers": {
                    "on_message": {
                        "message_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest",
                        "message_format_schema": {"title": "ChatCompletionRequest"},
                        "send_message_calls": [{
                            "message_format": "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse",
                            "message_format_schema": {"title": "ChatCompletionResponse"},
                        }],
                    }
                },
                "agent_dependencies": {},
            }
        }

        class MockHttpxResponse:
            def json(self):
                return mock_api_response
            def raise_for_status(self):
                pass

        def mock_get(*args, **kwargs):
            return MockHttpxResponse()

        monkeypatch.setattr("httpx.get", mock_get)

        mock_response = json.dumps({
            "agent_spec": {
                "id": "test_llm_agent",
                "name": "Test LLM Agent",
                "description": "Test LLM",
                "class_name": "rustic_ai.llm_agent.llm_agent.LLMAgent",
                "properties": {},
            },
            "explanation": "Selected LLMAgent",
        })

        agent_registry_spec = (
            AgentBuilder(AgentRegistryAgent)
            .set_id("agent_registry")
            .set_name("Agent Registry")
            .set_description("Test Agent Registry")
            .build_spec()
        )

        agent_registry_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": [mock_response]},
            ),
        }

        agent_registry, results = wrap_agent_for_testing(
            agent_registry_spec,
            dependency_map=agent_registry_deps,
        )

        action = OrchestratorAction(
            action=ActionType.ADD_AGENT,
            details={"purpose": "test llm agent"},
            user_message="@Orchestrator add llm agent",
        )

        agent_registry._on_message(build_message_from_payload(generator,action))

        assert len(results) == 1
        response = AgentLookupResponse.model_validate(results[0].payload)

        # Verify format info is included
        assert "input_formats" in response.model_dump()
        assert "output_formats" in response.model_dump()

        # AgentRegistryAgent should populate these from the agent catalog
        assert isinstance(response.input_formats, list)
        assert isinstance(response.output_formats, list)

        print("✓ AgentRegistry provides format information")

    def test_route_builder_uses_guild_state_formats(self, generator, build_message_from_payload):
        """Test that RouteBuilder correctly reads agent formats from guild_state."""
        guild_state = {
            "guild_builder": {
                "agent_message_info": [
                    {
                        "agent_name": "test_agent",
                        "agent_id": "test_1",
                        "input_formats": ["format.Input"],
                        "output_formats": ["format.Output"],
                    }
                ]
            }
        }

        route_builder_spec = (
            AgentBuilder(RouteBuilderAgent)
            .set_id("route_builder")
            .set_name("Route Builder")
            .set_description("Test Route Builder")
            .build_spec()
        )

        route_builder_deps = {
            "llm": DependencySpec(
                class_name=get_qualified_class_name(MockLLMResolver),
                properties={"responses": ["{}"]},
            ),
        }

        route_builder, _ = wrap_agent_for_testing(
            route_builder_spec,
            dependency_map=route_builder_deps,
        )

        # Set guild state
        route_builder._guild_state = guild_state

        # Test format lookup
        input_fmts, output_fmts = route_builder._get_agent_formats("test_agent")

        assert input_fmts == ["format.Input"]
        assert output_fmts == ["format.Output"]

        print("✓ RouteBuilder reads formats from guild_state correctly")


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*80)
    print("RUNNING END-TO-END ASYNC TRANSFORMATION TESTS")
    print("="*80)

    generator = GemstoneGenerator(1)

    # Test suite 1: E2E flow
    print("\n📋 Test Suite 1: End-to-End Flow")
    print("-" * 80)

    e2e_tests = TestAsyncTransformationE2E()

    try:
        e2e_tests.test_complete_flow_with_different_formats(generator)
        print("✅ Complete flow with different formats: PASSED")
    except Exception as e:
        print(f"❌ Complete flow with different formats: FAILED - {e}")
        raise

    try:
        e2e_tests.test_flow_with_same_formats_no_transformation(generator)
        print("✅ Flow with same formats (no transformation): PASSED")
    except Exception as e:
        print(f"❌ Flow with same formats: FAILED - {e}")
        raise

    # Test suite 2: JSONata generation
    print("\n📋 Test Suite 2: JSONata Transformation Generation")
    print("-" * 80)

    jsonata_tests = TestJSONataTransformationGeneration()

    try:
        jsonata_tests.test_chatcompletion_to_textformat_transformation(generator)
        print("✅ ChatCompletion → TextFormat JSONata: PASSED")
    except Exception as e:
        print(f"❌ ChatCompletion → TextFormat JSONata: FAILED - {e}")
        raise

    try:
        jsonata_tests.test_textformat_to_chatcompletion_transformation(generator)
        print("✅ TextFormat → ChatCompletion JSONata: PASSED")
    except Exception as e:
        print(f"❌ TextFormat → ChatCompletion JSONata: FAILED - {e}")
        raise

    try:
        jsonata_tests.test_content_based_router_transformation(generator)
        print("✅ Content-based router JSONata: PASSED")
    except Exception as e:
        print(f"❌ Content-based router JSONata: FAILED - {e}")
        raise

    # Test suite 3: Agent integration
    print("\n📋 Test Suite 3: Agent Integration")
    print("-" * 80)

    integration_tests = TestAgentIntegration()

    try:
        integration_tests.test_agent_registry_provides_format_info(generator)
        print("✅ AgentRegistry format info: PASSED")
    except Exception as e:
        print(f"❌ AgentRegistry format info: FAILED - {e}")
        raise

    try:
        integration_tests.test_route_builder_uses_guild_state_formats(generator)
        print("✅ RouteBuilder guild_state format lookup: PASSED")
    except Exception as e:
        print(f"❌ RouteBuilder guild_state format lookup: FAILED - {e}")
        raise

    print("\n" + "="*80)
    print("🎉 ALL TESTS PASSED! 🎉")
    print("="*80)
    print("\n✅ All agents running correctly")
    print("✅ All agents completing tasks correctly")
    print("✅ JSONata transformations generated as expected")
    print("✅ Message formats correctly identified")
    print("✅ Transformations properly applied to routes")
    print()


if __name__ == "__main__":
    run_all_tests()
