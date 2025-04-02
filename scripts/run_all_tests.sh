#!/bin/bash

# Create a directory to store coverage data
rm -rf coverage
mkdir coverage

# Run pytest directly with the desired parameters and pass all script arguments to pytest
PYTHONFAULTHANDLER=true coverage run --context=TESTS --data-file=coverage/coverage-tests -m pytest -vvvv --showlocals

