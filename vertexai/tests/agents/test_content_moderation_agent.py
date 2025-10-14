import os
import time

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    FinishReason,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.vertexai.agents.content_moderation import (
    ContentModerationAgent,
    ModerationResponse,
)


class TestContentModerationAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_content_moderation_scenarios(self, probe_spec, org_id):
        """
        Test multiple content moderation scenarios with different inputs and expected responses.
        """
        moderation_scenarios = [
            {
                "input": "Hello, how are you today? The weather is nice.",
                "description": "Safe content - should not be flagged",
                "assertions": lambda response: response["is_flagged"] is False,
            },
            {
                "input": "I'm a little over halfway through Ulysses by James Joyce and I hate it. What a pile of garbage!",
                "description": "Verify response includes all fields",
                "assertions": lambda response: (
                    "is_flagged" in response
                    and "max_confidence" in response
                    and (
                        not response["is_flagged"]
                        or (
                            "flagged_categories" in response
                            and isinstance(response["flagged_categories"], dict)
                            and len(response["flagged_categories"]) > 0
                        )
                    )
                ),
            },
            {
                "input": "",
                "description": "Empty input - should not be flagged",
                "assertions": lambda response: response["is_flagged"] is False,
            },
        ]

        # Arrange
        agent_spec = (
            AgentBuilder(ContentModerationAgent)
            .set_name("Test Content Moderator Agent")
            .set_description("An agent for testing content moderation")
            .set_properties({"threshold": 0.6})
            .build_spec()
        )

        guild_builder = GuildBuilder(
            guild_name="Moderation Test Guild", guild_description="Guild to test content moderation"
        ).add_agent_spec(agent_spec)

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        # Act & Assert
        for idx, scenario in enumerate(moderation_scenarios):
            probe_agent.clear_messages()
            print(f"\nRunning scenario {idx + 1}: {scenario['description']}")

            payload = {"messages": [{"content": scenario["input"], "role": "user"}]}

            probe_agent.publish_dict(
                topic=guild.DEFAULT_TOPIC,
                payload=payload,
                format=ChatCompletionRequest,
            )

            time.sleep(1)
            messages = probe_agent.get_messages()

            assert len(messages) == 1, f"Scenario {idx + 1} failed: Expected 1 message, got {len(messages)}"
            assert messages[0].format == get_qualified_class_name(
                ModerationResponse
            ), f"Scenario {idx + 1} failed: Wrong response format"

            moderation_response = messages[0].payload

            assert scenario["assertions"](
                moderation_response
            ), f"Scenario {idx + 1} failed: {scenario['description']}\nResponse: {moderation_response}"

        guild.shutdown()

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_category_moderation_scenarios(self, probe_spec, org_id):
        category_agent_spec = (
            AgentBuilder(ContentModerationAgent)
            .set_name("Category Moderator Agent")
            .set_description("An agent for flagging specified category and threshold")
            .set_properties({"categories": ["Health"], "threshold": 0.5})
            .build_spec()
        )

        guild_builder = GuildBuilder(
            guild_name="Moderation Guild with Config", guild_description="Guild to test content moderation"
        ).add_agent_spec(category_agent_spec)

        guild = guild_builder.launch(organization_id=org_id)
        probe_agent: ProbeAgent = guild._add_local_agent(probe_spec)  # type: ignore

        payload = {
            "messages": [
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "The ketogenic diet involves consuming a very low amount of carbohydrates and "
                            "replacing them with fat to help your body burn fat for energy.",
                        }
                    ],
                    "role": "user",
                }
            ]
        }

        probe_agent.publish_dict(
            topic=guild.DEFAULT_TOPIC,
            payload=payload,
            format=ChatCompletionRequest,
        )

        time.sleep(1)
        messages = probe_agent.get_messages()
        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(ModerationResponse)
        moderation_response = messages[0].payload
        assert moderation_response["is_flagged"] is True

        wt_loss_response = "A weight loss of about 0.5 to 1 kg (1 to 2 pounds) per week is considered reasonable."

        payload_2 = ChatCompletionResponse(
            id="xyz",
            created=1,
            model="custom",
            choices=[
                Choice(message=AssistantMessage(content=wt_loss_response), finish_reason=FinishReason.stop, index=0)
            ],
        ).model_dump()

        probe_agent.clear_messages()
        probe_agent.publish_dict(
            topic=guild.DEFAULT_TOPIC,
            payload=payload_2,
            format=ChatCompletionResponse,
        )
        time.sleep(1)
        messages = probe_agent.get_messages()
        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(ModerationResponse)
        moderation_response = messages[0].payload
        assert moderation_response["is_flagged"] is True
        guild.shutdown()
