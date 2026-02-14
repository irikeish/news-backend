"""Custom exceptions and HTTP mapping for News API."""

from typing import Sequence


class NewsAppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, details: Sequence[str] | None = None):
        super().__init__(message)
        self.details = list(details) if details else None


class LLMUnavailableError(NewsAppError):
    """Raised when LLM API fails."""

    pass


class DatabaseUnavailableError(NewsAppError):
    """Raised when MongoDB connection or query fails."""

    pass


class ValidationError(NewsAppError):
    """Raised when request parameters are invalid (e.g. missing lat/lon for nearby)."""

    pass


class NoArticlesFoundError(NewsAppError):
    """Raised when no articles match the query."""

    pass


EXCEPTION_TO_STATUS: dict[type, int] = {
    ValidationError: 400,
    NoArticlesFoundError: 404,
    LLMUnavailableError: 503,
    DatabaseUnavailableError: 503,
}

EXCEPTION_TO_CODE: dict[type, str] = {
    ValidationError: "VALIDATION_ERROR",
    NoArticlesFoundError: "NO_ARTICLES",
    LLMUnavailableError: "LLM_UNAVAILABLE",
    DatabaseUnavailableError: "DB_UNAVAILABLE",
}
