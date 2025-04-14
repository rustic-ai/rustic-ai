# Rustic AI Hugging Face

[Rustic AI](https://www.rustic.ai/) module which provides agents and mixin leveraging [Hugging Face](https://huggingface.co/).

## Installing

```shell
pip install rusticai-huggingface # depends on [rusticai-core](https://pypi.org/project/rusticai-core/).
```

PyTorch and Hugging Face Transformers are optional dependencies. To install them, use the desired extras:

```shell
# for only audio models - text-to-speech
pip install rusticai-huggingface[audio] 

# for only image models - image generation
pip install rusticai-huggingface[image] 

# for only LLMs - text generation
pip install rusticai-huggingface[llm]

# for all of the above
pip install rusticai-huggingface[all]
```


## Building from Source

```shell
poetry install --with dev --all-extras
poetry build
```
