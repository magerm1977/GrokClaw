"""Unit tests for scheduler priority queue."""

import asyncio
from unittest.mock import Mock

import pytest

from grok_harness.scheduler.models import Job, JobPriority, Schedule, ScheduleType
from grok_harness.scheduler.queue import PriorityJobQueue


@pytest.fixture
def queue() -> PriorityJobQueue:
    """Create priority queue."""
    return PriorityJobQueue()


def make_job(
    job_id: str,
    priority: JobPriority = JobPriority.NORMAL,
) -> Job:
    """Create a test job."""
    return Job(
        id=job_id,
        name=f"job-{job_id}",
        func=lambda: None,
        schedule=Schedule(type=ScheduleType.ONCE, value="now"),
        priority=priority,
    )


@pytest.mark.asyncio
async def test_put_get(queue: PriorityJobQueue) -> None:
    """Test put and get."""
    job = make_job("job1")
    await queue.put(job)

    result = await queue.get(timeout=1.0)
    assert result is not None
    assert result.id == "job1"


@pytest.mark.asyncio
async def test_priority_ordering(queue: PriorityJobQueue) -> None:
    """Test higher priority jobs come first."""
    low = make_job("low", JobPriority.LOW)
    high = make_job("high", JobPriority.HIGH)
    normal = make_job("normal", JobPriority.NORMAL)

    await queue.put(low)
    await queue.put(high)
    await queue.put(normal)

    first = await queue.get(timeout=1.0)
    assert first is not None
    assert first.id == "high"

    second = await queue.get(timeout=1.0)
    assert second is not None
    assert second.id == "normal"

    third = await queue.get(timeout=1.0)
    assert third is not None
    assert third.id == "low"


@pytest.mark.asyncio
async def test_cancel(queue: PriorityJobQueue) -> None:
    """Test job cancellation."""
    job = make_job("cancel-me")
    await queue.put(job)

    cancelled = await queue.cancel("cancel-me")
    assert cancelled is True

    result = await queue.get(timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_peek(queue: PriorityJobQueue) -> None:
    """Test peek without removing."""
    job = make_job("peek-job")
    await queue.put(job)

    peeked = await queue.peek()
    assert peeked is not None
    assert peeked.id == "peek-job"

    got = await queue.get(timeout=1.0)
    assert got is not None
    assert got.id == "peek-job"


@pytest.mark.asyncio
async def test_size(queue: PriorityJobQueue) -> None:
    """Test queue size."""
    assert await queue.size() == 0

    await queue.put(make_job("1"))
    await queue.put(make_job("2"))
    assert await queue.size() == 2

    await queue.get(timeout=1.0)
    assert await queue.size() == 1


@pytest.mark.asyncio
async def test_is_empty(queue: PriorityJobQueue) -> None:
    """Test is_empty."""
    assert await queue.is_empty() is True

    await queue.put(make_job("1"))
    assert await queue.is_empty() is False


@pytest.mark.asyncio
async def test_get_stats(queue: PriorityJobQueue) -> None:
    """Test queue statistics."""
    await queue.put(make_job("1", JobPriority.HIGH))
    await queue.put(make_job("2", JobPriority.NORMAL))

    stats = await queue.get_stats()

    assert "total_queued" in stats
    assert "by_priority" in stats
    assert stats["total_queued"] == 2


@pytest.mark.asyncio
async def test_delayed_put(queue: PriorityJobQueue) -> None:
    """Test delayed job becomes available."""
    job = make_job("delayed")
    await queue.put(job, delay_seconds=0.05)

    result = await queue.get(timeout=0.1)
    assert result is not None
    assert result.id == "delayed"
