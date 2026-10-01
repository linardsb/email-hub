# Plan: guard remote ESP template IDs before they reach provider URLs

Branch `fix/connectors-remote-template-id-ssrf` (worktree `../email-hub-ssrf`, cut from `origin/main` `fd1f25cc`).

## Problem

A user-supplied remote template ID is interpolated unchecked into every ESP provider URL
(e.g. `app/connectors/sendgrid/sync_provider.py:103` `f"{self._base_url}/templates/{template_id}"`).
`../x`, `a?b=c` and `a#b` reach other paths on the provider's API with the connection's stored
credentials attached (partial SSRF, CWE-918). Found by inspection; CodeQL does not flag it
(alert 238 was the Tolgee `project_id` flow, fixed in #417).

| Source | Where | Reaches |
|---|---|---|
| Path param `template_id: str` | `app/connectors/sync_routes.py:110` (`get_remote_template`) | `ConnectorSyncService.get_remote_template` → `provider.get_template` |
| Body `ESPImportRequest.template_id: str` | `app/connectors/sync_schemas.py:64` | `ConnectorSyncService.import_template` → `provider.get_template` |

Other `template_id`s on the push/export paths are local `int` IDs; remote IDs there come from ESP responses, not users.

## Change

| File | Change |
|---|---|
| `app/connectors/exceptions.py` | Add `InvalidRemoteTemplateIdError(DomainValidationError)` (422). |
| `app/connectors/sync_service.py` | Module-level `_REMOTE_TEMPLATE_ID_RE = re.compile(r"[A-Za-z0-9@][A-Za-z0-9@_.:-]{0,255}")`. Inline `if not _REMOTE_TEMPLATE_ID_RE.fullmatch(x): raise ...` at the top of `get_remote_template` and `import_template`, before any DB or network work. Inline (not a helper) because CodeQL's `StringRestrictionSanitizerGuard` only treats a `fullmatch` guard on the same variable as a barrier. |
| `app/connectors/tests/test_sync_service.py` | Parametrised rejection tests (`../x`, `a/b`, `a?b=c`, `a#b`, `..`, `""`, 257 chars) asserting the error and that neither BOLA lookup nor provider is called; acceptance test over real ID shapes from provider tests (`tpl_1`, `d-55`, `TMPL_5`, `cb_2`, `200`, UUID, Adobe-style `@AbC-12_x`). |

Allowed set (derived from ID shapes in `app/connectors/*/tests` and `services/mock-esp`): letters, digits, `@ _ . : -`; first char alphanumeric or `@`, so bare `.`/`..` segments are refused. Max 256 chars.

## Validation

1. RED: new tests fail on unmodified service → verify: pytest shows the rejection cases failing.
2. GREEN: implement → verify: `uv run pytest app/connectors/tests/test_sync_service.py` passes.
3. `make check-full` green, then re-read `git diff` (lint rewrites files).
4. Draft PR; CI `codeql` must not add alerts.

No schema or OpenAPI change, so no SDK regen. No migration.
