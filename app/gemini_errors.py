"""
Gemini API error handling module.

Provides utilities to catch and handle quota exhaustion, rate limiting, and other
Gemini API errors with graceful error messages and logging.
"""

import logging
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

# Type variable for decorator
F = TypeVar('F', bound=Callable[..., Any])


class GeminiQuotaExceededError(Exception):
    """Raised when Gemini API quota is exceeded."""

    def __init__(self, message: str = "Gemini API quota exceeded"):
        self.message = message
        super().__init__(message)


class GeminiRateLimitError(Exception):
    """Raised when Gemini API rate limit is exceeded."""

    def __init__(self, message: str = "Gemini API rate limit exceeded"):
        self.message = message
        super().__init__(message)


class GeminiAPIError(Exception):
    """Generic Gemini API error."""

    def __init__(self, message: str = "Gemini API error"):
        self.message = message
        super().__init__(message)


def handle_gemini_errors(func: F) -> F:
    """Decorator to catch and handle Gemini API errors.

    Catches common Google API exceptions and translates them to more specific
    errors (quota exceeded, rate limit, etc.).

    Args:
        func: Function to wrap.

    Returns:
        Wrapped function that handles Gemini errors.

    Raises:
        GeminiQuotaExceededError: If quota is exceeded.
        GeminiRateLimitError: If rate limit is hit.
        GeminiAPIError: For other API errors.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__

            logger.error(
                "Gemini API error in %s: %s (%s)",
                func.__name__,
                str(e)[:200],
                error_type,
            )

            # Check for quota exhaustion
            if any(keyword in error_str for keyword in [
                'quota',
                'exhausted',
                'resource_exhausted',
                'out of quota'
            ]):
                raise GeminiQuotaExceededError(
                    "Gemini API quota exceeded. Please check your API key or contact support."
                ) from e

            # Check for rate limiting
            if any(keyword in error_str for keyword in [
                'rate limit',
                'too many requests',
                '429',
                'deadline exceeded'
            ]):
                raise GeminiRateLimitError(
                    "Gemini API rate limit exceeded. Please try again later."
                ) from e

            # Generic API error
            raise GeminiAPIError(
                f"Gemini API error: {str(e)[:100]}"
            ) from e

    return wrapper  # type: ignore
