# Dependency Bumps — PR #114, #112, #109

> **Scope:** Land three open Dependabot PRs that need code work, in order of ascending blast radius.
> **Branches:** all three exist on `origin/dependabot/uv/<pkg>-<version>`. Rebase on `main` before each session.
> **Verification gate:** `make check-full` must pass on each branch before merge. For #109, also `make types` must run cleanly.

---

## Pre-flight (once, before starting)

1. `git fetch origin` — pick up the three Dependabot branches.
2. Confirm no deferred items match these files:
   - `grep -E "embedding\\.py|crypto\\.py|mypy" .agents/deferred-items.json` → empty (already verified).
3. Confirm pin format in `pyproject.toml`: each PR bumps the lower bound only (`openai>=2.33.0` → `>=2.36.0`, etc.). uv.lock carries the resolved version.

---

## Session 1 — PR #114: `openai` 2.33 → 2.36

**Blast radius:** single file + its test. ~10 LOC.

### Root cause
`openai.AsyncOpenAI(api_key=...)` in 2.34+ eagerly validates that `api_key` is non-empty. Today's no-key fallback in `app/knowledge/embedding.py:184` constructs the provider with `api_key=""` after logging a warning — that construction now raises `OpenAIError` and crashes any call to `get_embedding_provider()` when neither `EMBEDDING__API_KEY` nor `AI__API_KEY` is set.

Test that documents the current behaviour: `app/knowledge/tests/test_embedding.py::TestEmbeddingApiKeyFallback::test_warns_when_no_key_available` (asserts `provider._client.api_key == ""` — will break under any fix).

Callers: `app/memory/compaction.py:72`, `app/memory/routes.py:27`, `app/knowledge/service.py:61`, `app/knowledge/proactive_qa.py:177`. None of these guard against a no-key state — they just call `provider.embed(...)`. The graceful no-key path was always "construct now, fail at first `embed()` call." We must preserve that contract: provider construction must NOT raise when key is missing; only `.embed()` should fail.

### Fix — lazy client construction
In `app/knowledge/embedding.py::OpenAIEmbeddingProvider`:
- Stash `_api_key` and `_base_url` on `__init__`; do NOT call `openai.AsyncOpenAI(...)`.
- Add a `_get_client()` method (or `cached_property`) that constructs the client on first use and raises `AIConfigurationError("EMBEDDING__API_KEY or AI__API_KEY required")` when key is empty.
- `embed()` calls `self._get_client().embeddings.create(...)`.

Why lazy: matches `LocalEmbeddingProvider`'s pattern (model lazy-loaded), preserves the no-key fallback shape callers depend on, and the warning at `get_embedding_provider` line 179 still fires loudly in logs.

### Files to modify
| File | Change |
|------|--------|
| `app/knowledge/embedding.py:42–62` | Replace eager `self._client = openai.AsyncOpenAI(...)` with lazy `_get_client()`; rename instance attrs to `_api_key`, `_base_url` |
| `app/knowledge/embedding.py:81` | `await self._client.embeddings.create(...)` → `await self._get_client().embeddings.create(...)` |
| `app/knowledge/tests/test_embedding.py:38, 44, 53` | `provider._client.api_key == "..."` → `provider._api_key == "..."` (no eager client) |
| `app/knowledge/tests/test_embedding.py:46–53` | Add `test_no_key_raises_at_embed_time` (calls `await provider.embed(["x"])` and asserts `AIConfigurationError`) |
| `pyproject.toml` | `openai>=2.33.0` → `openai>=2.36.0` (Dependabot already wrote this on the branch) |

### Verification
1. `git checkout dependabot/uv/openai-2.36.0 && git rebase main`
2. `uv sync --extra dev`
3. `pytest app/knowledge/tests/test_embedding.py -v` — all 4 tests pass; new test confirms lazy-error.
4. `make check-full` — green.
5. Push, ensure CI green, merge.

### Risk
Low. Single-file behavioural change with explicit test coverage.

---

## Session 2 — PR #112: `cryptography` 47 → 48

**Blast radius:** zero application code change expected.

### What 48.0 changes
1. **Drops Python 3.8** — we're on 3.12. ✅ no-op.
2. **CRL signature-algorithm validation** now strict (mismatched inner/outer alg → `ValueError`). We don't parse X.509 CRLs anywhere. Verify with grep below.
3. **Adds ML-KEM / ML-DSA** when OpenSSL ≥ 3.5. Additive.

### Single usage
`app/design_sync/crypto.py` uses only `cryptography.fernet.Fernet` for token encryption. Fernet API is unchanged in 48.0.

### Verification
1. `git checkout dependabot/uv/cryptography-48.0.0 && git rebase main`
2. `uv sync --extra dev`
3. Sanity grep — confirm no surprise CRL/X.509 usage:
   ```bash
   grep -rn "x509\|load_pem_x509\|CertificateRevocationList\|cryptography\\." \
     --include="*.py" app/ services/ | grep -v "fernet\|crypto\\.py"
   ```
   Expected output: empty.
