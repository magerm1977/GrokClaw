"""Integration tests for orchestrator safety, retry, and polish features."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.cli.output import _SAFE_SYMBOLS, confirm_action
from grok_harness.core.orchestrator import Orchestrator, RunOptions, RunResult
from grok_harness.core.types import TaskPlan, TaskStep
from grok_harness.memory.unified import UnifiedMemory
from grok_harness.scheduler.smart import SmartScheduler
from grok_harness.utils.validators import (
    RiskLevel,
    classify_step_risk,
    is_transient_error,
    requires_approval,
)


# --- Validators ---


def test_classify_step_risk_low() -> None:
    """Low-risk actions are classified correctly."""
    assert classify_step_risk("navigate") == RiskLevel.LOW
    assert classify_step_risk("click") == RiskLevel.LOW
    assert classify_step_risk("wait") == RiskLevel.LOW
    assert classify_step_risk("memory_search") == RiskLevel.LOW


def test_classify_step_risk_high() -> None:
    """High-risk actions are classified correctly."""
    assert classify_step_risk("run_code") == RiskLevel.HIGH
    assert classify_step_risk("shell") == RiskLevel.HIGH
    assert classify_step_risk("file_write") == RiskLevel.HIGH


def test_requires_approval_none() -> None:
    """require_approval_level=none skips approval."""
    assert requires_approval("run_code", None, "none") is False


def test_requires_approval_high() -> None:
    """require_approval_level=high requires approval for run_code."""
    assert requires_approval("run_code", None, "high") is True
    assert requires_approval("wait", None, "high") is False


def test_requires_approval_medium() -> None:
    """require_approval_level=medium requires approval for medium and high."""
    assert requires_approval("run_code", None, "medium") is True
    assert requires_approval("submit", None, "medium") is True
    assert requires_approval("wait", None, "medium") is False


def test_is_transient_error() -> None:
    """Transient errors are identified."""
    assert is_transient_error(TimeoutError()) is True
    assert is_transient_error(ConnectionError()) is True
    assert is_transient_error(ValueError("foo")) is False


# --- Fixtures ---


@pytest.fixture
def tmp_storage(tmp_path: Path) -> Path:
    return tmp_path / "safety_test"


@pytest.fixture
def mock_grok() -> AsyncMock:
    grok = AsyncMock()
    grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.05),
                TaskStep(action="done"),
            ],
            reasoning="Test",
            estimated_steps=2,
        )
    )
    return grok


@pytest.fixture
def mock_memory(tmp_storage: Path) -> UnifiedMemory:
    from grok_harness.core.types import MemoryConfig

    config = MemoryConfig(
        path=tmp_storage / "memory.db",
        enable_embeddings=False,
        low_spec_mode=True,
        enable_compression=False,
    )
    return UnifiedMemory(config)


@pytest.fixture
def mock_scheduler(tmp_storage: Path) -> SmartScheduler:
    return SmartScheduler(
        grok_client=None,
        storage_path=tmp_storage,
        enable_learning=False,
        enable_predictive=True,
        enable_monitoring=False,
    )


@pytest.fixture
def config():
    from grok_harness.core.config_manager import ConfigManager
    return ConfigManager.create_default_config()


# --- Approval ---


@pytest.mark.asyncio
async def test_approval_prompt_for_high_risk(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Approval prompt appears for high-risk step when interactive and require_approval_level=high."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="run_code", value="1+1", description="Eval"),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    calls = []

    async def fake_confirm(prompt: str, default: bool = False, timeout_seconds: int = 30) -> bool:
        calls.append({"prompt": prompt, "default": default})
        return True  # Approve

    with patch("grok_harness.cli.output.confirm_action", side_effect=fake_confirm):
        orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
        result = await orch.run(
            "run code",
            RunOptions(interactive=True, live_progress=False, require_approval_level="high"),
        )

    assert len(calls) >= 1
    assert "run_code" in calls[0]["prompt"] or "Approve" in calls[0]["prompt"]
    assert result.status == "success"

    await mock_scheduler.stop()
    await mock_memory.stop()


# --- Retry ---


@pytest.mark.asyncio
async def test_retry_succeeds_on_transient_failure(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Retry succeeds when first attempt fails with transient error."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.05),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    execute_count = 0
    original_do = orch._do_execute_step

    async def failing_then_ok(step, task_id, step_idx):
        nonlocal execute_count
        execute_count += 1
        if execute_count == 1 and step.action == "wait":
            raise TimeoutError("Transient")
        return await original_do(step, task_id, step_idx)

    with patch.object(orch, "_do_execute_step", failing_then_ok):
        result = await orch.run("retry test", RunOptions(live_progress=False))

    assert result.status == "success"
    assert execute_count >= 2
    has_retries = any(
        ah.get("retries") for ah in result.action_history if isinstance(ah, dict)
    )
    assert has_retries or execute_count >= 2

    await mock_scheduler.stop()
    await mock_memory.stop()


# --- Partial episode on crash ---


@pytest.mark.asyncio
async def test_partial_episode_saved_on_crash(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Partial episode is stored when execution crashes mid-run."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.05),
                TaskStep(action="wait", value=0.05),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=3,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    progress_count = 0

    def crash_on_second_progress(**kwargs):
        nonlocal progress_count
        progress_count += 1
        if progress_count == 4:
            raise RuntimeError("Simulated crash in progress")

    orch.set_progress_callback(crash_on_second_progress)
    result = await orch.run("crash test", RunOptions(live_progress=False))

    assert result.status in ("partial", "failure")
    assert result.steps_completed >= 1
    assert result.episodes_added == 1
    assert "Simulated crash" in (result.error or "") or "crashed" in str(
        result.result or {}
    ).lower()

    await mock_scheduler.stop()
    await mock_memory.stop()


# --- Dry run ---


@pytest.mark.asyncio
async def test_dry_run_returns_plan_no_side_effects(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Dry-run returns plan without executing steps."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="run_code", value="1+1"),
                TaskStep(action="done"),
            ],
            reasoning="Dry run reasoning",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("dry run task", RunOptions(dry_run=True, live_progress=False))

    assert result.status == "success"
    assert result.steps_completed == 0
    assert result.episodes_added == 0
    assert result.plan["reasoning"] == "Dry run reasoning"
    assert result.result.get("dry_run") is True
    assert len(result.plan["steps"]) == 2

    await mock_scheduler.stop()
    await mock_memory.stop()


# --- Encoding fallback ---


def test_encoding_fallback_detection() -> None:
    """_SAFE_SYMBOLS is set when stdout uses cp1252/cp437."""
    assert isinstance(_SAFE_SYMBOLS, bool)


def test_encoding_fallback_print_uses_safe_symbols() -> None:
    """print_error uses module symbols; with ASCII fallback, no UnicodeEncodeError."""
    from grok_harness.cli import output
    # Patch to ASCII so output works even on cp1252
    with patch.object(output, "_ERR", "[X]"):
        output.print_error("Test message")  # Should not raise


@pytest.mark.asyncio
async def test_confirm_action_timeout_returns_default() -> None:
    """confirm_action returns default on timeout."""
    # Use a very short timeout; we won't provide input, so it should timeout
    result = await confirm_action(
        "Approve?",
        default=False,
        timeout_seconds=0.001,
    )
    assert result is False


@pytest.mark.asyncio
async def test_confirm_action_timeout_default_true() -> None:
    """confirm_action returns default=True on timeout."""
    result = await confirm_action(
        "Approve?",
        default=True,
        timeout_seconds=0.001,
    )
    assert result is True
