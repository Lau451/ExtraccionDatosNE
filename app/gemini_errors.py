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
    """Decorator to catch and handle Gemini API errors."""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__

            logger.error(
                "Gemini API error in %s: %s (%s)",
                func.__name__,
                str(e),
                error_type,
            )

            if any(kw in error_str for kw in ('quota', 'exhausted', 'resource_exhausted', 'out of quota')):
                raise GeminiQuotaExceededError(
                    "Gemini API quota exceeded. Please check your API key or contact support."
                ) from e

            if any(kw in error_str for kw in ('rate limit', 'too many requests', '429', 'deadline exceeded')):
                raise GeminiRateLimitError(
                    "Gemini API rate limit exceeded. Please try again later."
                ) from e

            raise GeminiAPIError(f"Gemini API error: {str(e)[:100]}") from e

    return wrapper  # type: ignore
