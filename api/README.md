# Rustic AI API
This module provides the backend server for the Rustic AI framework. It provides the interface for creating and interacting with guilds.
The interaction with a guild is supported through a Websocket interface, allowing for real-time communication and updates.

## Installing

```shell
pip install rusticai-api
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/) and [rusticai-ray](https://pypi.org/project/rusticai-ray/).

## Running from source

1. Install required dependencies:
```shell
poetry install --with dev
poetry shell
```

2. Start the server:
```shell
# If using an external SQL database, expose RUSTIC_METASTORE to the corresponding url 
# For example, if using postgres, export RUSTIC_METASTORE=postgresql+psycopg://user:pwd@localhost:5432
./scripts/dev_server.sh
```

Server will be available at `http://localhost:8880` by default. The API documentation can be accessed at `http://localhost:8880/docs`.

## Running from source with Telemetry

1. Install required dependencies:
```shell
poetry install --with dev
poetry shell
```

2. Start Zipkin server - requires [Docker](https://www.docker.com/get-started/)
```shell
sudo chmod 777 scripts/zipkin/data-tmp/
./scripts/zipkin/zipkin_up.sh
```

3. Set the otel env variables -
```shell
export OTEL_SERVICE_NAME=GuildCommunicationService
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://localhost:4318/v1/traces"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
```
Refer [docs](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/#endpoint-configuration)
for details.

3. Start the server -
```shell
./scripts/dev_server_with_otel.sh
```
Traces will be visible in Zipkin UI at http://localhost:9411/zipkin/

Note: To stop the Zipkin server, use `./scripts/zipkin/zipkin_down.sh`

**To run with all the available `rusticai` packages, use the poetry environment from the root directory, and prefix commands with `api/` — for example, use `./api/scripts/dev_server_with_otel.sh` instead of `./scripts/dev_server_with_otel.sh`.**
