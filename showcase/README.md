# Rustic AI Showcase

Module that showcases Rustic AI capabilities

## Installing

```shell
pip install rusticai-showcase
```

## Building from Source

```shell
poetry install --with dev
poetry build
```

## PaperBanana

[PaperBanana v2](apps/paper_banana_guild.json) uses Uniko document memory and bounded illustration refinement. Read the [complete guide](../docs/showcase/paper_banana.md) for setup, inputs, typed outcomes and local verification.

## Semantic Memory Assistant

The [v2 guide](../docs/showcase/semantic_memory_assistant.md) documents private Uniko
conversation memory, shared document evidence, bounded web tool rounds, typed
commit acknowledgment and deployment configuration.

## Blueprint catalog

The installed package includes the same JSON blueprints authored in `apps/`. Load
an envelope by its canonical relative catalog path, then apply deployment
configuration before creating a guild:

```python
from rustic_ai.showcase.catalog import list_blueprints, load_blueprint

names = list_blueprints()
blueprint = load_blueprint("iterative_studio/iterative_studio.json")
spec = blueprint["spec"]
```

Catalog dependencies are runtime dependencies of the showcase package. Catalog
flows that use agent or guild state must bootstrap a guild with its manager and
metastore; launching only the agent specs does not provide state management.

Installed artifact acceptance checks require a fresh environment containing the
current monorepo wheels and their runtime dependencies, without editable
installations or retired packages. From the repository root, use that
environment's Python:

```shell
RUSTIC_INSTALLED_ACCEPTANCE=1 /path/to/clean-env/bin/python -m pytest \
  showcase/tests/test_installed_artifacts.py
```

These checks verify installed module provenance, retired import absence,
blueprint resources and class imports, and native vector operations with a local
embedding function. Building these checks does not publish artifacts.
