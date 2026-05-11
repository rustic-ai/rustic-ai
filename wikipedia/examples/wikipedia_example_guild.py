"""
Wikipedia Agent Demo

This example demonstrates how to use the WikipediaAgent to search and fetch data from Wikipedia.

Environment variables (optional):
- WIKIPEDIA_LANGUAGE: Language code (default: 'en')
- WIKIPEDIA_USER_AGENT: Custom user agent string
"""

import asyncio

from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.guild.execution.sync_execution_engine import SyncExecutionEngine
from rustic_ai.wikipedia import (
    WikipediaAgent,
    WikipediaConfigResolver,
    WikipediaPageRequest,
    WikipediaSearchRequest,
    WikipediaSummaryRequest,
)


async def main():
    """Run Wikipedia agent demo."""

    # Build Wikipedia agent with config resolver
    wikipedia_agent_spec = (
        AgentBuilder(WikipediaAgent)
        .set_name("WikipediaAgent")
        .set_description("Wikipedia data connector for fetching articles and summaries")
        .set_dependency_map(
            {
                "wikipedia_config": DependencySpec(
                    class_name="rustic_ai.wikipedia.resolver.WikipediaConfigResolver", properties={}
                )
            }
        )
        .build_spec()
    )

    # Build guild with sync execution engine
    guild_spec = (
        GuildBuilder()
        .set_name("WikipediaGuild")
        .set_description("Guild for Wikipedia operations")
        .add_agent(wikipedia_agent_spec)
        .build_spec()
    )

    # Create and start guild
    execution_engine = SyncExecutionEngine()
    guild = await execution_engine.execute(guild_spec)

    print("Wikipedia Guild started!\n")

    # Example 1: Search for articles
    print("Example 1: Searching for 'Artificial Intelligence'")
    search_request = WikipediaSearchRequest(query="Artificial Intelligence", results=5)
    await guild.send("system", search_request)
    await asyncio.sleep(1)
    print()

    # Example 2: Get article summary
    print("Example 2: Fetching summary for 'Machine Learning'")
    summary_request = WikipediaSummaryRequest(title="Machine Learning", sentences=3)
    await guild.send("system", summary_request)
    await asyncio.sleep(1)
    print()

    # Example 3: Get full page content
    print("Example 3: Fetching full page for 'Python (programming language)'")
    page_request = WikipediaPageRequest(title="Python (programming language)")
    await guild.send("system", page_request)
    await asyncio.sleep(2)
    print()

    print("Demo completed!")

    # Shutdown guild
    await execution_engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())