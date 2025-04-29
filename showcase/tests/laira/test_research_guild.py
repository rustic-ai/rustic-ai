import asyncio
import os

import pytest
import shortuuid

from rustic_ai.chroma.agent_ext.vectorstore import ChromaResolver
from rustic_ai.core import AgentSpec, Guild, GuildTopics, Priority
from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.agents.indexing.vector_agent import IngestDocuments, VectorAgent
from rustic_ai.core.agents.system.models import (
    UserAgentCreationRequest,
    UserAgentCreationResponse,
)
from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.agents.utils import UserProxyAgent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystemResolver
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    TextContentPart,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder, RouteBuilder
from rustic_ai.core.guild.metastore import Metastore
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    Message,
    PayloadTransformer,
    RoutingDestination,
    RoutingRule,
    RoutingSlip,
)
from rustic_ai.core.ui_protocol.types import TextFormat
from rustic_ai.core.utils import GemstoneGenerator
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.jexpr import JExpr, JObj, JxScript
from rustic_ai.langchain.agent_ext.embeddings.openai import OpenAIEmbeddingsResolver
from rustic_ai.langchain.agent_ext.text_splitter.recursive_splitter import (
    RecursiveSplitterResolver,
)
from rustic_ai.litellm.agent_ext import LiteLLMResolver
from rustic_ai.playwright.agent import PlaywrightScraperAgent, WebScrapingRequest
from rustic_ai.serpapi.agent import SERPAgent, SERPResults
from rustic_ai.showcase.laira.research_manager import ResearchManager


