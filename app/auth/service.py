"""Authentication business logic."""

import datetime
import hashlib
import secrets

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import invalidate_user_cache
from app.auth.exceptions import AccountLockedError, InvalidCredentialsError
from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.schemas import (
    CreateUserRequest,
    LoginResponse,
    UpdateUserRequest,
    UserDetailResponse,
)
from app.auth.token import create_access_token, create_refresh_token
from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger
from app.shared.models import utcnow
from app.shared.schemas import PaginatedResponse

logger = get_logger(__name__)

# Brute-force protection constants
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = datetime.timedelta(minutes=15)

# F030 third-factor: hosts treated as loopback for /bootstrap. TestClient's
# "testclient" is intentionally excluded so non-loopback paths are exercised.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})

# Pre-computed dummy hash for timing normalization (email enumeration prevention)
_DUMMY_HASH = bcrypt.hashpw(b"timing-normalization-dummy", bcrypt.gensalt()).decode("utf-8")


def _email_key(email: str) -> str:
    """Hash email for use in Redis keys to avoid leaking PII at-rest."""
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]


async def _check_redis_brute_force(email: str) -> bool:
    """Check Redis for brute force lockout. Returns True if locked out."""
    try:
        from app.core.redis import get_redis

        redis_client = await get_redis()
        key = f"auth:lockout:{_email_key(email)}"
        locked = await redis_client.get(key)
        return locked is not None
    except Exception:
        logger.warning("auth.redis_lockout_check_unavailable", email=email)
        return False


async def _record_failed_attempt_redis(email: str) -> None:
    """Record a failed login attempt in Redis with TTL."""
    try:
        from app.core.redis import get_redis

        redis_client = await get_redis()
        email_hash = _email_key(email)
        key = f"auth:failures:{email_hash}"
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, int(LOCKOUT_DURATION.total_seconds()))
        result = await pipe.execute()
        count = int(result[0]) if result else 0
        if count >= MAX_FAILED_ATTEMPTS:
            lockout_key = f"auth:lockout:{email_hash}"
            await redis_client.setex(lockout_key, int(LOCKOUT_DURATION.total_seconds()), "locked")
    except Exception:
        logger.warning("auth.redis_brute_force_unavailable", email=email, exc_info=True)


async def _clear_redis_brute_force(email: str) -> None:
    """Clear Redis brute force keys on successful login."""
    try:
        from app.core.redis import get_redis

        redis_client = await get_redis()
        email_hash = _email_key(email)
        await redis_client.delete(
            f"auth:failures:{email_hash}",
            f"auth:lockout:{email_hash}",
        )
    except Exception:
        logger.warning("auth.redis_clear_unavailable", email=email, exc_info=True)


