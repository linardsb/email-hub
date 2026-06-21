# Plan: Close briefs import_items BOLA (unscoped get_items_by_ids)

## Context
`BriefService.import_items` fetches source items via `BriefRepository.get_items_by_ids`,
which runs `select(BriefItem).where(BriefItem.id.in_(ids))` with **no ownership scoping**.
Import only `_verify_access`-checks the *destination* project, never the *source* items —
a cross-user BOLA leak (deferred entry `tech-debt-03-briefs-import-items-unscoped-read`,
sibling of the `get_item_detail` fail-open fixed in `a188f802`). Brief ownership is
`item → connection_id → BriefConnection.created_by_id`; every other read in the repo
already filters on it via `scoped_access`. `import_items` is the **only** caller of
`get_items_by_ids` — scoping it is safe.

## Files to Create/Modify
- `app/briefs/repository.py` — `get_items_by_ids`: add owner scoping (mirror `list_items`).
- `app/briefs/service.py` — `import_items`: replace `if not items` with a full-coverage
  guard raising `BriefItemNotFoundError` (404) so non-owned/missing ids fail loud
  instead of being silently dropped (mirror the `get_item_detail` fix shape).
- `app/tests/test_briefs_user_isolation.py` — add repo-level + route-level BOLA tests.
- `app/briefs/tests/test_service.py` — add a `TestImportItems` service-guard unit test.
- `.agents/deferred-items.json` — flip the entry to `closed` + `closed_note`.

## Implementation Steps
1. **`get_items_by_ids`** — mirror `list_items` (repository.py:168-194):
   ```python
   access = scoped_access(self.db)
   stmt = select(BriefItem).join(BriefConnection).where(BriefItem.id.in_(item_ids))
   if access.project_ids is not None:
       stmt = stmt.where(BriefConnection.created_by_id == access.user_id)
   ```
   Join is safe for admins (`project_ids is None`): `connection_id` is `NOT NULL`,
   so the inner join drops nothing.
2. **`import_items`** — replace the `if not items` block:
   ```python
   if len(items) != len(set(brief_item_ids)):
       raise BriefItemNotFoundError("One or more brief items not found")
   ```
   `set(...)` dedups so duplicate ids in the request don't false-trip. Covers both
   all-missing (was 422) and partial-ownership (was a silent leak) → 404.
3. **Integration tests** (collect-skip without `TEST_DATABASE__URL`):
   - `test_get_items_by_ids_filters_by_creator`: owner scope returns the item;
     non-owner scope returns `[]`.
   - `test_import_items_denies_other_user`: same body, uuid-suffixed nonexistent
     project name — user2 → 404 (blocked at item gate), user1 → 422 (passed item gate,
     fails at project lookup). The 404-vs-422 split proves it's the item-ownership gate.
4. **Unit test** (`test_service.py`, runs without a DB — the only local signal for the
   service guard): mocked `get_items_by_ids` returns a subset of requested ids →
   `BriefItemNotFoundError`.
5. **Ledger**: set `tech-debt-03-briefs-import-items-unscoped-read` → `closed`, add
   `closed_note` + `"closed_commit pending commit"`.

## Security Checklist
- Endpoint already has auth (`require_role("developer")`) + rate limit (`10/minute`) — unchanged.
- Fix tightens an existing BOLA; no new endpoint/surface.
- Error is generic (`"One or more brief items not found"`) and BOLA-safe — does not reveal
  whether an id exists vs. is non-owned (both → 404, matching `get_item_detail`).

## Verification
- [ ] `app/briefs/tests/` unit tests pass (incl. new service-guard test).
- [ ] ruff + mypy + pyright clean on touched files.
- [ ] Repo SQL scoping verified by the CI integration job (`make test-integration`,
      docker-gated) — collect-skips locally; unit test covers the service guard only.
- [ ] `git diff` is limited to briefs files + deferred-items.json + this plan + the new
      test; no unrelated `git status` modifications leak in.
