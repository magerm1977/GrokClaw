"""Unit tests for error hierarchy."""

import pytest

from grok_harness.utils.errors import (
    GrokHarnessError,
    GrokAPIError,
    AuthenticationError,
    RateLimitError,
    BrowserError,
    NavigationError,
)


def test_error_hierarchy() -> None:
    """Test that errors inherit correctly."""
    assert issubclass(GrokAPIError, GrokHarnessError)
    assert issubclass(AuthenticationError, GrokAPIError)
    assert issubclass(RateLimitError, GrokAPIError)
    assert issubclass(BrowserError, GrokHarnessError)
    assert issubclass(NavigationError, BrowserError)


def test_error_with_details() -> None:
    """Test error with additional details."""
    error = GrokAPIError("API failed", status_code=500, response="Server error")
    assert error.status_code == 500
    assert error.response == "Server error"
    assert error.details["status_code"] == 500
    assert error.details["response"] == "Server error"


def test_rate_limit_error() -> None:
    """Test rate limit error with retry."""
    error = RateLimitError("Too many requests", retry_after=60)
    assert error.retry_after == 60
    assert error.status_code == 429
    assert error.details["retry_after"] == 60


def test_error_str_representation() -> None:
    """Test string representation."""
    error = GrokHarnessError("Something went wrong")
    assert str(error) == "Something went wrong"
    assert "GrokHarnessError" in repr(error)
