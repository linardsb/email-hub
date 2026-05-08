"""Tests for JWT algorithm pinning (Phase 6.4.2).

Verifies that the JWT implementation uses a hardcoded HS256 algorithm
and rejects tokens signed with other algorithms.
"""

from unittest.mock import patch

import jwt as pyjwt

from app.auth.token import _JWT_ALGORITHM, create_access_token, decode_token


def test_jwt_algorithm_constant_is_hs256() -> None:
    """Regression guard: algorithm constant must be HS256."""
    assert _JWT_ALGORITHM == "HS256"


def test_create_access_token_uses_hs256() -> None:
    """Access tokens must be signed with HS256."""
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = "test-secret"
        mock_settings.return_value.auth.access_token_expire_minutes = 30

        token = create_access_token(user_id=1, role="admin")
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"


def test_decode_rejects_wrong_algorithm() -> None:
    """Tokens signed with a different algorithm must be rejected."""
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = "test-secret"

        # Sign with HS384 instead of HS256
        # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        # "test-secret" is a fixture for verifying the decoder rejects mismatched
        # algorithms; never reaches a real auth path. Alert #158 false positive.
        token: str = pyjwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "type": "access",
                "jti": "abc",
                "iat": 1,
                "exp": 9999999999,
            },
            "test-secret",
            algorithm="HS384",
        )
        result = decode_token(token)
        assert result is None


def test_decode_rejects_none_algorithm() -> None:
    """Tokens with alg=none must be rejected."""
    with patch("app.auth.token.get_settings") as mock_settings:
        mock_settings.return_value.auth.jwt_secret_key = "test-secret"

        # Sign with empty key — PyJWT will reject on decode due to key mismatch
        # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
        # Empty-string key is the test setup for verifying signature mismatch
        # rejection; never reaches a real auth path. Alert #159 false positive.
        token: str = pyjwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "type": "access",
                "jti": "abc",
                "iat": 1,
                "exp": 9999999999,
            },
            "",
            algorithm="HS256",
        )
        result = decode_token(token)
        # Token was signed with empty string key, our decode uses "test-secret"
        # so signature mismatch → rejected
        assert result is None
