# Monorepo dependency refresh — 2026-11-25

The refresh audits 111 external dependency names across the root project, 25 packages, and the cookiecutter package template. Runtime, development, documentation and build requirements were checked against the latest non-yanked PyPI releases supporting Python 3.13. Existing GitHub Actions major tags already track the latest releases.

All 26 Poetry lockfiles and the LLM agent's tracked uv lockfile were regenerated. The build backend now uses poetry-core 2.5; CI and the Docker build use Poetry 2.5.2 and the verified tox 4.67.16 / tox-gh-actions 3.5.1 pair. Dev-only names referenced by package test extras now have optional runtime declarations so the published extras are valid.

## Runtime changes

UniDB advances from 5.2.1 to 6.0.0; Uniko from 0.5.1 to 0.6.0. The Uniko integration uses native idempotent agent registration, forwards generic generation-provider configuration, and publishes schemas matching the new SDK. This does not certify new extraction/retrieval capabilities or expose native verified-readiness policy.

The LLM integrations use OpenAI 3.59.0, LiteLLM 1.111.0, LangChain Core 1.8.4, Claude Agent SDK 0.2.189, Transformers 5.24.1 and Google GenAI 3.6.1. Vertex AI already constructs an explicitly configured Google GenAI client; its redundant legacy AI Platform initialization and dependency were removed because that SDK constrains Google GenAI below version 3. Client configuration regressions cover project, location and API selection.

Platform updates include Pydantic 2.14.4, FastAPI 0.165.0, Ray 2.60.1, Redis 8.2.0, Slack SDK 3.48.0 and DuckDB 2.0.1. Unchanged dependencies were also reviewed. Redis 8.2 joins its pub/sub worker inside `stop()`; cleanup must release the manager lock before stopping the worker, because message callbacks acquire that same lock. Two lifecycle regressions verify callback progress, bounded termination, and queue acknowledgement when a handler unsubscribes during delivery.

## Compatibility limits

- python-dateutil remains 2.9.0.post0: botocore 1.44.12 requires `<3`; PyPI's latest 4.0.0 cannot be resolved with the current AWS SDK.
- tenacity resolves to 9.1.4: Google GenAI 3.6.1 requires `<9.2`; latest 9.2.1 is incompatible. This is a transitive dependency.
- OpenTelemetry distro 0.66b2 is the latest available release; this project has no stable release line.
- Existing credential-dependent/model-expensive test gates remain in effect. Provider import and mocked contract tests do not certify live paid model calls.

## Validation

Validation used Python 3.13.12 on macOS ARM64 with CPU native wheels:

- Full repository suite: **2,096 passed, 88 skipped, 3 xfailed, 2 xpassed**, exit 0 in 284.56 seconds. Redis and NATS/JetStream were enabled; credential/model-expensive gates remained enabled. The xfails/xpasses retain their existing incomplete/flaky markers.
- All 26 manifests pass `poetry check --lock`; all 25 package wheels build with valid Python metadata. Wheel sources match the final repository sources and contain no local-path dependency URLs.
- Installed root environment: `uv pip check` passes. Latest tox/GitHub Actions plugin loads successfully.
- Formatting and import ordering pass across 750 Python files; flake8 passes; mypy reports no issues in 721 source files.
- Strict MkDocs build passes; all three UniDB design examples execute against 6.0.0. The original checked-in message fixtures remain labelled as their actual 5.2.1 capture baseline.
- Full isolated Uniko suite: 122 passed, 2 credential-gated skips. Native configuration schema exactly matches the installed 0.6.0 SDK.

The first full attempt exposed the Redis shutdown lock inversion described above. After the fix, the previously stalled thread-isolation integration and both new lifecycle regressions pass in the full suite. The final run emitted no resolver cleanup error or thread timeout.

The repository suite was run with `SKIP_EXPENSIVE_TESTS=true RUN_NATS_TESTS=true sh scripts/run_tests_no_coverage.sh --workers 4 -vv -o faulthandler_timeout=120`, using cached native assets and a matching installed Playwright Chromium browser.

## Credential-free follow-up

Source inspection separated the original 88 skips into 64 live-provider tests, 21 credential-free candidates, one gated local-model download, and two unconditionally deprecated research-guild cases.

The 21 credential-free candidates were attempted: **19 passed** and **2 were blocked by search-engine CAPTCHAs**. Successful runs include four local file/configuration checks, ten public GitHub/skill checks, real CPU inference with Phi-2/Pix2Pix/SpeechT5, and live Bing search plus pagination. DuckDuckGo and Google returned typed CAPTCHA errors rather than search results; those live tests failed their success assertions. No provider-backed inference calls were enabled.

The follow-up removes misplaced credential guards, retains provider/network/expense gates on the appropriate tests, and isolates Claude configuration files and live-browser profiles in temporary directories. Public skill tests now fail on missing assets or API errors rather than turning those failures into permissive skips. Local-model tests wait for actual responses with a bounded timeout instead of fixed sleeps.

Real model execution exposed two SpeechT5 compatibility details: Datasets 5 requires the published Parquet revision instead of the legacy dataset script, and the explicit vocoder must match the pipeline's selected device. Official PyTorch speech weights load directly without optional remote conversion threads. Phi's obsolete tokenizer-only dtype argument was removed. No new runtime dependencies were needed. An additional real SpeechT5 MPS smoke generated 9,216 finite audio samples at 16 kHz, verifying that production accelerator selection remains supported. Public model weights are cached in `/private/tmp/rustic-local-hf-cache` (approximately 10 GB).

