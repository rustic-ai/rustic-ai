import asyncio

from flaky import flaky
import shortuuid

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.messaging.core.message import AgentTag, Message
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority
from rustic_ai.playwright.agent import (
    PlaywrightScraperAgent,
    ScrapingOutputFormat,
    WebScrapingCompleted,
    WebScrapingRequest,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


class TestPlaywrightAgent:
    @flaky(max_runs=3, min_passes=1)
    async def test_scraping(self, generator):

        filesystem = DependencySpec(
            class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
            properties={
                "path_base": "/tmp",
                "protocol": "file",
                "storage_options": {
                    "auto_mkdir": True,
                },
            },
        )
        agent, results = wrap_agent_for_testing(
            AgentBuilder(PlaywrightScraperAgent)
            .set_id("001")
            .set_name("WebScrapper")
            .set_description("A web scraping agent using Playwright")
            .build(),
            generator,
            {"filesystem": filesystem},
        )

        request_id = shortuuid.uuid()

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=WebScrapingRequest(
                id=request_id,
                links=[
                    MediaLink(url="https://example.com/index.html"),
                    MediaLink(url="https://example.com/about.html"),
                    MediaLink(url="https://example.com/contact.html"),
                    MediaLink(url="https://www.rfc-editor.org/rfc/rfc2606.html"),
                ],
            ).model_dump(),
            format=get_qualified_class_name(WebScrapingRequest),
        )

        agent._on_message(message)

        wsc = get_qualified_class_name(WebScrapingCompleted)
        tries = 0

        while True:
            await asyncio.sleep(2)

            tries += 1
            if len(results) >= 5 or (results and results[-1].format == wsc) or tries > 10:
                break

        assert len(results) == 5
        assert results[0].priority == Priority.NORMAL
        assert results[0].in_response_to == message.id
        assert results[0].current_thread_id == message.id
        assert results[0].recipient_list == []

        assert results[0].payload["id"] is not None
        assert results[0].payload["mimetype"] == "text/html"
        assert results[0].payload["encoding"] == "utf-8"
        assert results[0].payload["name"] is not None

        assert results[0].payload["metadata"] is not None
        assert results[0].payload["metadata"]["scraped_url"] == "https://example.com/index.html"  # type: ignore
        assert results[0].payload["metadata"]["title"] == "Example Domain"  # type: ignore
        assert results[0].payload["metadata"]["request_id"] == request_id  # type: ignore

        assert results[0].payload["url"] is not None
        assert results[0].payload["on_filesystem"] is True

        fs = filesystem.to_resolver().resolve(agent.guild_id, "GUILD_GLOBAL")

        assert fs.exists(results[0].payload["url"])

        completed = WebScrapingCompleted.model_validate(results[-1].payload)

        assert completed.id == request_id
        assert len(completed.links) == 2  # 2 links are duplicates

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=WebScrapingRequest(
                id=request_id,
                links=[
                    MediaLink(url="https://example.com/index.html"),
                ],
                output_format=ScrapingOutputFormat.MARKDOWN,
                force=True,
            ).model_dump(),
            format=get_qualified_class_name(WebScrapingRequest),
        )

        agent._on_message(message)

        wsc = get_qualified_class_name(WebScrapingCompleted)
        tries = 0

        while True:
            await asyncio.sleep(2)

            tries += 1
            if len(results) >= 6 or (results and results[-1].format == wsc) or tries > 10:
                break

        result = results[-2]
        assert result.in_response_to == message.id
        assert result.current_thread_id == message.id
        assert result.recipient_list == []

        assert result.payload["id"] is not None
        assert result.payload["mimetype"] == "text/markdown"
        assert result.payload["encoding"] == "utf-8"
        assert result.payload["name"] is not None

        # Give the system a final moment to complete any pending tasks
        await asyncio.sleep(2)

        # Cancel any remaining tasks explicitly to avoid the warning
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task() and not task.done():
                task.cancel()

    @flaky(max_runs=3, min_passes=1)
    async def test_recursive_scraping_with_depth(self, generator):
        filesystem = DependencySpec(
            class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
            properties={
                "path_base": "/tmp",
                "protocol": "file",
                "storage_options": {
                    "auto_mkdir": True,
                },
            },
        )
        agent, results = wrap_agent_for_testing(
            AgentBuilder(PlaywrightScraperAgent)
            .set_id("002")
            .set_name("WebScrapperDepth")
            .set_description("A web scraping agent testing depth")
            .build(),
            generator,
            {"filesystem": filesystem},
        )

        request_id = shortuuid.uuid()

        message = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="testerId", name="tester"),
            payload=WebScrapingRequest(
                id=request_id,
                links=[MediaLink(url="https://webscraper.io/test-sites/e-commerce/static")],
                depth=1,
            ).model_dump(),
            format=get_qualified_class_name(WebScrapingRequest),
        )

        agent._on_message(message)

        wsc = get_qualified_class_name(WebScrapingCompleted)
        tries = 0

        while True:
            await asyncio.sleep(3)
            tries += 1
            if results and results[-1].format == wsc:
                break
            if tries > 12:
                break

        completed = WebScrapingCompleted.model_validate(results[-1].payload)

        assert completed.id == request_id
        assert len(completed.links) >= 1

        for result in results[:-1]:
            assert result.payload["url"].endswith(".html") or result.payload["url"].endswith(".md")
            fs = filesystem.to_resolver().resolve(agent.guild_id, "GUILD_GLOBAL")
            assert fs.exists(result.payload["url"])

        for task in asyncio.all_tasks():
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
