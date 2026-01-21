import asyncio
import os
import shutil

from flaky import flaky
import pytest
import shortuuid

from rustic_ai.core import GuildTopics, Priority
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

# Check if npx is available
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
                name="playwright",
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

        # Use dummy_ord or similar organization ID
        mcp_guild = mcp_guild_builder.bootstrap(rgdatabase, "test_org")

        yield mcp_guild

        # Wait for any pending message handlers to complete before shutdown
        # This prevents "cannot schedule new futures after shutdown" errors
        await asyncio.sleep(1)
        mcp_guild.shutdown()

    @pytest.mark.asyncio
    @flaky(max_runs=4, min_passes=1)
    async def test_playwright_navigate_and_read(self, mcp_guild, generator):

        # Setup Probe Agent to interact
        probe_spec = (
            AgentBuilder(ProbeAgent)
            .set_id("probe_agent")
            .set_name("Probe Agent")
            .set_description("Probe")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
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

        # We need to wait a bit for the MCP agent to start and connect to the server
        await asyncio.sleep(5)

        probe_agent.clear_messages()

        # Let's try to navigate to https://the-internet.herokuapp.com/abtest
        navigate_payload = CallToolRequest(
            server_name="playwright",
            tool_name="browser_navigate",
            arguments={"url": "https://the-internet.herokuapp.com/abtest"},
        ).model_dump()

        id_obj = generator.get_id(Priority.NORMAL)
        wrapped_message = Message(
            id_obj=id_obj,
            topics="mcp_requests",
            payload=navigate_payload,
            format=get_qualified_class_name(CallToolRequest),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )

        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

        await asyncio.sleep(8)

        messages = probe_agent.get_messages()
        messages = [msg for msg in messages if msg.topics == "mcp_requests"]
        assert messages[-1].payload["results"][0]["type"] == "text"
        assert "Also known as split testing" in messages[-1].payload["results"][0]["content"]