4. `pytest app/design_sync/tests/ -v` (Fernet round-trip test, `can_decrypt`).
5. `make check-full` — green.
6. Push, merge.

### Risk
Low. If grep in step 3 returns hits, switch to investigation mode and document what it found before merging.

---

## Session 3 — PR #109: `mypy` 1.20 → 2.0

**Blast radius:** entire `app/` (strict mode + new defaults). This session is **diagnose → triage → fix**, not a single edit.

### What mypy 2.0 changes (relevant defaults)
| Change | Likely impact |
|--------|---------------|
| `--local-partial-types` ON by default | Variables initialized to `None` then assigned in inner scope: previously inferred broadly, now needs explicit `var: T \| None = None`. |
| `--strict-bytes` ON by default (PEP 688) | `bytearray` / `memoryview` no longer assignable where `bytes` expected. Fix: explicit `bytes(b)` conversion. |
| `--allow-redefinition` semantics changed | Old `--allow-redefinition` ≡ new `--allow-redefinition-new` (more flexible). Anyone relying on the OLD strict behaviour will see new errors. We don't enable this flag → minor risk only. |

`pyproject.toml` already uses `strict = true`, `python_version = "3.12"`, plugin `pydantic.mypy`. No `--allow-redefinition` set. The two flags that bite us are `local-partial-types` and `strict-bytes`.

### Pre-scan (do BEFORE bumping)
```bash
# PEP 688 candidates — bytearray/memoryview where bytes might be expected
grep -rn "bytearray\|memoryview" --include="*.py" app/ | grep -v "tests/"

# None-init pattern that local-partial-types tightens
grep -rEn "^\s*\w+\s*=\s*None\s*$" --include="*.py" app/ | head -40
```
Use the output to size the work before opening the branch.

### Diagnose loop
1. `git checkout dependabot/uv/mypy-2.0.0 && git rebase main`
2. `uv sync --extra dev`
3. `make types 2>&1 | tee /tmp/mypy-2.0-output.log`
4. `grep -E "error:" /tmp/mypy-2.0-output.log | sed -E 's/.*\[([^]]+)\]$/\1/' | sort | uniq -c | sort -rn`
   → frequency table of error codes. Triage top categories first.
5. Spot-check `pyright` separately: `make types` runs both — if pyright passes but mypy doesn't, the issue is mypy 2.0-specific.

### Triage policy (apply per error code)
| Error code | Resolution |
|------------|------------|
| `assignment` (bytes/bytearray/memoryview) | Wrap with `bytes(...)` at the assignment site. Don't widen the receiver's type. |
| `assignment` / `var-annotated` (None-init) | Add explicit annotation: `x: SomeType \| None = None`. |
| `unreachable` (new narrowings) | Investigate — usually a real dead-code finding worth keeping. Remove or `# type: ignore[unreachable]` with comment. |
| `arg-type` involving Pydantic models | Check `pydantic.mypy` plugin updated alongside. If false-positive, narrow the call site, don't suppress globally. |
| Genuinely upstream-broken (3rd-party stub regression) | Add a per-module `[[tool.mypy.overrides]]` with `disable_error_code = [...]` AND a `# TODO mypy-2.0:` comment + tracking deferred-items entry. |

### Acceptance criteria
- `make types` exits 0 on the bump branch.
- `make check-full` exits 0.
- No new `# type: ignore` lines without an accompanying comment explaining why and a deferred-items entry if the suppression is non-trivial.
- If any new `[[tool.mypy.overrides]]` blocks are added, file a deferred-items entry per `.claude/rules/deferred-items.md` so they don't become permanent.

### Time budget
Plan for 1–3 hours of fix work depending on error count from step 4. If the error table > 100 errors, **stop and surface to user** before committing to a single-PR fix vs. splitting the bump.

### Risk
Highest of the three. Mitigation:
- Single CI gate (`make check-full`) is the source of truth — don't merge on a green local run alone.
- If a category of errors looks systemic (e.g., 50+ `assignment` errors from a Pydantic plugin regression), pause and consult before bulk-fixing.

---

## Sequencing & coordination

Run in order: **#114 → #112 → #109**. Each session ends with a merged PR before the next begins, because:
- #114 and #112 are independent of each other and of #109.
- #109 may rebase-conflict with anything that lands during its session, so do it last.
- Each merge unblocks Dependabot from re-resolving the lockfile; rebasing the next PR onto the freshly-bumped main keeps lock churn minimal.

After all three merge, run `make check-full` on `main` once to confirm no integration drift.

---

## Out of scope (explicitly)
- Updating other dependencies that the lockfile resolution may pull along — only the three named bumps.
- Refactoring `OpenAIEmbeddingProvider` beyond the lazy-init fix (e.g., consolidating with `LocalEmbeddingProvider`).
- Auditing other `Fernet` users (there are none).
- Bulk-fixing pre-existing `# type: ignore` lines unrelated to mypy 2.0's new errors.
