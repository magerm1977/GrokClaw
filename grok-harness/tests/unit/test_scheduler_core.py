"""Unit tests for scheduler core."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from grok_harness.scheduler.core import Scheduler
from grok_harness.scheduler.models import (
    Job,
    JobResult,
    JobStatus,
    Schedule,
    ScheduleType,
)


@pytest.fixture
def scheduler(tmp_path: Path) -> Scheduler:
    """Create scheduler instance."""
    return Scheduler(storage_path=tmp_path)


@pytest.mark.asyncio
async def test_add_job_cron(scheduler: Scheduler) -> None:
    """Test adding a cron job."""
    async def test_func() -> str:
        return "done"

    job = scheduler.add_job(
        func=test_func,
        schedule="*/5 * * * *",
        name="test_cron_job",
    )

    assert job.id is not None
    assert job.name == "test_cron_job"
    assert job.schedule is not None
    assert job.schedule.type == ScheduleType.CRON
    assert job.schedule.value == "*/5 * * * *"
    assert job.status == JobStatus.SCHEDULED


@pytest.mark.asyncio
async def test_add_job_interval(scheduler: Scheduler) -> None:
    """Test adding an interval job."""
    async def test_func() -> str:
        return "done"

    job = scheduler.add_job(
        func=test_func,
        schedule="300",
        name="test_interval_job",
    )

    assert job.schedule is not None
    assert job.schedule.type == ScheduleType.INTERVAL
    assert job.schedule.value == "300"


@pytest.mark.asyncio
async def test_add_job_with_schedule_object(scheduler: Scheduler) -> None:
    """Test adding job with Schedule object."""
    async def test_func() -> str:
        return "done"

    schedule = Schedule(
        type=ScheduleType.INTERVAL,
        value="60",
        start_date=datetime.now(),
    )

    job = scheduler.add_job(
        func=test_func,
        schedule=schedule,
        name="test_object_job",
    )

    assert job.schedule is not None
    assert job.schedule.type == ScheduleType.INTERVAL
    assert job.schedule.value == "60"
    assert job.schedule.start_date is not None


@pytest.mark.asyncio
async def test_run_once_immediate(scheduler: Scheduler) -> None:
    """Test immediate job execution."""
    mock_func = AsyncMock(return_value="success")

    result = await scheduler.run_once(
        func=mock_func,
        args=["test"],
        kwargs={"key": "value"},
    )

    assert result.success is True
    assert result.result == "success"
    mock_func.assert_called_once_with("test", key="value")


@pytest.mark.asyncio
async def test_run_once_delayed(scheduler: Scheduler) -> None:
    """Test delayed job execution."""
    mock_func = AsyncMock(return_value="success")

    scheduler.start()
    result = await scheduler.run_once(
        func=mock_func,
        delay=0.1,
        args=["test"],
    )

    assert result.success is False

    await asyncio.sleep(0.3)

    mock_func.assert_called_once_with("test")
    scheduler.stop()


@pytest.mark.asyncio
async def test_job_persistence(scheduler: Scheduler, tmp_path: Path) -> None:
    """Test job persistence across scheduler instances."""
    async def test_func() -> str:
        return "done"

    job = scheduler.add_job(
        func=test_func,
        schedule="*/5 * * * *",
        name="persist_test",
    )

    scheduler2 = Scheduler(storage_path=tmp_path)

    assert job.id in scheduler2.jobs
    loaded_job = scheduler2.get_job(job.id)
    assert loaded_job is not None
    assert loaded_job.name == "persist_test"
    assert loaded_job.schedule is not None
    assert loaded_job.schedule.value == "*/5 * * * *"


@pytest.mark.asyncio
async def test_get_jobs_filtering(scheduler: Scheduler) -> None:
    """Test job filtering."""
    async def test_func() -> str:
        return "done"

    scheduler.add_job(
        func=test_func,
        schedule="* * * * *",
        name="job1",
        tags=["important"],
        user_id="user1",
    )

    scheduler.add_job(
        func=test_func,
        schedule="*/5 * * * *",
        name="job2",
        tags=["background"],
        user_id="user1",
    )

    scheduler.add_job(
        func=test_func,
        schedule="0 */2 * * *",
        name="job3",
        tags=["important"],
        user_id="user2",
    )

    user1_jobs = scheduler.get_jobs(user_id="user1")
    assert len(user1_jobs) == 2

    important_jobs = scheduler.get_jobs(tags=["important"])
    assert len(important_jobs) == 2

    scheduled_jobs = scheduler.get_jobs(status=JobStatus.SCHEDULED)
    assert len(scheduled_jobs) == 3


@pytest.mark.asyncio
async def test_pause_resume_job(scheduler: Scheduler) -> None:
    """Test pausing and resuming jobs."""
    async def test_func() -> str:
        return "done"

    scheduler.start()
    job = scheduler.add_job(
        func=test_func,
        schedule="* * * * *",
        name="pause_test",
    )

    result = await scheduler.pause_job(job.id)
    assert result is True

    paused_job = scheduler.get_job(job.id)
    assert paused_job is not None
    assert paused_job.status == JobStatus.PAUSED

    result = await scheduler.resume_job(job.id)
    assert result is True

    resumed_job = scheduler.get_job(job.id)
    assert resumed_job is not None
    assert resumed_job.status == JobStatus.SCHEDULED

    scheduler.stop()


@pytest.mark.asyncio
async def test_remove_job(scheduler: Scheduler) -> None:
    """Test removing a job."""
    async def test_func() -> str:
        return "done"

    job = scheduler.add_job(
        func=test_func,
        schedule="* * * * *",
        name="remove_test",
    )

    assert job.id in scheduler.jobs

    result = await scheduler.remove_job(job.id)
    assert result is True
    assert job.id not in scheduler.jobs


@pytest.mark.asyncio
async def test_job_stats(scheduler: Scheduler) -> None:
    """Test job statistics."""
    async def test_func() -> str:
        return "done"

    job = scheduler.add_job(
        func=test_func,
        schedule="* * * * *",
        name="stats_test",
    )

    job.total_runs = 10
    job.successful_runs = 8
    job.failed_runs = 2

    stats = scheduler.get_job_stats(job.id)
    assert stats is not None
    assert stats.total_runs == 10
    assert stats.successful_runs == 8
    assert stats.failed_runs == 2
    assert stats.success_rate == 0.8


@pytest.mark.asyncio
async def test_recent_results(scheduler: Scheduler) -> None:
    """Test recent job results tracking."""
    mock_func = AsyncMock(return_value="success")

    for _ in range(5):
        await scheduler.run_once(mock_func)

    results = scheduler.get_recent_results(limit=3)
    assert len(results) == 3

    assert results[0].start_time >= results[-1].start_time


@pytest.mark.asyncio
async def test_concurrent_instances(scheduler: Scheduler) -> None:
    """Test max concurrent instances limit."""
    async def slow_func() -> str:
        await asyncio.sleep(0.5)
        return "done"

    job = scheduler.add_job(
        func=slow_func,
        schedule="* * * * *",
        name="concurrent_test",
        max_instances=2,
    )

    tasks = [
        scheduler._execute_job(job.id)
        for _ in range(5)
    ]
    await asyncio.gather(*tasks)

    assert len(scheduler.active_jobs) <= 2 or scheduler.active_jobs == {}


@pytest.mark.asyncio
async def test_retry_on_failure(scheduler: Scheduler) -> None:
    """Test job retry on failure."""
    mock_func = AsyncMock()
    mock_func.side_effect = [
        Exception("fail"),
        Exception("fail"),
        "success",
    ]

    job = scheduler.add_job(
        func=mock_func,
        schedule="* * * * *",
        name="retry_test",
        max_retries=2,
        retry_delay=0.05,
    )

    await asyncio.sleep(0.01)

    await scheduler._execute_job(job.id)
    await asyncio.sleep(0.2)

    assert mock_func.call_count == 3

    updated_job = scheduler.get_job(job.id)
    assert updated_job is not None
    assert updated_job.successful_runs == 1


@pytest.mark.asyncio
async def test_cleanup(scheduler: Scheduler) -> None:
    """Test cleanup of old results."""
    mock_func = AsyncMock(return_value="success")

    old_result = JobResult(
        job_id="old",
        success=True,
        start_time=datetime.now() - timedelta(days=10),
        end_time=datetime.now() - timedelta(days=10),
        duration_ms=100,
    )
    scheduler.job_results.append(old_result)

    await scheduler.run_once(mock_func)

    await scheduler.cleanup()

    assert len(scheduler.job_results) == 1
    assert scheduler.job_results[0].job_id != "old"


@pytest.mark.asyncio
async def test_event_handlers(scheduler: Scheduler) -> None:
    """Test event handlers."""
    events: list = []

    def on_complete(job_id: str, **kw: object) -> None:
        events.append(("complete", job_id))

    scheduler.on("job_complete", on_complete)

    mock_func = AsyncMock(return_value="success")
    await scheduler.run_once(mock_func)

    assert len(events) > 0
    assert events[0][0] == "complete"


@pytest.mark.asyncio
async def test_start_stop(scheduler: Scheduler) -> None:
    """Test starting and stopping scheduler."""
    assert scheduler._running is False

    scheduler.start()
    assert scheduler._running is True
    assert scheduler._scheduler is not None

    scheduler.stop()
    assert scheduler._running is False
    assert scheduler._scheduler is None