class AuthService:
    """Handles authentication logic with bcrypt password verification."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = UserRepository(db)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password with bcrypt."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against its bcrypt hash."""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    async def authenticate(self, email: str, password: str) -> LoginResponse:
        """Authenticate a user by email and password.

        Raises:
            InvalidCredentialsError: If credentials are invalid.
            AccountLockedError: If the account is locked.
        """
        # Redis fast-path lockout check (before DB query)
        if await _check_redis_brute_force(email):
            logger.warning("auth.login_locked_redis", email=email)
            raise AccountLockedError("Account is temporarily locked")

        user = await self.repo.find_by_email(email)
        if not user or not user.is_active:
            # Timing normalization: always run bcrypt to prevent email enumeration
            self.verify_password(password, _DUMMY_HASH)
            logger.warning("auth.login_failed", email=email, reason="user_not_found")
            raise InvalidCredentialsError("Invalid email or password")

        # Check lockout
        if user.locked_until and utcnow() < user.locked_until:
            logger.warning("auth.login_locked", email=email)
            raise AccountLockedError("Account is temporarily locked")

        # Clear expired lockout (both DB and Redis)
        if user.locked_until and utcnow() >= user.locked_until:
            user.locked_until = None
            user.failed_attempts = 0
            await _clear_redis_brute_force(email)

        # Verify password
        if not self.verify_password(password, user.hashed_password):
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = utcnow() + LOCKOUT_DURATION
                logger.warning("auth.account_locked", email=email, attempts=user.failed_attempts)
            await self.repo.update(user)
            await _record_failed_attempt_redis(email)
            logger.warning("auth.login_failed", email=email, reason="bad_password")
            raise InvalidCredentialsError("Invalid email or password")

        # Success — clear failed attempts
        if user.failed_attempts > 0:
            user.failed_attempts = 0
            user.locked_until = None
            await self.repo.update(user)
        await _clear_redis_brute_force(email)

        # Issue JWT tokens
        access_token = create_access_token(user.id, user.role)
        refresh_token = create_refresh_token(user.id)

        logger.info("auth.token_issued", email=email, role=user.role)
        return LoginResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_access_token(self, user_id: int) -> str:
        """Issue a new access token for a valid user.

        Args:
            user_id: The user ID from the refresh token.

        Returns:
            New access token string.

        Raises:
            InvalidCredentialsError: If user not found or inactive.
        """
        user = await self.repo.find_by_id(user_id)
        if not user or not user.is_active:
            raise InvalidCredentialsError("User not found or inactive")

        # Check lockout status — locked users must not refresh tokens
        if user.locked_until and utcnow() < user.locked_until:
            logger.warning("auth.refresh_locked", user_id=user_id)
            raise AccountLockedError("Account is temporarily locked")

        access_token = create_access_token(user.id, user.role)
        logger.info("auth.token_refreshed", user_id=user.id)
        return access_token

    async def reset_password(self, user_id: int, new_password: str) -> None:
        """Reset a user's password (admin action).

        Args:
            user_id: Target user's database ID.
            new_password: The new password (already validated by schema).

        Raises:
            InvalidCredentialsError: If user not found.
        """
        user = await self.repo.find_by_id(user_id)
        if not user:
            raise InvalidCredentialsError("User not found")

        user.hashed_password = self.hash_password(new_password)
        user.failed_attempts = 0
        user.locked_until = None
        await self.repo.update(user)

        # Invalidate auth cache so next request fetches fresh user
        invalidate_user_cache(user_id)

        # Clear Redis brute force state for this user
        await _clear_redis_brute_force(user.email)

        logger.info("auth.password_reset", user_id=user_id)

    async def delete_user_data(self, user_id: int, requesting_user_id: int) -> bool:
        """Delete all user data for GDPR right-to-erasure compliance.

        Deletes the user record (cascading to related data).
        Clears any Redis brute-force tracking keys.

        Args:
            user_id: The ID of the user to delete.
            requesting_user_id: The ID of the admin requesting deletion.

        Returns:
            True if user was found and deleted, False if not found.

        Raises:
            DomainValidationError: If attempting to delete own account.
        """
        from app.core.exceptions import DomainValidationError

        if user_id == requesting_user_id:
            raise DomainValidationError("Cannot delete your own account")

        # Look up user for email (Redis cleanup) and deletion
        user = await self.repo.find_by_id(user_id)
        if user is None:
            return False

        email = user.email

        # Delete user record from database (reuse fetched object)
        await self.repo.delete(user)

        # Invalidate auth cache for deleted user
        invalidate_user_cache(user_id)

        # Clear any Redis brute-force keys for this user
        await _clear_redis_brute_force(email)

        logger.warning(
            "auth.user_data_deleted",
            deleted_user_id=user_id,
            requesting_user_id=requesting_user_id,
        )
        return True

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResponse[UserDetailResponse]:
        """List users with pagination and optional filters (admin only)."""
        offset = (page - 1) * page_size
        users = await self.repo.list(
            offset=offset,
            limit=page_size,
            search=search,
            role=role,
            is_active=is_active,
        )
        total = await self.repo.count_filtered(
            search=search,
            role=role,
            is_active=is_active,
        )
        return PaginatedResponse(
            items=[UserDetailResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_user(self, user_id: int) -> UserDetailResponse:
        """Get a single user by ID (admin only)."""
        user = await self.repo.find_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")
        return UserDetailResponse.model_validate(user)

    async def create_user(self, data: CreateUserRequest) -> UserDetailResponse:
        """Create a new user (admin only)."""
        from app.core.exceptions import DomainValidationError

        existing = await self.repo.find_by_email(data.email)
        if existing is not None:
            raise DomainValidationError("Email already in use")

        user = User(
            email=data.email,
            name=data.name,
            hashed_password=self.hash_password(data.password),
            role=data.role,
        )
        user = await self.repo.create(user)
        logger.info("auth.user_created", user_id=user.id, role=data.role)
        return UserDetailResponse.model_validate(user)

    async def update_user(self, user_id: int, data: UpdateUserRequest) -> UserDetailResponse:
        """Update a user's profile (admin only)."""
        from app.core.exceptions import DomainValidationError

        user = await self.repo.find_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")

        # Check email uniqueness if changing email
        if data.email is not None and data.email != user.email:
            existing = await self.repo.find_by_email(data.email)
            if existing is not None:
                raise DomainValidationError("Email already in use")

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)

        user = await self.repo.update(user)

        # Invalidate auth cache so next request gets updated user data
        invalidate_user_cache(user_id)

        logger.info("auth.user_updated", user_id=user_id)
        return UserDetailResponse.model_validate(user)

    async def bootstrap_demo(
        self,
        *,
        client_host: str | None,
        provided_secret: str | None,
    ) -> LoginResponse:
        """Bootstrap the first admin user and return a login response.

        Only works in development environment when zero users exist AND the
        request originates from loopback OR carries a valid bootstrap secret
        (F030 third-factor hardening).

        Returns:
            LoginResponse with JWT tokens for the created admin.

        Raises:
            InvalidCredentialsError: If environment is not development or users already exist.
            ForbiddenError: If the request is not from loopback and no valid bootstrap secret was supplied.
        """
        from app.core.config import get_settings

        settings = get_settings()
        if settings.environment != "development":
            raise InvalidCredentialsError("Bootstrap only available in development")

        count = await self.repo.count()
        if count > 0:
            raise InvalidCredentialsError("Users already exist — use /login instead")

        loopback_ok = client_host in _LOOPBACK_HOSTS
        configured_secret = settings.auth.bootstrap_secret.get_secret_value()
        secret_ok = (
            bool(configured_secret)
            and provided_secret is not None
            and secrets.compare_digest(configured_secret, provided_secret)
        )
        if not (loopback_ok or secret_ok):
            logger.warning(
                "auth.bootstrap_denied",
                reason="third_factor_failed",
                client_host=client_host,
                loopback_ok=loopback_ok,
                secret_provided=provided_secret is not None,
            )
            raise ForbiddenError("Bootstrap requires loopback origin or a valid bootstrap secret")

        password = settings.auth.demo_user_password
        user = User(
            email="admin@email-hub.dev",
            hashed_password=self.hash_password(password),
            name="Admin",
            role="admin",
        )
        user = await self.repo.create(user)
        logger.info("auth.bootstrap_completed", user_id=user.id)

        access_token = create_access_token(user.id, user.role)
        refresh_token = create_refresh_token(user.id)
        return LoginResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def seed_demo_users(self) -> list[User]:
        """Create demo users if no users exist. Returns created users.

        Only seeds in development environment. Uses configurable password
        from AUTH__DEMO_USER_PASSWORD env var (defaults to 'admin').
        """
        from app.core.config import get_settings

        settings = get_settings()
        if settings.environment != "development":
            logger.info("auth.demo_seed_skipped", environment=settings.environment)
            return []

        count = await self.repo.count()
        if count > 0:
            return []

        password = settings.auth.demo_user_password
        demo_users = [
            (settings.auth.demo_user_email, password, "Demo Admin", "admin"),
        ]

        created: list[User] = []
        for email, pwd, name, role in demo_users:
            user = User(
                email=email,
                hashed_password=self.hash_password(pwd),
                name=name,
                role=role,
            )
            user = await self.repo.create(user)
            created.append(user)

        logger.info("auth.demo_users_seeded", count=len(created))
        return created
