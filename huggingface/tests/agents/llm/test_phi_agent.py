import os
import time

import pytest

from rustic_ai.core.agents.commons import GenerationPromptRequest
from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.guild import Guild
from rustic_ai.huggingface.agents.llm.phi_agent import LLMPhiAgent


class TestPhiAgent:
    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    def test_response_is_generated(self, probe_spec, guild: Guild):
        agent_spec = (
            AgentBuilder(LLMPhiAgent)
            .set_name("Test Agent")
            .set_description("A test agent")
            .set_id("phi_agent")
            .build_spec()
        )

        agent = guild._add_local_agent(agent_spec)
        probe_agent = guild._add_local_agent(probe_spec)

        generation_prompt = "Hello, my name is"
        probe_agent.publish_dict(
            guild.DEFAULT_TOPIC,
            {"generation_prompt": generation_prompt},
            in_response_to=1,
            format=GenerationPromptRequest,
        )

        time.sleep(60)

        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].topics == guild.DEFAULT_TOPIC
        assert messages[0].payload["generation_prompt"] == generation_prompt
        assert messages[0].payload["generated_response"] != ""
