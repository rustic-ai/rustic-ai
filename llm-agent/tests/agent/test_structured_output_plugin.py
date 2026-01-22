import os

from pydantic import BaseModel
import pytest

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.litellm.agent_ext.llm import LiteLLMResolver
from rustic_ai.llm_agent.llm_agent import LLMAgent
from rustic_ai.llm_agent.llm_agent_conf import LLMAgentConfig
from rustic_ai.llm_agent.plugins.structured_output import StructuredOutputPlugin

from rustic_ai.testing.helpers import wrap_agent_for_testing


class WeatherConditions(BaseModel):
    temperature: int
    humidity: str
    wind_speed: int
    day: str
    forecast: str


class Weather(BaseModel):
    forecast: list[WeatherConditions]


class TestStructuredOutputPlugin:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_structured_output_plugin(self, generator, build_message_from_payload):
        dependency_map = {
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(),
                properties={"model": "vertex_ai/gemini-3-pro-preview", "conf": {
                    "vertex_location": "global"
                }}
            )}
        agent_spec: AgentSpec = (
            AgentBuilder(LLMAgent)
            .set_name("LLM Agent")
            .set_description("An agent that uses a large language model")
            .set_properties(
                LLMAgentConfig(
                    model="vertex_ai/gemini-3-pro-preview",
                    vertex_location="global",
                    default_system_prompt="Extract the event information.",
                    response_postprocessors=[
                        StructuredOutputPlugin()
                    ]
                )
            )
            .build_spec()
        )

        agent, results = wrap_agent_for_testing(
            agent_spec,
            dependency_map=dependency_map,
        )

        agent._on_message(
            build_message_from_payload(
                generator,
                ChatCompletionRequest(
                    messages=[
                        UserMessage(content="""
                        The week ahead brings a mix of weather conditions.
    Sunday is expected to be sunny with a temperature of 77°F and a humidity level of 50%. Winds will be light at around 10 km/h.
    Monday will see partly cloudy skies with a slightly cooler temperature of 72°F and the winds will pick up slightly to around 15 km/h.
    Tuesday brings rain showers, with temperatures dropping to 64°F and humidity rising to 70%.
    Wednesday may see thunderstorms, with a temperature of 68°F.
    Thursday will be cloudy with a temperature of 66°F and moderate humidity at 60%.
    Friday returns to partly cloudy conditions, with a temperature of 73°F and the Winds will be light at 12 km/h.
    Finally, Saturday rounds off the week with sunny skies, a temperature of 80°F, and a humidity level of 40%. Winds will be gentle at 8 km/h.
                        """),
                    ],
                    response_format=get_qualified_class_name(Weather)
                ),
            )
        )

        assert len(results) > 0
        result = results[0]
        assert result.format == get_qualified_class_name(Weather)
        assert len(result.payload["forecast"]) == 7
