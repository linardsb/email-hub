"""Error message sanitization for HTTP responses.

Maps internal exception types to safe, client-facing messages.
Internal details are logged server-side but never returned to clients.
"""

from app.core.logging import get_logger

logger = get_logger(__name__)

# Maps exception class names to safe client-facing messages.
# Any exception not in this map gets the generic 500 message.
_SAFE_MESSAGES: dict[str, str] = {
    # Core errors — mapped by AppError subclass
    "NotFoundError": "Resource not found",
    "DomainValidationError": "Validation error",
    "ForbiddenError": "Access denied",
    "ConflictError": "Resource conflict",
    "ServiceUnavailableError": "Service temporarily unavailable",
    "ToolCapExceededError": "Agent tool-call limit exceeded",
    # Auth errors
    "InvalidCredentialsError": "Invalid email or password",
    "AccountLockedError": "Account is temporarily locked",
    # Email engine
    "BuildFailedError": "Email build failed",
    "BuildServiceUnavailableError": "Build service temporarily unavailable",
    # Connectors
    "ExportFailedError": "Export operation failed",
    "UnsupportedConnectorError": "Unsupported connector type",
    # AI errors
    "AIError": "AI service error",
    "AIConfigurationError": "AI service configuration error",
    "AIExecutionError": "AI request failed",
    # Blueprint errors
    "BlueprintError": "Blueprint execution failed",
    "BlueprintNodeError": "Blueprint step failed",
    "BlueprintEscalatedError": "Blueprint requires manual intervention",
    # Project access
    "ProjectAccessDeniedError": "Access denied",
    # Rendering
    "RenderingSubmitError": "Rendering test submission failed",
    "RenderingTestNotFoundError": "Rendering test not found",
    "RenderingProviderError": "Rendering provider error",
    # QA
    "QAOverrideNotFoundError": "QA result not found",
    # Knowledge
    "DuplicateTagError": "Tag already exists",
    # Import annotator
    "ImportAnnotationError": "Failed to annotate imported HTML",
    # Voice pipeline
    "VoiceError": "Voice processing failed",
    "VoiceDisabledError": "Voice input is not enabled",
    "AudioValidationError": "Invalid audio file",
    "TranscriptionError": "Audio transcription failed",
    "BriefExtractionError": "Brief extraction failed",
}

# Error types where the original message is safe to return
# (validation errors where the message IS the user-facing feedback)
_PASSTHROUGH_TYPES: set[str] = {
    "DomainValidationError",
    "UnsupportedConnectorError",
    "RenderingProviderError",
    "DuplicateTagError",
    "ImportAnnotationError",
    "SyncFailedError",
    "UnsupportedProviderError",
}


def get_safe_error_message(exc: Exception) -> str:
    """Get a sanitized, client-safe error message for an exception.

    Internal details are logged but never returned to the client.
    For validation-type errors where the message is user feedback,
    the original message is preserved.

    Args:
        exc: The exception to sanitize.

    Returns:
        A safe error message string.
    """
    # Check MRO for passthrough types (allows subclass matching)
    for cls in type(exc).__mro__:
        if cls.__name__ in _PASSTHROUGH_TYPES:
            return str(exc)

    # Look up safe message by class name, walking MRO for inheritance
    for cls in type(exc).__mro__:
        if cls.__name__ in _SAFE_MESSAGES:
            return _SAFE_MESSAGES[cls.__name__]

    # Fallback — generic message, log the unmapped type
    logger.warning(
        "error_sanitizer.unmapped_exception",
        exception_type=type(exc).__name__,
    )
    return "An unexpected error occurred"


def get_safe_error_type(exc: Exception) -> str:
    """Get a sanitized error type for the response.

    Returns a generic category instead of the internal class name.

    Args:
        exc: The exception to categorize.

    Returns:
        A safe error type string.
    """
    from app.core.exceptions import (
        ConflictError,
        DomainValidationError,
        ForbiddenError,
        NotFoundError,
        ServiceUnavailableError,
    )

    if isinstance(exc, NotFoundError):
        return "not_found"
    if isinstance(exc, DomainValidationError):
        return "validation_error"
    if isinstance(exc, ForbiddenError):
        return "forbidden"
    if isinstance(exc, ConflictError):
        return "conflict"
    if isinstance(exc, ServiceUnavailableError):
        return "service_unavailable"

    # Auth errors — check by class name to avoid circular imports
    exc_name = type(exc).__name__
    if exc_name == "InvalidCredentialsError":
        return "authentication_error"
    if exc_name == "AccountLockedError":
        return "account_locked"

    # AI errors — check by module to avoid circular imports
    exc_module = type(exc).__module__ or ""
    if "ai" in exc_module or "blueprint" in exc_module:
        return "ai_error"

    return "server_error"