class TestResearchGuild:

    @pytest.fixture
    def routing_slip(self) -> RoutingSlip:

        serp_to_playwright_route = (
            RouteBuilder(AgentTag(id="serp_agent"))
            .on_message_format(SERPResults)
            .set_payload_transformer(
                output_type=WebScrapingRequest,
                payload_xform=JxScript(
                    JObj({"id": JExpr("id"), "links": JExpr("$").results, "output_format": "text/markdown"})
                ),
            )
            .set_route_times(-1)
            .build()
        )

        playwright_to_vector_route = RoutingRule(
            agent=AgentTag(id="playwright_agent"),
            message_format=get_qualified_class_name(MediaLink),
            transformer=PayloadTransformer(
                output_format=get_qualified_class_name(IngestDocuments),
                expression='{"documents": [$]}',
            ),
            route_times=-1,
        )

        broadcast_research_results = RoutingRule(
            agent=AgentTag(id="research_manager"),
            message_format=get_qualified_class_name(TextFormat),
            destination=RoutingDestination(topics=UserProxyAgent.BROADCAST_TOPIC),
        )

        slip = RoutingSlip(
            steps=[
                serp_to_playwright_route,
                playwright_to_vector_route,
                broadcast_research_results,
            ],
        )

        return slip

    @pytest.fixture
    def rgdatabase(self):
        db = "sqlite:///rg_test_rustic_app.db"

        if os.path.exists("test_rustic_app.db"):
            os.remove("test_rustic_app.db")

        Metastore.initialize_engine(db)
        Metastore.get_engine(db)
        Metastore.create_db()
        yield db
        Metastore.drop_db()

    @pytest.fixture
    def research_guild(self, routing_slip, rgdatabase):
        dep_map = {
            "vectorstore": DependencySpec(
                class_name=ChromaResolver.get_qualified_class_name(),
                properties={"chroma_settings": {"persist_directory": "/tmp/research_guild_test"}},
            ),
            "filesystem": DependencySpec(
                class_name=FileSystemResolver.get_qualified_class_name(),
                properties={
                    "path_base": "/tmp",
                    "protocol": "file",
                    "storage_options": {
                        "auto_mkdir": True,
                    },
                },
            ),
            "textsplitter": DependencySpec(
                class_name=RecursiveSplitterResolver.get_qualified_class_name(),
                properties={"conf": {"chunk_size": 10000, "chunk_overlap": 500}},
            ),
            "embeddings": DependencySpec(class_name=OpenAIEmbeddingsResolver.get_qualified_class_name(), properties={}),
            "llm": DependencySpec(
                class_name=LiteLLMResolver.get_qualified_class_name(), properties={"model": "gpt-4o-mini"}
            ),
        }
        research_guild_builder = GuildBuilder(
            guild_id=f"research_guild_{shortuuid.uuid()}",
            guild_name="Research Guild",
            guild_description="A guild to research stuff",
        )

        research_guild_builder.set_dependency_map(dep_map)

        research_agent = (
            AgentBuilder(ResearchManager)
            .set_id("research_manager")
            .set_name("Research Manager")
            .set_description("A manager for the research process")
            .build_spec()
        )

        vector_agent = (
            AgentBuilder(VectorAgent)
            .set_id("vector_agent")
            .set_name("Vector Agent")
            .set_description("An agent that handles document indexing and similarity search using a vector store.")
            .build_spec()
        )

        serp_agent: AgentSpec = (
            AgentBuilder(SERPAgent)
            .set_id("serp_agent")
            .set_name("SERP Agent")
            .set_description("An agent that handles search engine results page queries")
            .build_spec()
        )

        playwright_agent: AgentSpec = (
            AgentBuilder(PlaywrightScraperAgent)
            .set_id("playwright_agent")
            .set_name("Playwright Agent")
            .set_description("An agent that handles web scraping using Playwright")
            .build_spec()
        )

        research_guild_builder.add_agent_spec(research_agent)
        research_guild_builder.add_agent_spec(vector_agent)
        research_guild_builder.add_agent_spec(serp_agent)
        research_guild_builder.add_agent_spec(playwright_agent)

        research_guild = research_guild_builder.set_routes(routing_slip).bootstrap(rgdatabase)

        yield research_guild
        research_guild.shutdown()

    @pytest.mark.skipif(os.getenv("SKIP_EXPENSIVE_TESTS") == "true", reason="Skipping expensive tests")
    @pytest.mark.asyncio
    async def test_research_guild(self, research_guild: Guild, routing_slip: RoutingSlip, generator: GemstoneGenerator):

        probe_agent: ProbeAgent = (
            AgentBuilder(ProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("A test agent")
            .add_additional_topic(UserProxyAgent.BROADCAST_TOPIC)
            .add_additional_topic(GuildTopics.SYSTEM_TOPIC)
            .build()
        )

        research_guild._add_local_agent(probe_agent)

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

        probe_agent.clear_messages()

        # Send a query to the research manager
        id_obj = generator.get_id(Priority.NORMAL)

        wrapped_message = Message(
            id_obj=id_obj,
            topics="default_topic",
            payload=ChatCompletionRequest(
                messages=[
                    UserMessage(
                        content=[TextContentPart(text="What is LSTM?"), TextContentPart(text="How does it work?")]
                    )
                ]
            ).model_dump(),
            format=get_qualified_class_name(ChatCompletionRequest),
            sender=AgentTag(id="test_agent", name="TestAgent"),
        )

        probe_agent.publish(
            topic=UserProxyAgent.get_user_inbox_topic("test_user"),
            payload=wrapped_message,
        )

        tf = get_qualified_class_name(TextFormat)

        count = 0

        while True:
            await asyncio.sleep(5)
            messages = probe_agent.get_messages()
            count += 1

            if (len(messages) >= 22 and messages[-1].format == tf) or count >= 20:
                break

        messages = probe_agent.get_messages()

        final_response = messages[-1]

        assert len(messages) >= 22

        assert final_response.format == tf

        content = TextFormat.model_validate(final_response.payload)

        # Check that the response text contains LSTM
        assert "LSTM" in content.text

        # Give the system a final moment to complete any pending tasks
        await asyncio.sleep(2)

        # Cancel any remaining tasks explicitly to avoid the warning
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
