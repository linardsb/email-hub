# Logging standard (reference)

Structured JSON logs via structlog. Event names are `domain.action_state` (two parts), per
`.claude/rules/backend.md` ("Log events: `domain.action_state` pattern").

- **Logger:** `from app.core.logging import get_logger`, then `logger = get_logger(__name__)` at module level
  (e.g. `app/connectors/service.py:37`). No `print()` in `app/`: ruff `T20` is selected (`pyproject.toml:143`;
  only `app/seed_demo.py` is exempt, `:196`).
- **domain:** the feature slice or area emitting it: `connectors`, `auth`, `design_sync`,
  `blueprint`, `knowledge`, `scheduling`, `projects`, `templates`, ...
- **action_state:** `<verb/noun>_<state>` in snake_case. Common states: `started`, `completed`, `failed`,
  `error`, `skipped`, `rejected`, `timeout`. Pair `_started` with `_completed` / `_failed` around work that
  can fail. State-less facts are fine when the name reads as one (`auth.token_revoked`, `app/auth/dependencies.py:77`).
- **Context goes in kwargs, never in the event string:** `logger.info("x.y_started", connection_id=cid)`.

Examples (opened):
- `app/connectors/service.py:97` `connectors.resolve_credentials_started` and `:115`
  `connectors.resolve_credentials_completed`, both with `connection_id=`.
- `app/connectors/service.py:109-113` `connectors.credential_decryption_failed` logs
  `error_type=type(exc).__name__`: the exception type, not its message, which can carry secrets.
- `app/auth/dependencies.py:68` `auth.token_invalid` with `reason=` as a short machine-readable code.

Rules:
- Never log secrets, tokens, credentials or decrypted payloads. PII redaction runs as a processor by default
  (`app/core/logging.py:71-73`), a safety net, not a licence to log PII.
- `request_id` is added automatically from a context var (`app/core/logging.py:43`, `add_request_id`); do
  not pass it by hand.
- Log at the service layer (business events); repositories stay DB-only (`.claude/rules/backend.md`).

## Observed shape of existing names

`observed` (python regex counter over `logger.<level>("<name>"` call sites in `app/`, multiline-aware,
tests excluded, run 2026-09-27): 1296 sites, 844 two-part, 440 three-part (`domain.component.action_state`,
e.g. `blueprint.service.run_started` at `app/ai/blueprints/service.py:387`), 12 four-part.

- The rule is two-part. New events use `domain.action_state`.
- Existing three-part names on lines a diff does not touch are **not** a review finding.
- Whether three-part should become an allowed form is an open decision for the user; until then,
  do not rename existing events and do not add new three-part ones.
