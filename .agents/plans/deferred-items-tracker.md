# Deferred-Items Tracker — Sequenced Closure Plan

**Source:** `.agents/deferred-items.json` (8 open items as of 2026-05-08).
**Sequencing rule:** Severity-first — known-bugs (real or imminent risk) close before soft/speculative items. Each cluster has a dedicated plan; this file is the contract for ordering, branching, and closure-evidence.
**Calendar:** F013-D3 closed by `d9132c7c` on 2026-05-08 (today). Operational follow-up in `TODO.md` is now stale and is retired as Cluster F below.

## Closure order

| # | Cluster | Plan | Severity | Risk if skipped | Branch | Done when |
|---|---------|------|----------|-----------------|--------|-----------|
| 1 | **A — Connector OAuth caches** | `tech-debt-04-connector-oauth-cache.md` | known-bug | Cross-tenant token reuse on SHA-256[:16] collisions; unbounded cache | `tech-debt/04-connector-oauth-cache` | Both `sync_provider.py` files use `LruWithTtl(64)` keyed by `f"{vendor}:{client_id}"`; cross-tenant test added |
| 2 | ~~**B — Alembic schema drift**~~ | ~~`tech-debt-19-alembic-schema-drift.md`~~ | ~~known-bug~~ | ~~Future `--autogenerate` run produces destructive 200-op migration~~ | ~~`tech-debt/19-alembic-drift`~~ | ~~`alembic check` exits 0 against fresh DB; CI step drops `continue-on-error: true`~~ — **closed 2026-05-10** via `normalize_schema_drift` migration. |
| 3 | **C — Tenant-isolation harness** | `tech-debt-03-tenant-isolation-harness.md` | soft | New repo ships without `scoped_access` filter; no integration net catches it | `tech-debt/03-tenant-iso-harness` | `make test-integration` runs `test_tenant_isolation.py` green w/o `TEST_DATABASE__URL` gate; 4 xfail entries promoted |
| 4 | **D — Design-sync 50.7 cluster + stranded templates** | `phase-50.8-lego-promotion-and-detector-followup.md` | soft + speculative (4 entries) | Phase 52.7 dark-mode flip mis-inverts physical cards; Phase 51A regressions ship invisible | `phase/50.8-lego-promotion` | LEGO + performance_reimagined + slate in `data/debug/`; `make converter-data-regression` covers them; gap-2/gap-3 empirically closed or moved to confirmed-bug status. Independent of Cluster C — does not need the integration harness. |
| 5 | **E — Pyright `reportDeprecated` demotion** | `tech-debt-pyright-deprecation-restore.md` | speculative | Real Pydantic v3 / SQLAlchemy 2.x deprecations land as warnings, slip CI | `tech-debt/pyright-restore-deprecated` | `reportDeprecated = "error"` restored OR upstream fix documented in code comment with version pin |
| 6 | ~~**F — F013-D3 stale follow-up cleanup**~~ | ~~`f013-d3-operational-followup-cleanup.md`~~ | ~~done-already~~ | ~~Stale operational follow-up survives in `TODO.md` and `deferred-items.json`~~ | ~~(any branch)~~ | ~~`TODO.md` follow-up removed; `tooling_followups[]` updated with `closed: 2026-05-08`~~ — closed; `TODO.md` cleanup landed on `docs/tech-debt-09-session-blocks` (no `tooling_followups[]` edit needed — verified no matching entry). |

## Why this order

**1 & 2 are known-bugs with real-world failure modes.** Cluster A is a security bug
(SHA-256[:16] truncation = 1-in-2^64 collision chance per tenant, but cross-tenant
token reuse on collision); Cluster B is a footgun where any unguarded
`alembic revision --autogenerate` corrupts production. Both deserve to land before
soft items.

**3 and 4 are independent**, but if both are queued, prefer landing C first —
not because D needs C, but because the integration harness investment from C
compounds across every later integration-flavoured test (D's regression
fixtures, the briefs follow-up isolation variant, future agent-pipeline
end-to-end tests). Sequencing by harness-payoff, not direct dependency.

**5 is mechanical** but blocked on a pyright bump cycle; do it last so it doesn't
gate higher-value work.

**6 is bookkeeping** — fold it into the first PR that touches `TODO.md` rather than
spinning a dedicated session.

## Branching strategy

Each cluster gets its own branch (column 6). Do **not** chain them: Cluster A and
Cluster B are independent and can be reviewed in parallel. Cluster C depends on
neither but should land before D so D's regression net inherits the integration
harness. Cluster E is independent of everything.

```
main
 ├── tech-debt/04-connector-oauth-cache       (Cluster A)
 ├── tech-debt/19-alembic-drift                (Cluster B, parallel with A)
 ├── tech-debt/03-tenant-iso-harness           (Cluster C, parallel-safe with A/B)
 ├── phase/50.8-lego-promotion                 (Cluster D, parallel-safe with A/B/C)
 └── tech-debt/pyright-restore-deprecated      (Cluster E, any time)
```

## Per-PR checklist (every cluster)

Each cluster's PR must:

1. Update `.agents/deferred-items.json` — change matching entry's `status` from
   `"deferred"` to `"closed"`, add `"closed_commit": "<short SHA>"` and
   `"closed": "<YYYY-MM-DD>"`. **Do not delete the entry** — closed history is
   debugging fuel.
2. Update the cluster's row in this tracker — strike the row out and link the PR
   number, e.g. `~~Cluster A~~ — closed in #145`.
3. Run `/preflight-check` against the plan; the deferred-items table must surface
   only the entry being closed (not collateral matches).
4. Backend gates: `make check-full`. If touching agents, also `make eval-check`.

## Open questions to resolve before starting

- **Cluster A — full migration vs. surgical bandaid?** Plan defaults to the
  surgical bandaid (Option B in `deferred-items.json`) because the
  `OAuthConnectorService` ABC is shaped for `export()` (one-shot push) and the
  `sync_provider.py` surface is bidirectional CRUD (`list/get/create/update/delete`
  + `validate_credentials`). Full unification needs a sibling `OAuthSyncProvider`
  ABC and is out of scope. Re-open if the connector team wants the proper fix
  bundled.
- **Cluster B — single mega-migration vs. split?** Plan defaults to single
  migration to match the `closes_when` clause in the deferred entry. If the
  squawk gate flags any of the column changes as table-rewriting, split the
  high-risk columns into a separate migration with `op.execute()` + `SET DEFAULT`
  pattern.
- **Cluster D — pull LEGO forward into 51A vs. wait for 53.6?** Plan does the
  former (slim 51.0 task). 53.6 is too far out and 51A composite-slot work targets
  LEGO's footer membership card, so the data has to land before 51A starts
  anyway.

## Status updates

Edit this section as work lands. Format: `YYYY-MM-DD — Cluster <X> — <state>`.

- 2026-05-08 — Cluster F — closed in `d9132c7c` (shipped early; `TODO.md` cleanup
  pending in next PR that touches that file).
- 2026-05-09 — Cluster F — `TODO.md` cleanup applied on
  `docs/tech-debt-09-session-blocks`; one-line closing note replaces the
  stale readiness-check block. No `deferred-items.json` edit (verified no
  matching `tooling_followups[]` entry). Followup plan's "Done When" already
  showed Part D3 `[x]` from `113e1114`. Cluster F retired.
