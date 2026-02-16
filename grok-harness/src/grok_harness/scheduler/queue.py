"""Priority queue for jobs with time-based scheduling."""

import asyncio
import heapq
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .models import Job, JobPriority, JobStatus


@dataclass(order=True)
class QueueItem:
    """Item in priority queue."""

    priority: int
    scheduled_time: float = field(compare=False)
    job_id: str = field(compare=False)
    job: Job = field(compare=False)


class PriorityJobQueue:
    """
    Priority queue for jobs with time-based scheduling.

    Features:
    - Priority-based ordering (higher priority first)
    - Time-based scheduling (future execution)
    - Job cancellation
    - Queue statistics
    """

    def __init__(self) -> None:
        self._queue: List[QueueItem] = []
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._cancelled: Set[str] = set()

    def _priority_value(self, job: Job) -> int:
        """Get priority value (lower = higher priority)."""
        priority_map = {
            JobPriority.CRITICAL: 0,
            JobPriority.HIGH: 1,
            JobPriority.NORMAL: 2,
            JobPriority.LOW: 3,
        }
        return priority_map.get(job.priority, 2)

    async def put(self, job: Job, delay_seconds: float = 0) -> None:
        """
        Add a job to the queue.

        Args:
            job: Job to queue
            delay_seconds: Delay before job becomes available
        """
        scheduled_time = datetime.now().timestamp() + delay_seconds
        priority_value = self._priority_value(job)

        item = QueueItem(
            priority=priority_value,
            scheduled_time=scheduled_time,
            job_id=job.id,
            job=job,
        )

        async with self._condition:
            heapq.heappush(self._queue, item)
            self._condition.notify()

    def _clean_top_cancelled(self) -> None:
        """Remove cancelled jobs from top of heap."""
        while self._queue and self._queue[0].job_id in self._cancelled:
            item = heapq.heappop(self._queue)
            self._cancelled.discard(item.job_id)

    async def get(self, timeout: Optional[float] = None) -> Optional[Job]:
        """
        Get the next available job.

        Args:
            timeout: Maximum time to wait for a job

        Returns:
            Next job or None if timeout
        """
        async with self._condition:
            start_time = datetime.now().timestamp()

            while True:
                now = datetime.now().timestamp()
                self._clean_top_cancelled()

                if self._queue and self._queue[0].scheduled_time <= now:
                    item = heapq.heappop(self._queue)
                    return item.job

                if self._queue:
                    wait_time = self._queue[0].scheduled_time - now
                else:
                    if timeout is not None:
                        elapsed = datetime.now().timestamp() - start_time
                        if elapsed >= timeout:
                            return None
                    wait_time = timeout

                if timeout is not None:
                    elapsed = datetime.now().timestamp() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                    if wait_time is not None and wait_time > 0:
                        wait_time = min(wait_time, remaining)
                    else:
                        wait_time = remaining

                try:
                    if wait_time is not None and wait_time > 0:
                        await asyncio.wait_for(
                            self._condition.wait(),
                            timeout=wait_time,
                        )
                    else:
                        await self._condition.wait()
                except asyncio.TimeoutError:
                    continue

    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued job."""
        async with self._condition:
            for item in self._queue:
                if item.job_id == job_id:
                    self._cancelled.add(job_id)
                    self._condition.notify()
                    return True
            return False

    async def peek(self) -> Optional[Job]:
        """Look at next job without removing."""
        async with self._condition:
            self._clean_top_cancelled()
            if not self._queue:
                return None
            return self._queue[0].job

    async def size(self) -> int:
        """Get queue size (excluding cancelled)."""
        async with self._condition:
            count = sum(
                1 for item in self._queue
                if item.job_id not in self._cancelled
            )
            return count

    async def is_empty(self) -> bool:
        """Check if queue is empty."""
        return await self.size() == 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        async with self._condition:
            now = datetime.now().timestamp()
            priority_counts: Dict[int, int] = defaultdict(int)
            next_wait: Optional[float] = None

            for item in self._queue:
                if item.job_id not in self._cancelled:
                    priority_counts[item.priority] += 1
                    if next_wait is None:
                        wait = item.scheduled_time - now
                        next_wait = max(0.0, wait)

            queued = sum(
                1 for item in self._queue
                if item.job_id not in self._cancelled
            )

            return {
                "total_queued": queued,
                "total_cancelled": len(self._cancelled),
                "by_priority": dict(priority_counts),
                "next_job_wait_seconds": next_wait,
            }
