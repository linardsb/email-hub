# ADR 0001 — Cognee dependency surface isolation

- **Status:** Proposed (discovery only — no code change in audit Phase 3 §3.6)
- **Date:** 2026-04-28
- **Driver:** `docs/email-hub-audit.md` §3.11; `.agents/plans/audit-implementation.md` Phase 3 §3.6

## Context

`cognee` is the optional graph-memory backend used by the Knowledge agent. It is declared as an **optional extra** (`pyproject.toml [project.optional-dependencies].graph`) and is gated at runtime by `KNOWLEDGE__USE_GRAPH` / `COGNEE__ENABLED`. When the graph is disabled (the default in dev), no cognee code path executes.

However, even with the feature flag off, **every developer environment that runs `uv sync --all-extras` (or the default install)** pulls cognee's transitive surface. As of April 2026 that includes `litellm`, `onnx`, `pypdf`, `aiohttp`, `mako`, `pygments`, `requests` — each of which has appeared in past Dependabot advisories. Project history (`pyproject.toml:60-69`) shows we have had to pin transitives manually multiple times to keep the tree CVE-clean.

### Cognee call-site footprint (today)

Direct imports of `cognee` in the codebase:

| Site | Purpose |
|------|---------|
| `app/knowledge/graph/config.py:23` | One-shot `cognee.config.set_*` during init |
| `app/knowledge/graph/cognee_provider.py` (7 sites) | `add()`, `cognify()`, `search()` calls — graph CRUD |
| `app/knowledge/seed.py:107,171` | Seed data ingestion via the provider wrapper |

All seven call sites are funneled through the `cognee_provider.py` adapter — there is **one** logical interface (`GraphMemoryProvider`) and a single concrete implementation (`CogneeProvider`). The adapter already isolates the rest of `app/` from cognee's API.

### Audit ask

> Investigate isolating cognee in a separate Docker service so its transitive
> surface stops landing in the API container.

## Decision

**Defer.** Draft three options, recommend the user pick one before any code lands.

## Options considered

### Option A — Status quo (in-process, optional extra)

Keep cognee as today: `pyproject.toml` optional extra, runtime-gated. Continue manual transitive pinning via `[tool.uv].constraint-dependencies`.

- **Pros:** zero migration cost; cognee stays in-process so calls are sub-millisecond.
- **Cons:** every `uv sync --all-extras` still pulls the surface. Dependabot churn continues. Production image carries cognee even when `KNOWLEDGE__USE_GRAPH=false`.

### Option B — Sidecar service (HTTP boundary)

Move cognee into a separate container behind a thin HTTP API (FastAPI app under `services/cognee-graph/`). `CogneeProvider` becomes an HTTP client; the main image drops cognee from its lockfile.

- **Pros:** clean dependency boundary — main image's CVE surface shrinks materially; cognee can scale independently; sidecar can be turned off entirely in deployments that don't need the graph.
- **Cons:** new container to operate (deploy, monitor, secret-distribute). Latency moves from sub-ms to ~5–20 ms per call. Coolify deploy needs a second service entry. Auth between API and sidecar needs design (mTLS, shared secret, network policy).
- **Estimated effort:** ~1 week — sidecar scaffold, HTTP API surface (≤6 endpoints matching `GraphMemoryProvider`), client adapter, docker-compose entry, deploy doc update, integration test against sidecar.

### Option C — Subprocess/IPC sandbox

Run cognee in an in-process subprocess sandbox (`multiprocessing` or `pyodide`-style WASM). Main process imports nothing from cognee.

- **Pros:** keeps a single deploy artefact; isolates the dep tree at the process boundary so `pip-audit` only sees cognee in the worker venv.
- **Cons:** complex IPC layer; doesn't actually shrink the docker image (cognee still installed); doesn't help Dependabot — same package set still scanned. Effectively all of B's downsides without B's upside.
- **Estimated effort:** ~2 weeks (and likely abandoned — IPC in Python is fragile).

## Recommendation

**Pursue Option B once the audit Phase 2 SCA gates (`pip-audit`, Trivy) start surfacing cognee transitives at a cadence > 1 per quarter.** Until then, Option A is the right cost/benefit point.

Trigger criteria (any one fires the migration):
1. Dependabot opens >2 cognee-transitive PRs in any rolling 30-day window.
2. A cognee transitive lands a CRITICAL CVE that `pip-audit` blocks releases on.
3. We ship a deployment topology where cognee is *not* used (e.g. an "API-only" tier).

## Open questions for the user

- Are we OK with Option A as the steady state for the next ~quarter? If yes, this ADR sits in `Proposed` and we revisit on trigger.
- If we move to Option B, do we want the sidecar to also host the embedding model (currently `app/embedding/`), or is that out of scope?
- Do we deploy the sidecar to Coolify alongside the API, or to a separate compute pool?

## Follow-up

When this ADR is accepted, the implementing plan should cover:
- `services/cognee-graph/` — FastAPI app, Dockerfile, requirements
- `app/knowledge/graph/cognee_provider.py` — swap from in-process import to httpx client
- `pyproject.toml` — drop cognee from `[project.optional-dependencies].graph`; add `cognee` only to `services/cognee-graph/requirements.txt`
- `docker-compose.yml`, `docker-compose.observability.yml` — new `cognee-graph` service entry
- `docs/deploy-hetzner-coolify.md` — second service deploy instructions
