---
description: Rules for test files
paths:
  - "**/test_*.py"
  - "**/tests/**/*.py"
---

# Testing Rules

- Use `@pytest.mark.integration` for tests requiring real database
- Use AsyncMock for database sessions in unit tests
- Use factory functions (make_item, make_user) for test data
- Save/restore `app.dependency_overrides` in fixtures
- Clear auth cache between tests (`clear_user_cache()`)
- Disable rate limiter in route tests (`limiter.enabled = False`)
