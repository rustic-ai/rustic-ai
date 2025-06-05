# Rustic AI VertexAI

Rustic AI module supporting integration with [Vertex AI](https://cloud.google.com/vertex-ai)

## Prerequisites
1. Using this module requires a Google Cloud Account project with Vertex AI API enabled. The account must have the role `Vertex AI User`.
2. `gcloud CLI` for local development.

## Installing

```shell
pip install rusticai-vertexai
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

## Building from Source

```shell
poetry install --with dev
poetry build
```

## Usage
The library also supports using environment variables `VERTEXAI_PROJECT` and `VERTEXAI_LOCATION` in addition to the ones supported by [Google Cloud AI Platform SDK](https://cloud.google.com/python/docs/reference/aiplatform/latest) 
```shell
export VERTEXAI_PROJECT=<project-id>
export VERTEXAI_LOCATION=<location>
```

For local development/use, ensure the account you are using has the roles/permissions of `Vertex AI User` and `Service Usage Consumer` at the minimum.
Login using `gcloud CLI` in a terminal
```shell
gcloud auth application-default set-quota-project <project-id>
gcloud auth application-default login
```
For more options/details, [refer Google Cloud docs](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

On Cloud, It's recommended to use Google Workload Identity.
