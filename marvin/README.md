# Rustic AI Marvin

[Rustic AI](https://www.rustic.ai/) module which provides text classification and extraction agent using [Marvin](https://www.askmarvin.ai/welcome/what_is_marvin/).

## Installing

```shell
pip install rusticai-marvin
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

Marvin by default uses OpenAI, but it can be configured to use other providers. For example, to use Gemini, 
```shell
export MARVIN_AGENT_MODEL=google-vertex:gemini-2.0-flash
```

Refer [Marvin Docs](https://askmarvin.ai/guides/configure-llms) for more on this.

## Building from Source

```shell
poetry install --with dev
poetry build
```
