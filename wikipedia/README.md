# Rustic AI - Wikipedia Data Connector

A Rustic AI module that provides Wikipedia data access through a simple agent interface. Fetch articles, search for content, and retrieve summaries from Wikipedia using the Wikipedia API.

## Features

- **Search Wikipedia**: Find articles matching a query
- **Fetch Full Pages**: Retrieve complete article content, images, references, and categories
- **Get Summaries**: Fetch concise article summaries with configurable length
- **Error Handling**: Graceful handling of disambiguation pages and missing articles
- **Configurable**: Support for custom language and user-agent via environment variables

## Installation

```bash
cd wikipedia
poetry install --with dev --all-extras
```

## Quick Start

### Basic Usage

```python
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.wikipedia import (
    WikipediaAgent,
    WikipediaSearchRequest,
    WikipediaPageRequest,
    WikipediaSummaryRequest,
)

# Build Wikipedia agent
agent_spec = (
    AgentBuilder(WikipediaAgent)
    .set_name("WikipediaAgent")
    .set_description("Wikipedia data connector")
    .build_spec()
)

# Build guild
guild_spec = (
    GuildBuilder()
    .set_name("WikipediaGuild")
    .add_agent(agent_spec)
    .build_spec()
)

# Use the agent
await guild.send("system", WikipediaSearchRequest(query="Python programming"))
```

### Environment Variables

Configure Wikipedia API behavior using environment variables:

- `WIKIPEDIA_LANGUAGE`: Language code (default: `en`)
  - Examples: `es`, `fr`, `de`, `ja`, `zh`
- `WIKIPEDIA_USER_AGENT`: Custom user agent string (optional)
  - Useful for identifying your application to Wikipedia

```bash
export WIKIPEDIA_LANGUAGE=es
export WIKIPEDIA_USER_AGENT="MyApp/1.0 (contact@example.com)"
```

## API Reference

### Messages

#### WikipediaSearchRequest
Search for Wikipedia articles.

**Fields:**
- `query` (str): Search query
- `results` (int): Number of results to return (default: 10)

**Response:** `WikipediaSearchResponse`
- `query` (str): Original search query
- `results` (list[str]): List of article titles

#### WikipediaPageRequest
Fetch a complete Wikipedia page.

**Fields:**
- `title` (str): Article title
- `auto_suggest` (bool): Enable auto-suggestion for alternative titles (default: True)

**Response:** `WikipediaPageResponse`
- `title` (str): Article title
- `summary` (str): Article summary
- `content` (str): Full article content
- `url` (str): Article URL
- `images` (list[str]): Image URLs
- `references` (list[str]): Reference links
- `categories` (list[str]): Article categories

#### WikipediaSummaryRequest
Fetch a Wikipedia page summary.

**Fields:**
- `title` (str): Article title
- `sentences` (int): Number of sentences in summary (default: 5)
- `auto_suggest` (bool): Enable auto-suggestion (default: True)

**Response:** `WikipediaSummaryResponse`
- `title` (str): Article title
- `summary` (str): Article summary
- `url` (str): Article URL

#### WikipediaError
Error response for failed operations.

**Fields:**
- `error_type` (str): Error type (e.g., "PageError", "DisambiguationError")
- `message` (str): Error description
- `query` (str, optional): Original query that caused the error

## Examples

### Search for Articles

```python
from rustic_ai.wikipedia import WikipediaSearchRequest

search_request = WikipediaSearchRequest(
    query="Machine Learning",
    results=5
)
await guild.send("system", search_request)
```

### Fetch Article Summary

```python
from rustic_ai.wikipedia import WikipediaSummaryRequest

summary_request = WikipediaSummaryRequest(
    title="Artificial Intelligence",
    sentences=3
)
await guild.send("system", summary_request)
```

### Fetch Full Article

```python
from rustic_ai.wikipedia import WikipediaPageRequest

page_request = WikipediaPageRequest(
    title="Python (programming language)"
)
await guild.send("system", page_request)
```

### With Dependency Injection

```python
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.wikipedia import WikipediaConfigResolver

agent_spec = (
    AgentBuilder(WikipediaAgent)
    .set_name("WikipediaAgent")
    .set_dependency_map({
        "wikipedia_config": DependencySpec(
            class_name="rustic_ai.wikipedia.resolver.WikipediaConfigResolver",
            properties={}
        )
    })
    .build_spec()
)
```

## Testing

Run tests:

```bash
# Run all tests
poetry run tox

# Run specific test
poetry run pytest tests/test_wikipedia_agent.py -v

# Run with coverage
poetry run pytest tests/ --cov=rustic_ai.wikipedia --cov-report=html
```

## Error Handling

The Wikipedia agent handles common errors gracefully:

1. **Page Not Found**: Returns `WikipediaError` with `error_type="PageError"`
2. **Disambiguation Pages**: Returns `WikipediaError` with `error_type="DisambiguationError"` and available options
3. **Network Errors**: Returns `WikipediaError` with detailed error message

## Run Demo

```bash
cd wikipedia
poetry shell
python examples/wikipedia_demo.py
```

## Architecture

The Wikipedia module follows Rustic AI's agent architecture:

- **WikipediaAgent**: Core agent with three processors:
  - `search_wikipedia`: Handles search requests
  - `fetch_page`: Fetches full page content
  - `fetch_summary`: Fetches page summaries
- **Messages**: Pydantic models for requests/responses
- **WikipediaConfigResolver**: Dependency resolver for configuration

## License

Apache-2.0

## Links

- [Rustic AI Homepage](https://www.rustic.ai/)
- [GitHub Repository](https://github.com/dragonscale-ai/rustic-ai)
- [Wikipedia API Documentation](https://www.mediawiki.org/wiki/API:Main_page)
