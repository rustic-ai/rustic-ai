import logging
import os

from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
import wikipedia

# Configure Wikipedia API settings
wikipedia.set_rate_limiting(True)
wikipedia.set_lang(os.getenv("WIKIPEDIA_LANGUAGE", "en"))

# Set a user agent to avoid being blocked
user_agent = os.getenv("WIKIPEDIA_USER_AGENT", "RusticAI-Wikipedia/1.0 (https://rustic.ai; opensource@rustic.ai)")
wikipedia.set_user_agent(user_agent)
from rustic_ai.wikipedia.messages import (
    WikipediaError,
    WikipediaPageRequest,
    WikipediaPageResponse,
    WikipediaSearchRequest,
    WikipediaSearchResponse,
    WikipediaSummaryRequest,
    WikipediaSummaryResponse,
)

logger = logging.getLogger(__name__)


class WikipediaAgent(Agent):
    """Agent that provides access to Wikipedia data via the Wikipedia API.

    Automatically configures Wikipedia API with rate limiting enabled.
    """

    @processor(clz=WikipediaSearchRequest)
    def search_wikipedia(self, ctx: ProcessContext[WikipediaSearchRequest]):
        """Search Wikipedia for articles matching the query.

        Args:
            ctx: Process context containing WikipediaSearchRequest
        """
        try:
            logger.info(f"Searching Wikipedia for: {ctx.payload.query}")
            results = wikipedia.search(ctx.payload.query, results=ctx.payload.results)

            response = WikipediaSearchResponse(query=ctx.payload.query, results=results)
            ctx.send(response)

        except Exception as e:
            logger.error(f"Error searching Wikipedia: {e}")
            error = WikipediaError(error_type=type(e).__name__, message=str(e), query=ctx.payload.query)
            ctx.send_error(error)

    @processor(clz=WikipediaPageRequest)
    def fetch_page(self, ctx: ProcessContext[WikipediaPageRequest]):
        """Fetch full Wikipedia page content.

        Args:
            ctx: Process context containing WikipediaPageRequest
        """
        try:
            logger.info(f"Fetching Wikipedia page: {ctx.payload.title}")

            page = wikipedia.page(ctx.payload.title, auto_suggest=ctx.payload.auto_suggest)

            response = WikipediaPageResponse(
                title=page.title,
                summary=page.summary,
                content=page.content,
                url=page.url,
                images=page.images,
                references=page.references,
                categories=page.categories,
            )
            ctx.send(response)

        except wikipedia.exceptions.DisambiguationError as e:
            logger.warning(f"Disambiguation page found for: {ctx.payload.title}")
            error = WikipediaError(
                error_type="DisambiguationError",
                message=f"Multiple pages found. Options: {', '.join(e.options[:10])}",
                query=ctx.payload.title,
            )
            ctx.send_error(error)

        except wikipedia.exceptions.PageError as e:
            logger.warning(f"Page not found: {ctx.payload.title}")
            error = WikipediaError(
                error_type="PageError",
                message=f"Page not found: {ctx.payload.title}",
                query=ctx.payload.title,
            )
            ctx.send_error(error)

        except Exception as e:
            logger.error(f"Error fetching Wikipedia page: {e}")
            error = WikipediaError(error_type=type(e).__name__, message=str(e), query=ctx.payload.title)
            ctx.send_error(error)

    @processor(clz=WikipediaSummaryRequest)
    def fetch_summary(self, ctx: ProcessContext[WikipediaSummaryRequest]):
        """Fetch Wikipedia page summary.

        Args:
            ctx: Process context containing WikipediaSummaryRequest
        """
        try:
            logger.info(f"Fetching Wikipedia summary for: {ctx.payload.title}")

            summary = wikipedia.summary(
                ctx.payload.title,
                sentences=ctx.payload.sentences,
                auto_suggest=ctx.payload.auto_suggest,
            )

            page = wikipedia.page(ctx.payload.title, auto_suggest=ctx.payload.auto_suggest)

            response = WikipediaSummaryResponse(title=page.title, summary=summary, url=page.url)
            ctx.send(response)

        except wikipedia.exceptions.DisambiguationError as e:
            logger.warning(f"Disambiguation page found for: {ctx.payload.title}")
            error = WikipediaError(
                error_type="DisambiguationError",
                message=f"Multiple pages found. Options: {', '.join(e.options[:10])}",
                query=ctx.payload.title,
            )
            ctx.send_error(error)

        except wikipedia.exceptions.PageError as e:
            logger.warning(f"Page not found: {ctx.payload.title}")
            error = WikipediaError(
                error_type="PageError",
                message=f"Page not found: {ctx.payload.title}",
                query=ctx.payload.title,
            )
            ctx.send_error(error)

        except Exception as e:
            logger.error(f"Error fetching Wikipedia summary: {e}")
            error = WikipediaError(error_type=type(e).__name__, message=str(e), query=ctx.payload.title)
            ctx.send_error(error)
