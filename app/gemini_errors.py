"""
Gemini API error handling module.

Provides utilities to catch and handle quota exhaustion, rate limiting, and other
Gemini API errors with graceful error messages, logging, and automatic retry logic.
"""

import logging
import time
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


class GeminiTruncationError(Exception):
    """Raised when Gemini truncates its response mid-JSON due to max_output_tokens.

    This error is DETERMINISTIC — retrying the exact same input will produce
    the same truncation. The caller must reduce the input size before retrying.
    Never retry this with the same chunk.
    """

    def __init__(self, message: str = "Gemini truncated response (MAX_TOKENS)"):
        self.message = message
        super().__init__(message)


class GeminiAPIError(Exception):
    """Generic Gemini API error."""

    def __init__(self, message: str = "Gemini API error"):
        self.message = message
        super().__init__(message)


def _classify_gemini_error(e: Exception) -> tuple[type, str]:
    """Classify Gemini error and return (error_class, message)."""
    error_str = str(e).lower()

    if any(kw in error_str for kw in ('quota', 'exhausted', 'resource_exhausted', 'out of quota')):
        return GeminiQuotaExceededError, "Gemini API quota exceeded. Please check your API key or contact support."

    # Check for rate limiting: 429, 503, "rate limit", "too many requests", "high demand", "unavailable"
    if any(kw in error_str for kw in ('rate limit', 'too many requests', '429', 'deadline exceeded', '503', 'high demand', 'unavailable')):
        return GeminiRateLimitError, "Gemini API rate limit exceeded. Please try again later."

    return GeminiAPIError, f"Gemini API error: {str(e)[:100]}"


def handle_gemini_errors(max_retries: int = 3, backoff_factor: float = 2.0) -> Callable:
    """
    Decorator to catch, classify, and retry Gemini API errors with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Exponential backoff multiplier (default: 2.0)
    """
    def decorator(func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except GeminiTruncationError:
                    raise  # deterministic — retrying same input is pointless
                except Exception as e:
                    last_exception = e
                    error_class, error_msg = _classify_gemini_error(e)
                    error_type = type(e).__name__

                    logger.error(
                        "Gemini API error in %s (attempt %d/%d): %s (%s)",
                        func.__name__,
                        attempt + 1,
                        max_retries,
                        str(e)[:100],
                        error_type,
                    )

                    # Don't retry quota errors — they're permanent until quota is renewed
                    if error_class == GeminiQuotaExceededError:
                        raise error_class(error_msg) from e

                    # For rate limit errors, retry with backoff
                    if error_class == GeminiRateLimitError:
                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * backoff_factor
                            logger.warning(
                                "Rate limit hit. Retrying in %.1f seconds... (attempt %d/%d)",
                                wait_time,
                                attempt + 1,
                                max_retries,
                            )
                            time.sleep(wait_time)
                            continue
                        else:
                            raise error_class(error_msg) from e

                    # For other generic errors, retry once with short backoff
                    if attempt < max_retries - 1:
                        wait_time = 1.0 * (attempt + 1)
                        logger.warning(
                            "Transient error. Retrying in %.1f seconds... (attempt %d/%d)",
                            wait_time,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise error_class(error_msg) from e

            # Fallback (shouldn't reach here)
            if last_exception:
                error_class, error_msg = _classify_gemini_error(last_exception)
                raise error_class(error_msg) from last_exception

        return wrapper  # type: ignore

    return decorator
