# Core language & runtime
- **Python 3.12+** — stable, great perf, long support window.
- **uv** — your standard for fast, reproducible env + resolver.

# CLI & UX
- **Typer** (on top of Click) — ergonomic CLIs with type hints.
- **Rich** — pretty console output, progress bars, trace previews.
- **platformdirs** — OS-correct cache/config dirs.
- **filelock** — safe concurrent file access.

# Config, YAML & templating
- **ruamel.yaml** — robust YAML 1.2 with round-trip (preserves comments/anchors).
- **Jinja2** — template prompts/inputs safely.
- **pydantic v2 + pydantic-settings** — typed config models; env + .env override.
- **jsonschema** — validate workflow specs (Draft 2020-12).

# Orchestration & data models
- **graphlib** (stdlib) — topological sorts for DAG/workflow.
- **anyio** — structured concurrency that works with asyncio/threads.
- **tenacity** — mature retries with backoff.
- **JMESPath** — safe, declarative expressions for routing/guards.

# LLM/Agents (AWS-first)
- **boto3 / botocore** — Bedrock/Agents/Secrets Manager integration.
- **(optional) openai** — if you ever need cross-provider fallback.
- **(optional) mcp** — Model Context Protocol client/server for tool bridges once you want skill/tool interop.

# HTTP, I/O, serialization
- **httpx** — async/sync HTTP client (timeouts, retries, HTTP/2).
- **orjson** — fast JSON (use for logs/artifacts; fall back to stdlib for edge cases).
- **python-dotenv** — load local secrets in dev only.

# Observability & reliability
- **opentelemetry-sdk**
- **opentelemetry-exporter-otlp**
- **opentelemetry-instrumentation-logging**
- **opentelemetry-instrumentation-httpx**
- **structlog** — structured logs (route to JSON; wire to OTEL).
- **prometheus-client** — optional local metrics if you want /metrics.

# Security & secrets
- **boto3 (Secrets Manager / SSM Parameter Store)** — production secrets.
- **python-dotenv** — dev-only secrets loading (guard behind a flag).

# Persistence & caching
- **sqlite3** (stdlib) — durable local state (runs everywhere).
- **diskcache** — fast, file-system cache for tool results/artifacts.

# Packaging, linting, quality
- **hatchling** — simple, modern PEP 517 build backend.
- **ruff** — formatter + linter + import sorter (one tool).
- **mypy** — type checking (pydantic v2 compatible stubs).
- **pytest**, **pytest-asyncio**, **coverage.py** — tests & coverage.

# Docs & examples
- **MkDocs + Material** — fast, readable docs; great for CLI how-tos.
- **mkdocstrings[python]** — auto-docs from type hints.

---

## Suggested minimal dependency set (to start)

```
typer
rich
ruamel.yaml
jinja2
pydantic>=2
pydantic-settings
jsonschema
anyio
tenacity
jmespath
httpx
orjson
structlog
opentelemetry-sdk
opentelemetry-exporter-otlp
opentelemetry-instrumentation-logging
opentelemetry-instrumentation-httpx
boto3
python-dotenv
diskcache
ruff
mypy
pytest
pytest-asyncio
coverage
hatchling
platformdirs
filelock
```

### uv quickstart
```bash
# initialize
uv init strands-cli
cd strands-cli

# add runtime deps
uv add typer rich ruamel.yaml jinja2 pydantic pydantic-settings jsonschema anyio tenacity jmespath httpx orjson structlog \
opentelemetry-sdk opentelemetry-exporter-otlp opentelemetry-instrumentation-logging opentelemetry-instrumentation-httpx \
boto3 python-dotenv diskcache platformdirs filelock

# add dev deps
uv add --dev ruff mypy pytest pytest-asyncio coverage hatchling mkdocs mkdocs-material mkdocstrings[python]
```

---

## Why these picks (brief)
- **Typer/Rich** are the de-facto combo for modern CLIs with great UX.
- **ruamel.yaml + jsonschema + pydantic** gives you schema-first safety, round-trip editing, and strong typing.
- **anyio + tenacity** keeps concurrency and retries clear and portable.
- **JMESPath** is mature (AWS CLI uses it) for routing/guards in YAML without eval().
- **httpx + orjson** are fast and well-maintained for network + JSON throughput.
- **OTEL + structlog** gives you vendor-neutral tracing/metrics/logs you can ship to AWS Observability stacks.
- **boto3** aligns with Bedrock/Agents/Secrets Manager; no exotic SDK exposure.
- **sqlite3/diskcache** cover durable state and caching without ops burden.
- **ruff/mypy/pytest** keep the codebase tight and high-quality; one linter/formatter.