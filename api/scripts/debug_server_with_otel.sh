#!/bin/sh

opentelemetry-instrument python -Xfrozen_modules=off -m rustic_ai.api_server.main_debug