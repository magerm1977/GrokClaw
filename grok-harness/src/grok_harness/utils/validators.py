"""Risk classification and validation utilities."""

import asyncio
from enum import Enum
from typing import Any, Dict, Optional

# Import TaskStep only for type hint to avoid circular imports
try:
    from ..core.types import TaskStep
except ImportError:
    TaskStep = Any  # type: ignore


class RiskLevel(str, Enum):
    """Risk level for orchestrator steps."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Actions by risk level
_LOW_RISK_ACTIONS = frozenset({
    "navigate",
    "click",
    "type",
    "select",
    "scroll",
    "extract",
    "wait",
    "done",
    "fail",
    "memory_search",
    "memory_store",
    "schedule_add",
})

_MEDIUM_RISK_ACTIONS = frozenset({
    "browser_submit",
    "form_submit",
    "submit",
})

_HIGH_RISK_ACTIONS = frozenset({
    "run_code",
    "shell",
    "exec",
    "file_write",
    "file_delete",
    "subprocess",
})


def classify_step_risk(action: str, step: Optional[Any] = None) -> RiskLevel:
    """
    Classify a step's risk level.

    Args:
        action: Step action name (e.g. "run_code", "navigate").
        step: Optional TaskStep for context (e.g. target URL for navigate).

    Returns:
        RiskLevel: low, medium, or high.
    """
    action_lower = (action or "").strip().lower()
    if action_lower in _HIGH_RISK_ACTIONS:
        return RiskLevel.HIGH
    if action_lower in _MEDIUM_RISK_ACTIONS:
        return RiskLevel.MEDIUM
    if action_lower in _LOW_RISK_ACTIONS:
        # Special case: navigate to unknown URLs can be medium
        if action_lower == "navigate" and step and getattr(step, "target", None):
            target = str(step.target).lower()
            low_risk_markers = ("example.com", "localhost", "127.0.0.1", "about:blank")
            if not any(m in target for m in low_risk_markers):
                return RiskLevel.MEDIUM
        return RiskLevel.LOW
    # Unknown actions default to high for safety
    return RiskLevel.HIGH


def requires_approval(
    action: str,
    step: Optional[Any],
    require_approval_level: str,
) -> bool:
    """
    Determine if a step requires user approval.

    Args:
        action: Step action.
        step: Optional TaskStep.
        require_approval_level: "none" | "medium" | "high".

    Returns:
        True if approval is required.
    """
    if not require_approval_level or require_approval_level.lower() == "none":
        return False
    risk = classify_step_risk(action, step)
    level = require_approval_level.lower()
    if level == "high":
        return risk == RiskLevel.HIGH
    if level == "medium":
        return risk in (RiskLevel.HIGH, RiskLevel.MEDIUM)
    return False


def is_transient_error(exc: BaseException) -> bool:
    """
    Check if an exception is transient (retryable).

    Transient: timeout, rate limit, network/connection errors.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    name = type(exc).__name__
    if "RateLimit" in name or "429" in str(exc):
        return True
    if "Timeout" in name or "timeout" in str(exc).lower():
        return True
    if "Connection" in name or "connection" in str(exc).lower():
        return True
    if "Network" in name or "network" in str(exc).lower():
        return True
    # GrokAPIError with 429
    if hasattr(exc, "details") and isinstance(getattr(exc, "details"), dict):
        if exc.details.get("status_code") == 429:
            return True
    return False


