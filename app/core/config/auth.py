"""Authentication and JWT settings."""

from pydantic import BaseModel, Field, SecretStr


class AuthConfig(BaseModel):
    """Authentication and JWT settings."""

    jwt_secret_key: str = Field(
        default="CHANGE-ME-IN-PRODUCTION-this-is-not-a-real-secret",  # 49 chars; passes min_length, trips prod sentinel
        min_length=32,
        description="HS256 signing key; must be >=32 chars (256 bits). Production refuses the default placeholder.",
    )
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    demo_user_email: str = "demo@example.com"
    demo_user_password: str = "admin"  # noqa: S105
    bootstrap_secret: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Optional shared secret required by /api/v1/auth/bootstrap when the request "
            "is not from a loopback address. Empty disables non-loopback bootstrapping. "
            "Combined with ENVIRONMENT=development + zero-users gates as a third "
            "independent factor (F030)."
        ),
    )
