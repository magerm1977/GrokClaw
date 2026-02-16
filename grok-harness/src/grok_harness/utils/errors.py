"""Custom exception hierarchy for Grok Harness."""


class GrokHarnessError(Exception):
    """Base exception for all Grok-Harness errors."""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ConfigError(GrokHarnessError):
    """Configuration-related errors."""

    pass


class GrokAPIError(GrokHarnessError):
    """Grok API interaction errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: str | None = None,
        details: dict | None = None,
    ):
        self.status_code = status_code
        self.response = response
        merged_details = details.copy() if details else {}
        if status_code is not None:
            merged_details["status_code"] = status_code
        if response is not None:
            merged_details["response"] = response[:200]  # Truncate long responses
        super().__init__(message, merged_details)


class AuthenticationError(GrokAPIError):
    """API key authentication failures."""

    pass


class RateLimitError(GrokAPIError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
    ):
        self.retry_after = retry_after
        details: dict = {}
        if retry_after is not None:
            details["retry_after"] = retry_after
        super().__init__(message, status_code=429, details=details)


class BudgetExceededError(GrokAPIError):
    """Budget limit reached."""

    pass


class BrowserError(GrokHarnessError):
    """Browser automation errors."""

    pass


class NavigationError(BrowserError):
    """Page navigation failures."""

    pass


class SecurityError(BrowserError):
    """Security-related browser issues (high-risk domains, etc.)."""

    pass


class MemorySystemError(GrokHarnessError):
    """Memory system errors (renamed to avoid shadowing built-in MemoryError)."""

    pass


class EmbeddingError(MemorySystemError):
    """Embedding generation failures."""

    pass


class SchedulerError(GrokHarnessError):
    """Scheduler-related errors."""

    pass


class LearningError(GrokHarnessError):
    """Pattern learning and analysis errors."""

    pass


class PredictiveError(GrokHarnessError):
    """Predictive analysis errors."""

    pass


class ConflictError(SchedulerError):
    """Task conflict errors."""

    pass


class OperationTimeoutError(GrokHarnessError):
    """Operation timeout (renamed to avoid shadowing built-in TimeoutError)."""

    pass


class ResourceError(GrokHarnessError):
    """Resource exhaustion (memory, disk, etc.)."""

    pass


class ValidationError(GrokHarnessError):
    """Input validation errors."""

    pass
