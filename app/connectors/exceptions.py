"""Feature-specific exceptions for connectors."""

from app.core.exceptions import AppError, ConflictError, DomainValidationError, NotFoundError


class ExportFailedError(AppError):
    """Raised when an export operation fails."""


class UnsupportedConnectorError(DomainValidationError):
    """Raised when an unsupported connector type is requested."""


class ESPConnectionNotFoundError(NotFoundError):
    """Raised when an ESP connection is not found."""


class ESPSyncFailedError(AppError):
    """Raised when an ESP sync operation fails."""


class InvalidESPCredentialsError(DomainValidationError):
    """Raised when ESP credentials are invalid."""


class InvalidRemoteTemplateIdError(DomainValidationError):
    """Raised when a remote ESP template ID is not a safe URL path segment."""


class ESPConflictError(ConflictError):
    """Raised when an ESP returns 409 for a duplicate resource."""


class ExportQAGateBlockedError(DomainValidationError):
    """Raised when QA gate blocks export in enforce mode."""


class ApprovalRequiredError(DomainValidationError):
    """Raised when approval is required but not yet granted."""
