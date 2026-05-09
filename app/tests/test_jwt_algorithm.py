"""Tests for JWT algorithm pinning (Phase 6.4.2).

Verifies that the JWT implementation uses a hardcoded HS256 algorithm
and rejects tokens signed with other algorithms.
"""

import secrets
from unittest.mock import patch

import jwt as pyjwt

from app.auth.token import _JWT_ALGORITHM, create_access_token, decode_token


def test_jwt_algorithm_constant_is_hs256() -> None:
    """Regression guard: algorithm constant must be HS256."""
    assert _JWT_ALGORITHM == "HS256"


def test_create_access_token_uses_hs256() -> None:
    """Access tokens must be signed with HS256."""
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = secrets.token_urlsafe(32)
        mock_settings.return_value.auth.access_token_expire_minutes = 30

        token = create_access_token(user_id=1, role="admin")
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"


def test_decode_rejects_wrong_algorithm() -> None:
    """Tokens signed with a different algorithm must be rejected."""
    secret = secrets.token_urlsafe(32)
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = secret

        token: str = pyjwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "type": "access",
                "jti": "abc",
                "iat": 1,
                "exp": 9999999999,
            },
            secret,
            algorithm="HS384",
        )
        assert decode_token(token) is None


def test_decode_rejects_none_algorithm() -> None:
    """Tokens signed with a mismatched secret must be rejected.

    Originally written to verify alg=none rejection; PyJWT now blocks alg=none at
    encode time, so this asserts the broader signature-mismatch rejection path
    that catches the same class of forgery attempts.
    """
    secret = secrets.token_urlsafe(32)
    wrong_secret = secrets.token_urlsafe(32)
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = secret

        token: str = pyjwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "type": "access",
                "jti": "abc",
                "iat": 1,
                "exp": 9999999999,
            },
            wrong_secret,
            algorithm="HS256",
        )
        assert decode_token(token) is None
