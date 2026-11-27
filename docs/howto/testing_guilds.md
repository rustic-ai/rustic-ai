# Testing composed guilds

A guild test should execute the authored specification, retain the production agent classes, and observe the messages at its public boundary. Component tests alone cannot detect consumed fan-out routes, missing state services, stale event names or a tool result that loses its correlation identity.

## Load the shipped catalog

The showcase package ships the same JSON files used for authoring. The loader works in a checkout and from installed wheel resources:

```python
from rustic_ai.showcase.catalog import list_blueprints, load_blueprint

names = list_blueprints()
envelope = load_blueprint("semantic_memory_assistant.json")
```

Names are canonical paths relative to the catalog, including `iterative_studio/iterative_studio.json`. Unknown names and traversal paths are rejected. Render declared configuration placeholders before validating a `GuildSpec`; retain the catalog's agents, predicates, routes and toolsets in the test.

Stateful flows need the guild manager. Use `GuildBuilder.bootstrap(database_url, organization_id)` with an isolated metastore to exercise state updates, dynamic agent launch and guild-to-guild messaging. `GuildBuilder.launch()` is appropriate for component fixtures that do not need those services. Always shut down the returned guild after the test; its manager also releases the actors it launched. Add a real User Proxy when testing Studio input, and observe its output along with the framework error topic. User input may itself be broadcast; count terminal output by its producer and status.

## Test capability boundaries

Use deterministic LLM resolvers and local substitutes for external API clients. Keep native Uniko stores, Chroma, filesystem access, SQL/data tools, coordinator barriers and message routing active. Assert what the final model actually received, the tool's persistent effects and the final typed outcome. No hosted generation keys are needed for these local acceptance tests.

| Catalog | Composed behavior covered |
|---|---|
| PaperBanana | Uploaded sources, native document recall, generation, revisions, restart and failure paths |
| Semantic Memory Assistant | Native conversation memory, uploads, web tool continuation, source isolation, invalid input, deadline and restart |
| Uni-DB assistant and diagnostics | Typed database tools, native queries, plans, indexes and correlated outcomes |
| Uniko Research and Researcher | Native or vector retrieval, search fan-out, ingestion, synthesis and result routing |
| Iterative Studio | All five modes, bounded revision loops, fallback and separate requests |
| LLM Council | Opinion fan-out, aggregation, peer review and chairman output |
| Debate | Bounded alternating turns and fact-check presentation |
| Multi-LLM | Tagged starter agents, dynamic launch and typed memory rehydration |
| Personal Workspace | MCP tool identity/results through orchestration and summary; moderation stop |
| ReAct data analyst and Todo | Native data/task tool loops and user presentation |
| VendingBench and player | Paired guild tool handoffs, supplier discovery, owner-scoped registry reads and simulation state |
| UI components | User entry and routing of every component message |

The catalog tests live in `showcase/tests/catalog`; established consumer tests remain in their existing showcase and package directories. Run relevant suites after changing a protocol or route:

```bash
.venv/bin/pytest showcase/tests uniko-agent/tests \
  playwright/tests/agent/test_bounded_scraping.py \
  llm-agent/tests/agent/test_memories_stores.py \
  testing/tests/test_repository_scripts.py
```

Each test metastore uses its own identity, including when independent processes run the same case. Exercise both synchronous and threaded engines where timing, admission or state publication matters. Cover early source failure, expiry before dispatch, late delivery, duplicate replies and shutdown. Check that one intentional terminal outcome is produced and expired work cannot start a native operation. Memory tests also inspect stored records to ensure rejected evidence and synthetic feedback do not become user assertions.

## Verify installed artifacts

Build fresh wheel and source outputs. `scripts/run_on_each.sh` reports all failing modules and exits unsuccessfully if any command fails. `scripts/poetry_build.sh` stages each fresh build and publishes the aggregate only when all builds succeed; stale module output cannot enter the aggregate, and existing non-artifact entries are preserved.

Create a separate environment, install fresh wheels with the repository's locked dependencies, and run:

```bash
RUSTIC_INSTALLED_ACCEPTANCE=1 /path/to/clean-env/bin/python -m pytest \
  showcase/tests/test_installed_artifacts.py
```

These tests require non-editable package metadata and module paths inside the clean environment. They verify retired imports are absent, generic native vector operations still work, every catalog resource is present, and catalog agent/plugin classes resolve from installed distributions. Run composed catalog and consumer flows in that same environment to verify runtime behavior beyond import checks.

Native tests need local model assets and permission to read their cache. Installed-artifact tests intentionally skip unless their environment flag is enabled. Hosted provider availability, distributed deployment scheduling and persistent-volume durability require separate checks in the target deployment.
