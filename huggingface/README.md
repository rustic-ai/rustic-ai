# Rustic AI Hugging Face

[Rustic AI](https://www.rustic.ai/) module which provides agents and mixin leveraging [Hugging Face](https://huggingface.co/).

## Installing

```shell
pip install rusticai-huggingface # depends on [rusticai-core](https://pypi.org/project/rusticai-core/).
```

**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/) and uses Pytorch CPU dependency by default.

For models that require authentication, set the environment variable `HF_TOKEN` or use the [huggingface-cli](https://huggingface.co/docs/huggingface_hub/en/quick-start#authentication)

## Building from Source

```shell
poetry install --with dev --all-extras
poetry build
```
