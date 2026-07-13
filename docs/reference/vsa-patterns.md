# Vertical Slice Architecture (VSA) Patterns

## Feature Structure

Every feature follows this file structure:

```
app/{feature}/
├── __init__.py         # Module docstring
├── models.py           # SQLAlchemy models (Base + TimestampMixin)
├── schemas.py          # Pydantic request/response schemas
├── repository.py       # Database operations (CRUD + search + pagination)
├── service.py          # Business logic + structured logging
├── exceptions.py       # Feature-specific exceptions (inherit AppError)
├── routes.py           # FastAPI endpoints (thin, delegates to service)
└── tests/
    ├── __init__.py
    ├── conftest.py     # Factory functions + fixtures
    ├── test_service.py # Unit tests for business logic
    └── test_routes.py  # API endpoint tests
```

## Layer Responsibilities

### Models (models.py)
- Inherit from `Base` and `TimestampMixin`
- Define table structure only — no business logic
- Use `Mapped[T]` type annotations

### Schemas (schemas.py)
- `{Feature}Create` — fields for creation (required fields)
- `{Feature}Update` — all optional fields for partial updates
- `{Feature}Response` — output format with `model_config = {"from_attributes": True}`

### Repository (repository.py)
- Database operations ONLY
- Accepts `AsyncSession` in constructor
- Methods: `get()`, `list()`, `count()`, `create()`, `update()`, `delete()`
- Use `escape_like()` for safe LIKE patterns

### Service (service.py)
- Business logic, validation, orchestration
- Creates Repository internally
- Structured logging for all operations
- Returns Pydantic response schemas

### Exceptions (exceptions.py)
- Inherit from `AppError` hierarchy for automatic HTTP status mapping
- `NotFoundError` → 404
- `DomainValidationError` → 422
- `ConflictError` → 409

### Routes (routes.py)
- Thin layer — delegates to service
- Handles HTTP concerns (status codes, dependencies)
- Rate limiting on all endpoints
- Auth via `get_current_user` or `require_role(...)`

## Adding a New Feature

1. Create the directory: `mkdir -p app/{feature}/tests`
2. Create files in order: schemas → models → repository → service → exceptions → routes → tests
3. Register the router in `app/main.py`
4. Import models in `alembic/env.py`
5. Create migration: `make db-revision m="add {feature} table"`
6. Run migration: `make db-migrate`
7. Verify: `make check`
