import os
import time

import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild import Guild
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.huggingface.agents.nlp.squad_agent import (
    QuestionWithContext,
    SquadAgent,
    SquadAnswer,
)


class TestSquadAgent:
    @pytest.mark.skipif(os.getenv("HF_TOKEN") is None, reason="HF_TOKEN environment variable not set")
    def test_answer_question(self, probe_spec, guild: Guild):

        squad_agent_spec = (
            AgentBuilder(SquadAgent)
            .set_id("squad2")
            .set_name("Test Agent")
            .set_description("Test for SquadAgent")
            .build_spec()
        )
        squad_agent = guild._add_local_agent(squad_agent_spec)
        probe_agent = guild._add_local_agent(probe_spec)

        context = (
            "The Taj Mahal, found in the Indian state of Uttar Pradesh, is one of the Seven Wonders of the "
            "Modern World. It was built in the 17th century by Mughal emperor Shah Jahan as a mausoleum for "
            "his third wife, Mumtaz Mahal. The Taj Mahal is a fine example of Mughal architecture, which is a "
            "blend of Islamic, Persian, Turkish and Indian architectural styles. It is one of the most famous "
            "buildings in the world and a UNESCO World Heritage Site since 1983."
        )
        prompt = "Who was Mumtaz Mahal?"

        question = QuestionWithContext(context=context, question=prompt)

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, question.model_dump(), format=QuestionWithContext)

        time.sleep(60)
        messages = probe_agent.get_messages()

        assert len(messages) == 1
        assert messages[0].format == get_qualified_class_name(SquadAnswer)
        assert "third wife" in messages[0].payload["text"]
