"""Unit tests for scheduler pattern learning."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from grok_harness.scheduler.learning import AdaptiveScheduler, PatternLearner
from grok_harness.scheduler.models import Job, Schedule, ScheduleType
from grok_harness.utils.errors import LearningError


@pytest.fixture
def mock_grok_client() -> AsyncMock:
    """Mock Grok client."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"optimal_times": {"job1": 10}, "risk_periods": [], "conflict_predictions": [], "schedule_adjustments": [], "trends": {}}'
                    }
                }
            ]
        }
    )
    return client


@pytest.fixture
def mock_conflict_scheduler() -> Mock:
    """Mock conflict-aware scheduler."""
    sched = Mock()
    sched.schedule_with_conflicts = AsyncMock()
    sched.conflict_detector = Mock()
    sched.conflict_detector.add_conflict = Mock()
    sched.get_waiting_jobs = Mock(return_value=[])
    sched.get_resource_status = Mock(return_value={})
    return sched


@pytest.fixture
def mock_base_scheduler() -> Mock:
    """Mock base scheduler."""
    sched = Mock()
    sched.get_job = Mock(return_value=None)
    sched.pause_job = AsyncMock()
    sched.resume_job = AsyncMock()
    return sched


@pytest.mark.asyncio
async def test_record_execution(mock_grok_client: AsyncMock) -> None:
    """Test recording execution for learning."""
    learner = PatternLearner(mock_grok_client)

    job = Job(
        id="job1",
        name="Test Job",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
        tags=["test"],
    )

    learner.record_execution(job, success=True, duration=1.5)
    learner.record_execution(job, success=False, duration=0.5)

    assert len(learner.execution_history) == 2
    assert learner.execution_history[0]["success"] is True
    assert learner.execution_history[1]["success"] is False
    assert learner.execution_history[0]["duration"] == 1.5


@pytest.mark.asyncio
async def test_analyze_patterns_insufficient_data(
    mock_grok_client: AsyncMock,
) -> None:
    """Test analyze returns empty with insufficient data."""
    learner = PatternLearner(mock_grok_client)

    job = Job(
        id="job1",
        name="Test",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )
    for _ in range(5):
        learner.record_execution(job, True, 1.0)

    result = await learner.analyze_patterns()
    assert result == {}
    mock_grok_client.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_patterns_success(
    mock_grok_client: AsyncMock,
) -> None:
    """Test pattern analysis with Grok."""
    learner = PatternLearner(mock_grok_client)

    job = Job(
        id="job1",
        name="Test",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )
    for _ in range(15):
        learner.record_execution(job, True, 1.0)

    result = await learner.analyze_patterns(force=True)

    assert "optimal_times" in result or result == {}
    mock_grok_client.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_optimal_schedule_no_data(
    mock_grok_client: AsyncMock,
) -> None:
    """Test suggest returns None with no patterns."""
    learner = PatternLearner(mock_grok_client)
    job = Job(
        id="job1",
        name="Test",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )

    result = await learner.suggest_optimal_schedule(job)
    assert result is None


@pytest.mark.asyncio
async def test_suggest_optimal_schedule_with_patterns(
    mock_grok_client: AsyncMock,
) -> None:
    """Test suggest returns schedule when patterns exist."""
    learner = PatternLearner(mock_grok_client)
    learner.learned_patterns = {"optimal_times": {"job1": 10}}

    job = Job(
        id="job1",
        name="Test",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )

    result = await learner.suggest_optimal_schedule(job)
    assert result is not None
    assert result.type == ScheduleType.CRON
    assert "10" in result.value


@pytest.mark.asyncio
async def test_get_risk_periods(mock_grok_client: AsyncMock) -> None:
    """Test getting risk periods."""
    learner = PatternLearner(mock_grok_client)
    learner.learned_patterns = {
        "risk_periods": [{"hour": 2, "day": 0}]
    }

    assert learner.get_risk_periods() == [{"hour": 2, "day": 0}]


@pytest.mark.asyncio
async def test_adaptive_scheduler_schedule(
    mock_base_scheduler: Mock,
    mock_grok_client: AsyncMock,
    mock_conflict_scheduler: Mock,
) -> None:
    """Test adaptive scheduler schedules with conflict check."""
    adaptive = AdaptiveScheduler(
        mock_base_scheduler,
        mock_grok_client,
        mock_conflict_scheduler,
    )

    job = Job(
        id="job1",
        name="Test",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
    )

    await adaptive.schedule_adaptive(job, resources=["db1"])

    mock_conflict_scheduler.schedule_with_conflicts.assert_called_once_with(
        job,
        ["db1"],
    )
