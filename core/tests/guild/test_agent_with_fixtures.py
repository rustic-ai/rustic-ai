import time

from pydantic import BaseModel

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import (
    Agent,
    AgentFixtures,
    AgentMode,
    AgentType,
    ProcessContext,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.dsl import AgentSpec
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging.core.message import JsonDict, Message, MessageConstants


class SomeTestError(BaseModel):
    msg: str


class FixtureTestAgent(Agent):
    """
    An Agent to test the fixture decorators
    """

    def __init__(self, agent_spec: AgentSpec):
        super().__init__(
            agent_spec,
            agent_type=AgentType.BOT,
            agent_mode=AgentMode.LOCAL,
        )
        self._before_process_count = 0
        self._after_process_count = 0
        self._send_message_count = 0
        self._send_error_count = 0
        self._message_mod_count = 0

        self._alt_before_process_count = 0
        self._alt_after_process_count = 0
        self._alt_send_message_count = 0
        self._alt_send_error_count = 0
        self._alt_message_mod_count = 0

    @agent.processor(JsonDict)
    def some_message_handler(self, ctx: ProcessContext[JsonDict]):
        """
        Handles messages of type MessageDataModel, doing cool things with the data
        """

        if ctx.payload.get("error"):
            ctx.send_error(SomeTestError(msg="An error occurred"))
        else:
            ctx.send_dict({"response": "cool response"})

    @AgentFixtures.before_process
    def before_process(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._before_process_count += 1

    @AgentFixtures.after_process
    def after_process(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._after_process_count += 1

    @AgentFixtures.on_send
    def send_message(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._send_message_count += 1

    @AgentFixtures.on_send_error
    def send_error(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._send_error_count += 1

    @AgentFixtures.before_process
    def alt_before_process(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._alt_before_process_count += 1

    @AgentFixtures.after_process
    def alt_after_process(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._alt_after_process_count += 1

    @AgentFixtures.on_send
    def alt_send_message(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._alt_send_message_count += 1

    @AgentFixtures.on_send_error
    def alt_send_error(self, ctx: ProcessContext[JsonDict]):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._alt_send_error_count += 1

    @AgentFixtures.outgoing_message_modifier
    def message_mod(self, ctx: ProcessContext[JsonDict], message: Message):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._message_mod_count += 1

    @AgentFixtures.outgoing_message_modifier
    def alt_message_mod(self, ctx: ProcessContext[JsonDict], message: Message):
        if ctx.message.format == MessageConstants.RAW_JSON_FORMAT:
            self._alt_message_mod_count += 1


class TestAgentFixtures:
    def test_fixture_calls(self, guild: Guild, probe_agent: ProbeAgent):

        agent = AgentBuilder(FixtureTestAgent).set_name("test_agent").set_description("test agent").build()
        guild._add_local_agent(agent)
        guild._add_local_agent(probe_agent)

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"key1": "value1"})

        # Allow time for asynchronous message processing
        time.sleep(0.5)

        assert agent._before_process_count == 1
        assert agent._after_process_count == 1
        assert agent._send_message_count == 1
        assert agent._send_error_count == 0
        assert agent._message_mod_count == 1

        assert agent._alt_before_process_count == 1
        assert agent._alt_after_process_count == 1
        assert agent._alt_send_message_count == 1
        assert agent._alt_send_error_count == 0
        assert agent._alt_message_mod_count == 1

        probe_agent.publish_dict(guild.DEFAULT_TOPIC, {"key1": "value1", "error": True})

        # Allow time for asynchronous message processing
        time.sleep(0.5)

        assert agent._before_process_count == 2
        assert agent._after_process_count == 2
        assert agent._send_message_count == 1
        assert agent._send_error_count == 1
        assert agent._message_mod_count == 2

        assert agent._alt_before_process_count == 2
        assert agent._alt_after_process_count == 2
        assert agent._alt_send_message_count == 1
        assert agent._alt_send_error_count == 1
        assert agent._alt_message_mod_count == 2
