"""Tolgee-specific error types."""

from __future__ import annotations

from app.core.exceptions import AppError, DomainValidationError, ServiceUnavailableError


class TolgeeConnectionError(AppError):
    """Failed to connect to Tolgee instance."""


class TolgeeAuthenticationError(DomainValidationError):
    """Invalid Tolgee PAT or insufficient permissions."""


class TolgeeBaseUrlNotAllowedError(DomainValidationError):
    """Requested Tolgee base URL is not in the configured allowlist."""


class TolgeeInvalidProjectIdError(DomainValidationError):
    """Tolgee project id is not a non-negative integer."""


class TolgeeSyncError(AppError):
    """Failed to sync keys or pull translations."""


class TolgeeServiceUnavailableError(ServiceUnavailableError):
    """Tolgee instance not reachable."""


class LocaleBuildError(AppError):
    """Failed to build locale-specific email."""


class GmailClippingWarning(DomainValidationError):
    """Translated content exceeds Gmail clipping threshold (~102KB)."""
