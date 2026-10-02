# Rustic AI SerpApi

This module provides an agent that can be used to Search the web using [SerpApi](https://serpapi.com/)


## Installing

```shell
pip install rusticai-serpapi
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

## Local search without an API key

`LocalSERPAgent` is a drop-in replacement for `SERPAgent` for guilds that run on a user's own machine. It drives the user's installed Chrome through Playwright, so it needs no SerpAPI key. Use `SERPAgent` on shared or hosted infrastructure.

```shell
pip install "rusticai-serpapi[local]"
python -m rustic_ai.serpapi.local_setup   # optional one-time step: accept consent pages, solve a CAPTCHA, sign in
```

In the guild spec, use `"class_name": "rustic_ai.serpapi.local_agent.LocalSERPAgent"`. Set `"headless": false` for a real, minimized Chrome window: Google is far less likely to block it, and if a CAPTCHA does appear, the window pops up so you can solve it. When a search is blocked or fails, the agent sends a `SearchError` with a `reason` and doesn't switch engines by itself.

See [docs/agents/serpapi/local_serp_agent.md](../docs/agents/serpapi/local_serp_agent.md) for modes, errors and configuration.

## Building from Source

```shell
poetry install --with dev
poetry build
```