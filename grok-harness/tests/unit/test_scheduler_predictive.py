"""Unit tests for predictive analysis engine."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from grok_harness.scheduler.models import (
    Job,
    JobResult,
    Schedule,
    ScheduleType,
)
from grok_harness.scheduler.predictive import (
    LoadPredictor,
    Prediction,
    PredictiveEngine,
)
from grok_harness.utils.errors import PredictiveError


@pytest.fixture
def sample_job() -> Job:
    """Create sample job for tests."""
    return Job(
        id="test-job-1",
        name="Test Job",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.INTERVAL, value="300"),
        tags=["test"],
    )


@pytest.fixture
def predictive_engine() -> PredictiveEngine:
    """Create predictive engine."""
    return PredictiveEngine()


@pytest.mark.asyncio
async def test_record_execution(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test recording job execution."""
    result = JobResult(
        job_id=sample_job.id,
        success=True,
        start_time=datetime(2025, 1, 15, 10, 0),
        end_time=datetime(2025, 1, 15, 10, 1),
        duration_ms=1000,
    )

    predictive_engine.record_execution(sample_job, result)

    assert len(predictive_engine.execution_history) == 1
    entry = predictive_engine.execution_history[0]
    assert entry["job_id"] == sample_job.id
    assert entry["duration"] == 1.0
    assert entry["success"] is True
    assert entry["hour"] == 10


@pytest.mark.asyncio
async def test_predict_duration_insufficient_data(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test duration prediction with insufficient history."""
    duration, confidence = predictive_engine.predict_duration(sample_job)

    assert duration == 60.0
    assert confidence == 0.3


@pytest.mark.asyncio
async def test_predict_duration_with_history(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test duration prediction with enough history."""
    for i in range(5):
        result = JobResult(
            job_id=sample_job.id,
            success=True,
            start_time=datetime(2025, 1, 15, 10, i),
            end_time=datetime(2025, 1, 15, 10, i + 1),
            duration_ms=(i + 1) * 1000,
        )
        predictive_engine.record_execution(sample_job, result)

    duration, confidence = predictive_engine.predict_duration(sample_job)

    assert 2.0 <= duration <= 4.0
    assert 0.3 <= confidence <= 1.0


@pytest.mark.asyncio
async def test_predict_optimal_time_insufficient_data(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test optimal time prediction with insufficient data."""
    optimal = predictive_engine.predict_optimal_time(sample_job)
    assert optimal is None


@pytest.mark.asyncio
async def test_predict_optimal_time_with_history(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test optimal time prediction with enough history."""
    for hour in [8, 8, 10, 10, 14]:
        result = JobResult(
            job_id=sample_job.id,
            success=True,
            start_time=datetime(2025, 1, 15, hour, 0),
            end_time=datetime(2025, 1, 15, hour, 1),
            duration_ms=(10 if hour == 8 else 100) * 1000,
        )
        predictive_engine.record_execution(sample_job, result)

    optimal = predictive_engine.predict_optimal_time(sample_job)
    assert optimal == 8


@pytest.mark.asyncio
async def test_predict_failure_probability_no_history(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test failure probability with no history."""
    prob = predictive_engine.predict_failure_probability(sample_job)
    assert prob == 0.1


@pytest.mark.asyncio
async def test_predict_failure_probability_with_history(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test failure probability calculation."""
    for i in range(10):
        result = JobResult(
            job_id=sample_job.id,
            success=(i < 8),
            start_time=datetime(2025, 1, 15, 10, i),
            end_time=datetime(2025, 1, 15, 10, i + 1),
            duration_ms=1000,
        )
        predictive_engine.record_execution(sample_job, result)

    prob = predictive_engine.predict_failure_probability(sample_job)
    assert 0.1 <= prob <= 0.5


@pytest.mark.asyncio
async def test_predict_resource_contention(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test resource contention prediction."""
    job1 = Job(
        id="job1",
        name="Job 1",
        func=lambda: None,
        resources=["db"],
        schedule=Schedule(type=ScheduleType.CRON, value="0 * * * *"),
    )
    job2 = Job(
        id="job2",
        name="Job 2",
        func=lambda: None,
        resources=["db"],
        schedule=Schedule(type=ScheduleType.CRON, value="0 * * * *"),
    )

    contentions = predictive_engine.predict_resource_contention([job1, job2])

    assert len(contentions) >= 1
    assert any(c["resource"] == "db" for c in contentions)


@pytest.mark.asyncio
async def test_update_predictions(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test updating predictions for a job."""
    for _ in range(5):
        result = JobResult(
            job_id=sample_job.id,
            success=True,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=2000,
        )
        predictive_engine.record_execution(sample_job, result)

    predictive_engine.update_predictions(sample_job)

    pred = predictive_engine.get_predictions(sample_job.id)
    assert pred is not None
    assert isinstance(pred, Prediction)
    assert pred.job_id == sample_job.id
    assert pred.estimated_duration == 2.0
    assert pred.risk_level in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_analyze_with_grok_no_client(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test Grok analysis raises without client."""
    engine = PredictiveEngine(grok_client=None)

    with pytest.raises(PredictiveError, match="Grok client required"):
        await engine.analyze_with_grok([sample_job])


@pytest.mark.asyncio
async def test_analyze_with_grok_success(
    sample_job: Job,
) -> None:
    """Test Grok analysis with mock client."""
    mock_grok = AsyncMock()
    mock_grok.chat_completion = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"load_predictions": {}, "schedule_adjustments": [], "risk_assessment": {"test-job-1": "low"}, "optimizations": [], "capacity_recommendations": []}'
                    }
                }
            ]
        }
    )

    engine = PredictiveEngine(grok_client=mock_grok)
    result = await engine.analyze_with_grok([sample_job])

    assert "risk_assessment" in result
    assert result["risk_assessment"]["test-job-1"] == "low"


@pytest.mark.asyncio
async def test_load_predictor(
    predictive_engine: PredictiveEngine,
    sample_job: Job,
) -> None:
    """Test load predictor."""
    for _ in range(5):
        result = JobResult(
            job_id=sample_job.id,
            success=True,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=1000,
        )
        predictive_engine.record_execution(sample_job, result)

    predictor = LoadPredictor(predictive_engine)
    load = predictor.predict_load([sample_job], hours_ahead=24)

    assert isinstance(load, dict)
    assert len(load) <= 24
    if load:
        max_load = max(load.values())
        assert 0 <= max_load <= 1.0
