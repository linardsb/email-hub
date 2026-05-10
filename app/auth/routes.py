# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""REST API routes for authentication."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.requests import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role, security
from app.auth.models import User
from app.auth.schemas import (
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    RefreshRequest,
    RefreshResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.auth.token import decode_token, revoke_token
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.shared.schemas import PaginatedResponse

logger = get_logger(__name__)


def _refresh_ttl_seconds() -> int:
    """Compute refresh-token revocation TTL from auth config."""
    return get_settings().auth.refresh_token_expire_days * 86400


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:  # tenant-exempt: pre-auth (login/refresh/bootstrap have no user yet); /users/* admin endpoints use require_role("admin")
    """Dependency to create AuthService with request-scoped session."""
    return AuthService(db)


@router.post("/bootstrap", response_model=LoginResponse)
@limiter.limit("5/minute")
async def bootstrap(
    request: Request,
    service: AuthService = Depends(get_service),
) -> LoginResponse:
    """Bootstrap first admin user (dev + zero-users + loopback-or-secret).

    Creates the initial admin account and returns JWT tokens. All three of
    the following must hold (F030):
      1. ENVIRONMENT=development
      2. No users exist yet
      3. Request originates from 127.0.0.1/::1 OR carries a valid
         X-Bootstrap-Secret header matching AUTH__BOOTSTRAP_SECRET.
    """
    client_host = request.client.host if request.client else None
    provided_secret = request.headers.get("x-bootstrap-secret")
    return await service.bootstrap_demo(
        client_host=client_host,
        provided_secret=provided_secret,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    service: AuthService = Depends(get_service),
) -> LoginResponse:
    """Authenticate user with email and password. Returns JWT tokens."""
    _ = request
    return await service.authenticate(body.email, body.password)


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    service: AuthService = Depends(get_service),
) -> RefreshResponse:
    """Exchange a valid refresh token for a new access token."""
    _ = request
    logger.info("auth.token.refresh_started")
    payload = decode_token(body.refresh_token)
    if payload is None or payload.type != "refresh":
        logger.warning("auth.token.refresh_failed", reason="invalid_refresh_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token = await service.refresh_access_token(payload.sub)
    # Revoke the used refresh token to prevent replay attacks
    await revoke_token(payload.jti, ttl_seconds=_refresh_ttl_seconds())
    logger.info("auth.token.refresh_completed", user_id=payload.sub)
    return RefreshResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """Revoke the current access token, effectively logging out."""
    _ = request
    logger.info("auth.logout_started", user_id=current_user.id)
    # get_current_user already validated the token; decode again to extract JTI for revocation
    if credentials is not None:
        payload = decode_token(credentials.credentials)
        if payload is not None:
            await revoke_token(payload.jti)
    logger.info("auth.logout_completed", user_id=current_user.id)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: PasswordResetRequest,
    service: AuthService = Depends(get_service),
    _current_user: User = Depends(require_role("admin")),
) -> None:
    """Reset a user's password (admin only)."""
    _ = request
    await service.reset_password(body.user_id, body.new_password)


@router.post("/seed", response_model=list[UserResponse])
@limiter.limit("5/minute")
async def seed_demo_users(
    request: Request,
    _current_user: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> list[UserResponse]:
    """Seed demo users (development only, admin-only, no-op if users exist)."""
    _ = request
    settings = get_settings()
    if settings.environment != "development":
        logger.info("auth.seed.skipped", environment=settings.environment)
        return []
    users = await service.seed_demo_users()
    return [UserResponse.model_validate(u) for u in users]


@router.get("/users", response_model=PaginatedResponse[UserDetailResponse])
@limiter.limit("30/minute")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    _admin: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> PaginatedResponse[UserDetailResponse]:
    """List all users with pagination and filters (admin only)."""
    _ = request
    return await service.list_users(
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@router.get("/users/{user_id}", response_model=UserDetailResponse)
@limiter.limit("30/minute")
async def get_user(
    request: Request,
    user_id: int,
    _admin: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> UserDetailResponse:
    """Get a single user by ID (admin only)."""
    _ = request
    return await service.get_user(user_id)


@router.post("/users", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_user(
    request: Request,
    body: CreateUserRequest,
    _admin: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> UserDetailResponse:
    """Create a new user (admin only)."""
    _ = request
    return await service.create_user(body)


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
@limiter.limit("10/minute")
async def update_user(
    request: Request,
    user_id: int,
    body: UpdateUserRequest,
    _admin: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> UserDetailResponse:
    """Update a user's profile (admin only)."""
    _ = request
    return await service.update_user(user_id, body)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("5/minute")
async def delete_user_data(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    service: AuthService = Depends(get_service),
) -> None:
    """Delete user data for GDPR right-to-erasure compliance.

    Admin-only. Permanently removes user record and clears associated
    Redis tracking data. Cannot delete own account.
    """
    _ = request
    deleted = await service.delete_user_data(user_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
