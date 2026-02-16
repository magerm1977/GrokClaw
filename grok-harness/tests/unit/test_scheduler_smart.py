"""Unit tests for smart scheduler."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from grok_harness.scheduler.models import (
    Job,
    JobPriority,
    JobResult,
    JobStatus,
)
from grok_harness.scheduler.smart import SmartScheduler


@pytest.fixture
def tmp_storage(tmp_path: Path) -> Path:
    """Temporary storage for scheduler."""
    return tmp_path / "smart_scheduler"


@pytest.fixture
def smart_scheduler_no_grok(tmp_storage: Path) -> SmartScheduler:
    """Create smart scheduler without Grok (no learning)."""
    return SmartScheduler(
        grok_client=None,
        storage_path=tmp_storage,
        enable_learning=False,
        enable_predictive=True,
        enable_monitoring=True,
    )


@pytest.fixture
def smart_scheduler_minimal(tmp_storage: Path) -> SmartScheduler:
    """Create minimal smart scheduler (predictive + monitoring off)."""
    return SmartScheduler(
        grok_client=None,
        storage_path=tmp_storage,
        enable_learning=False,
        enable_predictive=False,
        enable_monitoring=False,
    )


@pytest.mark.asyncio
async def test_smart_scheduler_init(smart_scheduler_no_grok: SmartScheduler) -> None:
    """Test smart scheduler initialization."""
    assert smart_scheduler_no_grok.base_scheduler is not None
    assert smart_scheduler_no_grok.conflict_scheduler is not None
    assert smart_scheduler_no_grok.predictive is not None
    assert smart_scheduler_no_grok.monitor is not None
    assert smart_scheduler_no_grok.queue is not None
    assert smart_scheduler_no_grok.adaptive is None
    assert smart_scheduler_no_grok.learner is None


@pytest.mark.asyncio
async def test_smart_scheduler_start_stop(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test start and stop lifecycle."""
    await smart_scheduler_no_grok.start()
    assert smart_scheduler_no_grok._running is True

    await smart_scheduler_no_grok.stop()
    assert smart_scheduler_no_grok._running is False


@pytest.mark.asyncio
async def test_schedule_job(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test scheduling a job."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="*/5 * * * *",
        name="test_cron",
    )

    assert job is not None
    assert job.name == "test_cron"
    assert job.schedule is not None
    assert smart_scheduler_no_grok.stats["jobs_scheduled"] >= 1

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_schedule_interval_job(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test scheduling an interval job."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="test_interval",
    )

    assert job is not None
    assert job.schedule is not None
    assert job.schedule.type.value == "interval"
    assert job.schedule.value == "300"

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_run_now_immediate(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test immediate job execution."""
    await smart_scheduler_no_grok.start()

    mock_func = AsyncMock(return_value="result")

    result = await smart_scheduler_no_grok.run_now(
        func=mock_func,
        args=["a"],
        kwargs={"b": 1},
    )

    assert result.success is True
    assert result.result == "result"
    assert result.duration_ms >= 0
    mock_func.assert_called_once_with("a", b=1)

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_run_now_with_delay(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test run_now with delay queues job."""
    await smart_scheduler_no_grok.start()

    mock_func = AsyncMock(return_value="delayed")

    result = await smart_scheduler_no_grok.run_now(
        func=mock_func,
        delay=60,
    )

    assert result.success is False
    assert "queued" in result.error.lower()
    mock_func.assert_not_called()

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_get_job(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test getting job by ID."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="get_test",
    )

    found = smart_scheduler_no_grok.get_job(job.id)
    assert found is not None
    assert found.id == job.id

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_get_job_stats(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test getting job statistics."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="stats_test",
    )

    stats = smart_scheduler_no_grok.get_job_stats(job.id)
    assert stats is not None
    assert "total_runs" in stats or "job_id" in stats

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_get_system_health(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test system health report."""
    await smart_scheduler_no_grok.start()

    health = await smart_scheduler_no_grok.get_system_health()

    assert "status" in health
    assert "total_jobs" in health
    assert "stats" in health
    assert "queue_size" in health
    assert health["status"] == "running"

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_get_optimization_report(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test optimization report."""
    await smart_scheduler_no_grok.start()

    report = await smart_scheduler_no_grok.get_optimization_report()

    assert "timestamp" in report
    assert "system_health" in report
    assert "queue_stats" in report

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_get_queue_stats(smart_scheduler_no_grok: SmartScheduler) -> None:
    """Test queue statistics."""
    stats = await smart_scheduler_no_grok.get_queue_stats()
    assert isinstance(stats, dict)


@pytest.mark.asyncio
async def test_cleanup(
    smart_scheduler_no_grok: SmartScheduler,
) -> None:
    """Test cleanup."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="cleanup_test",
    )

    await smart_scheduler_no_grok.cleanup()

    state_file = smart_scheduler_no_grok.storage_path / "smart_state.json"
    assert state_file.exists()

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_smart_scheduler_with_grok(tmp_storage: Path) -> None:
    """Test smart scheduler with Grok (learning enabled)."""
    mock_grok = AsyncMock()
    mock_grok.chat_completion = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"optimal_times": {}, "risk_periods": [], "conflict_predictions": [], "schedule_adjustments": [], "trends": {}}'
                    }
                }
            ]
        }
    )

    scheduler = SmartScheduler(
        grok_client=mock_grok,
        storage_path=tmp_storage,
        enable_learning=True,
        enable_predictive=True,
        enable_monitoring=True,
    )

    assert scheduler.adaptive is not None
    assert scheduler.learner is not None

    await scheduler.start()

    async def sample_func() -> str:
        return "ok"

    job = await scheduler.schedule(
        func=sample_func,
        schedule="300",
        name="grok_test",
        adaptive=True,
    )

    assert job is not None

    await scheduler.stop()


@pytest.mark.asyncio
async def test_pause_resume_job(smart_scheduler_no_grok: SmartScheduler) -> None:
    """Test pausing and resuming a job."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="pause_test",
    )

    paused = await smart_scheduler_no_grok.pause_job(job.id)
    assert paused is True

    resumed = await smart_scheduler_no_grok.resume_job(job.id)
    assert resumed is True

    await smart_scheduler_no_grok.stop()


@pytest.mark.asyncio
async def test_remove_job(smart_scheduler_no_grok: SmartScheduler) -> None:
    """Test removing a job."""
    await smart_scheduler_no_grok.start()

    async def sample_func() -> str:
        return "ok"

    job = await smart_scheduler_no_grok.schedule(
        func=sample_func,
        schedule="300",
        name="remove_test",
    )

    removed = await smart_scheduler_no_grok.remove_job(job.id)
    assert removed is True

    found = smart_scheduler_no_grok.get_job(job.id)
    assert found is None

    await smart_scheduler_no_grok.stop()
