import asyncio
import os
import shutil

from flaky import flaky
import pytest
import shortuuid

from rustic_ai.core import GuildTopics, Priority
from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.mcp.agent import MCPAgent
from rustic_ai.mcp.models import (
    CallToolRequest,
    MCPAgentConfig,
    MCPClientType,
    MCPServerConfig,
)

npx_available = shutil.which("npx") is not None


@pytest.mark.skipif(not npx_available, reason="npx not found")
class TestMCPPlaywrightIntegration:

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///mcp_playwright_demo.db"

        if os.path.exists("mcp_playwright_demo.db"):
            os.remove("mcp_playwright_demo.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()
        if os.path.exists("mcp_playwright_demo.db"):
            os.remove("mcp_playwright_demo.db")

    @pytest.fixture
    def playwright_agent_spec(self):
        config = MCPAgentConfig(
            server=MCPServerConfig(
                type=MCPClientType.STDIO,
                command="npx",
                args=["-y", "@playwright/mcp@latest", "--isolated"],
            )
        )

        return (
            AgentBuilder(MCPAgent)
            .set_id("PlaywrightMCPAgent")
            .set_name("Playwright MCP Agent")
            .set_description("Agent connecting to Playwright MCP")
            .set_properties(config)
            .add_additional_topic("mcp_requests")
            .build_spec()
        )

    @pytest.fixture
    async def mcp_guild(self, playwright_agent_spec, rgdatabase):
        mcp_guild_builder = GuildBuilder(
            guild_id=f"mcp_guild{shortuuid.uuid()}",
            guild_name="MCPGuild",
            guild_description="Demonstrates playwright mcp",
        )

        mcp_guild_builder.add_agent_spec(playwright_agent_spec)

        mcp_guild = mcp_guild_builder.bootstrap(rgdatabase, "test_org")

        yield mcp_guild

        # Wait for pending message handlers to drain before shutdown to avoid
        # "cannot schedule new futures after shutdown" errors.
        await asyncio.sleep(1)
        mcp_guild.shutdown()

    async def _setup_probe_and_user(self, mcp_guild):
        """Attach a probe agent, create a user, wait for MCP agent to be reachable."""
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("Probe Agent")
            .set_description("Probe")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .add_additional_topic(GuildTopics.ERROR_TOPIC)
            .add_additional_topic("mcp_requests")
            .build_spec()
        )

        probe_agent = mcp_guild._add_local_agent(probe_spec)

        probe_agent.publish_dict(
            topic=GuildTopics.SYSTEM_TOPIC,
            payload=UserAgentCreationRequest(user_id="test_user", user_name="test_user").model_dump(),
            format=UserAgentCreationRequest,
        )

        await asyncio.sleep(2)

        system_messages = probe_agent.get_messages()
        assert len(system_messages) == 1
        user_created = system_messages[0]
        assert user_created.format == get_qualified_class_name(UserAgentCreationResponse)
        assert user_created.payload["user_id"] == "test_user"
        assert user_created.payload["status_code"] == 201

        # MCP server is launched lazily on first call, but warm up the user proxy.
        await asyncio.sleep(5)
        probe_agent.clear_messages()
        return probe_agent

    def _publish_call_tool_request(self, probe_agent, generator, request: CallToolRequest):
        wrapped_message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="mcp_requests",
            payload=request.model_dump(),
            format=get_qualified_class_name(CallToolRequest),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )
        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

    @pytest.mark.asyncio
    @flaky(max_runs=4, min_passes=1)
    async def test_playwright_navigate_and_read(self, mcp_guild, generator):
        probe_agent = await self._setup_probe_and_user(mcp_guild)

        self._publish_call_tool_request(
            probe_agent,
            generator,
            CallToolRequest(
                tool_name="browser_navigate",
                arguments={"url": "https://the-internet.herokuapp.com/frames"},
            ),
        )

        await asyncio.sleep(8)

        messages = [m for m in probe_agent.get_messages() if "mcp_requests" in m.topics]
        assert messages[-1].payload["results"][0]["type"] == "text"
        assert "frames" in messages[-1].payload["results"][0]["content"]

    @pytest.mark.asyncio
    @flaky(max_runs=4, min_passes=1)
    async def test_unknown_tool_rejected_locally(self, mcp_guild, generator):
        """A tool not offered by the server is rejected by MCPAgent after lazy
        discovery — the request is never forwarded to playwright."""
        probe_agent = await self._setup_probe_and_user(mcp_guild)

        self._publish_call_tool_request(
            probe_agent,
            generator,
            CallToolRequest(
                tool_name="definitely_not_a_real_playwright_tool",
                arguments={},
            ),
        )

        await asyncio.sleep(8)

        errors = [m for m in probe_agent.get_messages() if m.format == get_qualified_class_name(ErrorMessage)]
        assert errors, "expected ErrorMessage from MCPAgent"
        err = errors[-1].payload
        assert err["error_type"] == "ToolNotAllowed"
        # The error must enumerate what the server actually offers so the caller
        # can recover. browser_navigate is a stable part of the playwright MCP surface.
        assert "browser_navigate" in err["error_message"]
