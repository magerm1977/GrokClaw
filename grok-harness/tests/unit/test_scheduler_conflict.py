"""Unit tests for scheduler conflict detection."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from grok_harness.scheduler.conflict import (
    ConflictAwareScheduler,
    ConflictDetector,
    ResourceLock,
)
from grok_harness.scheduler.models import (
    Job,
    JobPriority,
    JobStatus,
    Schedule,
    ScheduleType,
)
from grok_harness.utils.errors import ConflictError


@pytest.fixture
def mock_base_scheduler() -> Mock:
    """Mock base scheduler."""
    scheduler = Mock()
    scheduler.jobs = {}
    scheduler.add_job = Mock()
    scheduler.get_job = Mock()
    scheduler.pause_job = AsyncMock()
    scheduler.resume_job = AsyncMock()
    return scheduler


@pytest.mark.asyncio
async def test_conflict_detector_init() -> None:
    """Test conflict detector initialization."""
    detector = ConflictDetector()
    assert detector.resource_locks == {}
    assert len(detector.job_dependencies) == 0


@pytest.mark.asyncio
async def test_declare_resource() -> None:
    """Test declaring a resource."""
    detector = ConflictDetector()
    detector.declare_resource("job1", "database")

    assert "database" in detector.resource_locks
    assert detector.resource_locks["database"].resource_id == "database"


@pytest.mark.asyncio
async def test_add_dependency() -> None:
    """Test adding job dependency."""
    detector = ConflictDetector()
    detector.add_dependency("job2", "job1")

    assert "job2" in detector.job_dependencies
    assert "job1" in detector.job_dependencies["job2"]


@pytest.mark.asyncio
async def test_add_conflict() -> None:
    """Test adding job conflict."""
    detector = ConflictDetector()
    detector.add_conflict("job1", "job2")

    assert "job1" in detector.job_conflicts
    assert "job2" in detector.job_conflicts["job1"]
    assert "job1" in detector.job_conflicts["job2"]


@pytest.mark.asyncio
async def test_acquire_resources() -> None:
    """Test acquiring resources."""
    detector = ConflictDetector()

    class TestJob:
        id = "job1"
        resources = ["db1", "db2"]

    job = TestJob()

    success = await detector.acquire_resources(job)
    assert success is True

    assert detector.resource_locks["db1"].holder == "job1"
    assert detector.resource_locks["db2"].holder == "job1"


@pytest.mark.asyncio
async def test_release_resources() -> None:
    """Test releasing resources."""
    detector = ConflictDetector()

    class TestJob:
        id = "job1"
        resources = ["db1"]

    job = TestJob()

    await detector.acquire_resources(job)
    assert detector.resource_locks["db1"].holder == "job1"

    detector.release_all_resources("job1")
    assert detector.resource_locks["db1"].holder is None


@pytest.mark.asyncio
async def test_conflict_aware_scheduler(mock_base_scheduler: Mock) -> None:
    """Test conflict-aware scheduler."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    async def dummy() -> str:
        return "done"

    job = Job(
        id="test-job",
        name="Test Job",
        func=dummy,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
        priority=JobPriority.NORMAL,
    )

    result = await scheduler.schedule_with_conflicts(
        job,
        resources=["database"],
    )

    assert "database" in scheduler.conflict_detector.resource_locks
    assert mock_base_scheduler.add_job.called


@pytest.mark.asyncio
async def test_conflict_detection(mock_base_scheduler: Mock) -> None:
    """Test conflict detection when running job holds resource."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    async def dummy() -> str:
        return "done"

    job1 = Job(
        id="job1",
        name="Job 1",
        func=dummy,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )
    job1.resources = ["database"]
    job1.status = JobStatus.RUNNING

    job2 = Job(
        id="job2",
        name="Job 2",
        func=dummy,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )

    mock_base_scheduler.jobs = {"job1": job1}

    with pytest.raises(ConflictError):
        await scheduler.schedule_with_conflicts(job2, resources=["database"])


@pytest.mark.asyncio
async def test_waiting_queue(mock_base_scheduler: Mock) -> None:
    """Test waiting jobs queue."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    async def dummy() -> str:
        return "done"

    job = Job(
        id="waiting-job",
        name="Waiting Job",
        func=dummy,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )

    scheduler.waiting_jobs.append(
        (job, datetime.now() + timedelta(minutes=5))
    )

    waiting = scheduler.get_waiting_jobs()
    assert len(waiting) == 1
    assert waiting[0]["job_id"] == "waiting-job"


@pytest.mark.asyncio
async def test_resource_status(mock_base_scheduler: Mock) -> None:
    """Test resource status reporting."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    scheduler.conflict_detector.declare_resource("job1", "db1")
    scheduler.conflict_detector.resource_locks["db1"].holder = "job1"

    status = scheduler.get_resource_status()
    assert "db1" in status
    assert status["db1"] == "job1"


@pytest.mark.asyncio
async def test_retry_delay_calculation(mock_base_scheduler: Mock) -> None:
    """Test retry delay calculation by priority."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    job_low = Job(priority=JobPriority.LOW)
    job_normal = Job(priority=JobPriority.NORMAL)
    job_high = Job(priority=JobPriority.HIGH)
    job_critical = Job(priority=JobPriority.CRITICAL)

    delay_low = scheduler._calculate_retry_delay(job_low)
    delay_normal = scheduler._calculate_retry_delay(job_normal)
    delay_high = scheduler._calculate_retry_delay(job_high)
    delay_critical = scheduler._calculate_retry_delay(job_critical)

    assert delay_low > delay_normal
    assert delay_normal > delay_high
    assert delay_high >= delay_critical


@pytest.mark.asyncio
async def test_execute_with_resources(mock_base_scheduler: Mock) -> None:
    """Test executing job with resources."""
    scheduler = ConflictAwareScheduler(mock_base_scheduler)

    async def test_func() -> str:
        return "success"

    job = Job(
        id="exec-job",
        name="Exec Job",
        func=test_func,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )
    job.resources = ["db1"]

    mock_base_scheduler.get_job.return_value = job

    result = await scheduler.execute_with_resources("exec-job")

    assert result == "success"
    assert (
        scheduler.conflict_detector.resource_locks["db1"].holder is None
    )
