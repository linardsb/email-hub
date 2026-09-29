---
description: Rules for backend Python files
paths: app/**/*.py
---

# Backend Rules

- All functions MUST have complete type annotations
- Use `from app.core.logging import get_logger` for structured logging
- Log events: `domain.action_state` pattern (e.g., `items.create_completed`)
- Use AppError hierarchy from `app.core.exceptions` — never raise bare Exception
- Use nested config: `settings.database.url`, `settings.auth.jwt_secret_key`
- Repository layer: database operations ONLY (no business logic)
- Service layer: business logic, validation, logging
- Routes: thin — delegate to service, handle HTTP concerns only