The combined local/configuration/skill regression run passes **49 tests, with 26 provider-dependent tests skipped**. Formatting, lint and type checks pass, and the Hugging Face wheel was rebuilt after the compatibility changes. The full-suite result above remains the earlier dependency-refresh baseline; this section records the subsequent focused executions.

## Audited dependency versions

Versions below come from refreshed package lockfiles, including packages used only by individual modules. The package template and CI tools also receive refreshed constraints. Two spelling aliases for PyYAML were present in the original manifest inventory.

| Dependency | Selected version |
| --- | --- |
| aiohttp | 3.14.5 |
| apscheduler | 3.11.3 |
| arxiv | 4.1.0 |
| beautifulsoup4 | 4.15.0 |
| black | 26.10.1 |
| cachetools | 8.0.3 |
| cel-python | 0.5.0 |
| chevron | 0.14.0 |
| chromadb | 1.5.9 |
| claude-agent-sdk | 0.2.189 |
| cookiecutter | 2.7.1 |
| coverage | 7.17.5 |
| datasets | 5.2.0 |
| diffusers | 0.43.0 |
| diskcache | 5.6.3 |
| dotenv | 0.9.9 |
| duckdb | 2.0.1 |
| fakeredis | 2.41.0 |
| fastapi | 0.165.0 |
| fastapi-sso | 0.23.0 |
| flake8 | 7.5.0 |
| flaky | 3.8.1 |
| fsspec | 2026.9.0 |
| gcsfs | 2026.10.1 |
| gitpython | 3.2.1 |
| google-api-python-client | 2.202.0 |
| google-cloud-aiplatform | removed |
| google-cloud-language | 2.22.0 |
| google-genai | 3.6.1 |
| griffe | 2.4.1 |
| httpx | 0.28.1 |
| install-playwright | 1.0.3 |
| isort | 9.0.2 |
| json-merge-patch | 0.3.0 |
| jsonata-python | 0.7.2 |
| jsonpatch | 1.48 |
| jsonpath-ng | 1.16.0 |
| jsonschema | 4.26.0 |
| lancedb | 0.41.0 |
| langchain-core | 1.8.4 |
| langchain-openai | 1.8.5 |
| langchain-text-splitters | 1.2.0 |
| litellm | 1.111.0 |
| markdownify | 1.2.4 |
| mcp | 2.3.0 |
| mdx-truly-sane-lists | 1.3 |
| mkdocs | 1.6.1 |
| mkdocs-material | 9.8.2 |
| mkdocstrings | 1.0.8 |
| mkdocstrings-python | 2.0.11 |
| mypy | 2.4.1 |
| nats-py | 2.17.0 |
| openai | 3.59.0 |
| opentelemetry-api | 1.45.2 |
| opentelemetry-distro | 0.66b2 |
| opentelemetry-exporter-otlp | 1.45.2 |
| opentelemetry-exporter-otlp-proto-grpc | 1.45.2 |
| opentelemetry-sdk | 1.45.2 |
| orjson | 3.13.0 |
| pandas | 3.1.1 |
| pillow | 13.0.0 |
| playwright | 1.65.2 |
| poetry | 2.5.2 (build/CI tooling) |
| poetry-core | 2.5.0 (build/CI tooling) |
| poetry-plugin-mono-repo-deps | 0.3.3 (build/CI tooling) |
| protobuf | 7.36.2 |
| psycopg | 3.3.9 |
| ptvsd | 4.3.2 |
| pyarrow | 26.0.1 |
| pydantic | 2.14.4 |
| pydoc-markdown | 4.8.2 |
| pytest | 9.2.0 |
| pytest-asyncio | 1.5.0 |
| pytest-xdist | 3.8.0 |
| python-dateutil | 2.9.0.post0 |
| python-dotenv | 1.2.4 |
| python-json-logger | 4.2.0 |
| python-multipart | 0.0.34 |
| pyyaml | 6.0.4 |
| PyYAML | 6.0.4 |
| ray | 2.60.1 |
| redis | 8.2.0 |
| requests | 2.34.2 |
| sentence-transformers | 6.3.0 |
| sentencepiece | 0.2.3 |
| serpapi | 1.3.0 |
| shortuuid | 1.0.13 |
| slack-sdk | 3.48.0 |
| soundfile | 0.14.0 |
| spacy | 3.8.18 |
| spacytextblob | 5.1.0 |
| sqlmodel | 0.0.50 |
| starlette | 1.10.0 |
| sympy | 1.14.0 |
| tabulate | 0.10.0 |
| tiktoken | 0.14.0 |
| tomlkit | 0.15.3 |
| torch | 2.15.0, 2.15.0+cpu |
| tox | 4.67.16 |
| tox-gh-actions | 3.5.1 (build/CI tooling) |
| tox-uv | 1.37.9 (build/CI tooling) |
| transformers | 5.24.1 |
| types-cachetools | 7.0.0.20260713 |
| types-python-dateutil | 2.9.0.20261122 |
| types-pyyaml | 6.0.12.20261122 |
| tzdata | 2026.6 |
| tzlocal | 5.4.5 |
| uni-db | 6.0.0 |
| uniko | 0.6.0 |
| uvicorn | 0.54.0 |
| websockets | 17.4 |
