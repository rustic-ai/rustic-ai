"""
Constants for the Guild Generator module.

This module centralizes magic numbers, hardcoded strings, and configuration values
used throughout the guild generator to improve maintainability.
"""

# API Configuration
DEFAULT_API_BASE_URL = "http://localhost:3001"
API_TIMEOUT_SECONDS = 10.0
API_MAX_RETRIES = 3
API_RETRY_BACKOFF_FACTOR = 2.0  # Exponential backoff: 1s, 2s, 4s
API_RETRY_INITIAL_DELAY = 1.0  # Initial retry delay in seconds

# Agent Name Validation
MAX_AGENT_NAME_LENGTH = 100
MIN_AGENT_NAME_WORD_LENGTH = 3
AGENT_NAME_STEM_LENGTH = 5

# Text Truncation
MAX_DESCRIPTION_DISPLAY_LENGTH = 50
MAX_AGENT_NAME_DISPLAY_LENGTH = 30
MAX_ERROR_CONTEXT_LENGTH = 100

# Fuzzy Matching
MIN_FUZZY_MATCH_SCORE = 2
FUZZY_MATCH_EXACT_WORD_SCORE = 4
FUZZY_MATCH_STEM_SCORE = 2
FUZZY_MATCH_COMPOUND_SCORE = 5
MIN_COMPOUND_WORD_LENGTH = 6
MIN_COMPOUND_SPLIT_LENGTH = 3

# System Agent and Topic Names
SYSTEM_USER_PROXY_AGENT = "UserProxyAgent"
SYSTEM_USER_MESSAGE_BROADCAST = "user_message_broadcast"
SYSTEM_DEFAULT_TOPIC = "default_topic"
SYSTEM_DEFAULT_TOPICS = "DEFAULT_TOPICS"

# Valid system destinations for routes
VALID_SYSTEM_DESTINATIONS = [
    SYSTEM_USER_MESSAGE_BROADCAST,
    SYSTEM_DEFAULT_TOPIC,
    SYSTEM_DEFAULT_TOPICS,
]

# Message Formats
CHAT_COMPLETION_REQUEST_FORMAT = "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionRequest"
CHAT_COMPLETION_RESPONSE_FORMAT = "rustic_ai.core.guild.agent_ext.depends.llm.models.ChatCompletionResponse"
TEXT_FORMAT = "rustic_ai.core.ui_protocol.types.TextFormat"

# Generic/Flexible Format Indicators
GENERIC_MESSAGE_FORMATS = ["any", "generic_json", "configurable"]

# Agent Type Suggestions
LLM_AGENT_CLASS = "rustic_ai.llm_agent.llm_agent.LLMAgent"
REACT_AGENT_CLASS = "rustic_ai.llm_agent.react.react_agent.ReActAgent"
SPLITTER_AGENT_CLASS = "rustic_ai.core.agents.eip.splitter_agent.SplitterAgent"
AGGREGATING_AGENT_CLASS = "rustic_ai.core.agents.eip.aggregating_agent.AggregatingAgent"

# Common agent type keywords for suggestions
AGENT_TYPE_KEYWORDS = {
    "llm": [LLM_AGENT_CLASS, REACT_AGENT_CLASS],
    "language": [LLM_AGENT_CLASS, REACT_AGENT_CLASS],
    "split": [SPLITTER_AGENT_CLASS],
    "aggregat": [AGGREGATING_AGENT_CLASS],
}

# Words to skip in agent name matching
AGENT_NAME_SKIP_WORDS = {
    "agent", "the", "a", "an", "for", "of", "to", "in", "llm", "simple", "new"
}

# Agent Types to Exclude from Route Builder Listings
DEFAULT_EXCLUDED_AGENTS = [
    "FlowchartAgent",
    "GuildExportAgent",
]

# Guild Builder State Defaults
DEFAULT_GUILD_NAME = "New Guild"
DEFAULT_GUILD_DESCRIPTION = "A guild created with Guild Generator"

# UI Display Limits
MAX_AGENTS_IN_ERROR_MESSAGE = 5
MAX_ROUTES_IN_OVERVIEW = 100

# Routing Configuration
ROUTE_ALWAYS = -1  # Route every time (-1 means unlimited)
