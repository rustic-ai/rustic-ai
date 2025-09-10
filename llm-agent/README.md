# Rustic AI LLMAgent

This module introduces a pluggable LLMAgent based on common patterns observed while using of language models within [Rustic AI](https://www.rustic.ai/) guilds.
The implementation leverages the Rustic AI's LLM dependency injection to allow for custom implementations of the LLM.

## Installing

```shell
pip install rusticai-llm-agent rusticai-litellm
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

## Building from Source

```shell
poetry install --with dev
poetry build
```