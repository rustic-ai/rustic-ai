#!/bin/sh

# Combine coverage data from integration and unit tests
coverage combine --keep coverage/coverage-*

# Print coverage report
coverage report -m --no-skip-covered

# Generate XML report for CI/CD
coverage xml -o coverage.xml 