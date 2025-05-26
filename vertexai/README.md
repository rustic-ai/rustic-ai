# Rustic AI VertexAI

Rustic AI module supporting Vertex AI integration

## Prerequisites
1. Using this module requires a Google Cloud Account project with Vertex AI API enabled. The account must have the role `Vertex AI User`.
2. `gcloud CLI` for local development

## Installing

```shell
pip install rusticai-vertexai
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

The library also supports using environment variables `VERTEXAI_PROJECT` and `VERTEXAI_LOCATION` in addition to the ones supported by Google Cloud AiPlatform SDK 
```shell
export VERTEXAI_PROJECT=<project-id>
export VERTEXAI_LOCATION=<location>
```

For local development, 
```shell
gcloud auth application-default login
```
For more options/details, [refer Google Cloud docs](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

On Cloud, It's recommended to use Google Workload Identity.

## Building from Source

```shell
poetry install --with dev
poetry build
```