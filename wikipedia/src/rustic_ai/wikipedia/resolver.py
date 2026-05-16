import os

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
import wikipedia


class WikipediaConfigResolver(DependencyResolver):
    """Resolver for Wikipedia API configuration.

    Configures Wikipedia API settings from environment variables:
    - WIKIPEDIA_LANGUAGE: Language code (default: 'en')
    - WIKIPEDIA_USER_AGENT: Custom user agent string (optional)
    """

    def __init__(self):
        super().__init__()
        self.language = os.getenv("WIKIPEDIA_LANGUAGE", "en")
        self.user_agent = os.getenv("WIKIPEDIA_USER_AGENT", None)

    def resolve(self) -> dict:
        """Configure and return Wikipedia API settings.

        Returns:
            dict: Configuration dictionary with language and user_agent
        """
        wikipedia.set_lang(self.language)

        if self.user_agent:
            wikipedia.set_user_agent(self.user_agent)

        return {"language": self.language, "user_agent": self.user_agent}
