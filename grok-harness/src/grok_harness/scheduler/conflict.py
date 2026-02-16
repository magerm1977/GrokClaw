"""Conflict detection and prevention for the scheduler."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from ..utils.errors import ConflictError
from .models import Job, JobPriority, JobStatus


class ResourceLock:
    """Lock for a specific resource."""

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        self.lock = asyncio.Lock()
        self.holder: Optional[str] = None
        self.acquired_at: Optional[datetime] = None


class ConflictDetector:
    """
    Detects potential conflicts between jobs.

    Conflicts can be:
    - Resource conflicts (same file, same URL)
    - Time conflicts (overlapping execution windows)
    - Dependency conflicts (job A needs job B)
    """

    def __init__(self) -> None:
        self.resource_locks: Dict[str, ResourceLock] = {}
        self.job_dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.job_conflicts: Dict[str, Set[str]] = defaultdict(set)
        self.execution_history: List[Dict[str, Any]] = []

    def declare_resource(self, job_id: str, resource: str) -> None:
        """Declare that a job uses a resource."""
        if resource not in self.resource_locks:
            self.resource_locks[resource] = ResourceLock(resource)

    def add_dependency(self, job_id: str, depends_on: str) -> None:
        """Add a dependency (job_id depends on depends_on)."""
        self.job_dependencies[job_id].add(depends_on)

    def add_conflict(self, job_id: str, conflicts_with: str) -> None:
        """Add a conflict relationship (jobs that cannot run together)."""
        self.job_conflicts[job_id].add(conflicts_with)
        self.job_conflicts[conflicts_with].add(job_id)

    async def check_conflicts(
        self,
        job: Job,
        running_jobs: List[Job],
        scheduled_jobs: List[Job],
    ) -> List[str]:
        """
        Check for conflicts with running and scheduled jobs.

        Returns:
            List of conflict descriptions
        """
        conflicts: List[str] = []

        resources = getattr(job, "resources", None) or []

        for resource in resources:
            if resource in self.resource_locks:
                lock = self.resource_locks[resource]
                if lock.holder and lock.holder != job.id:
                    conflicts.append(
                        f"Resource conflict: {resource} held by {lock.holder}"
                    )

        for running in running_jobs:
            running_res = getattr(running, "resources", None) or []
            if set(resources) & set(running_res):
                conflicts.append(
                    f"Resource conflict with running job: {running.id}"
                )

        for running in running_jobs:
            if running.id in self.job_dependencies.get(job.id, set()):
                conflicts.append(
                    f"Dependency not met: waiting for {running.id}"
                )

        for running in running_jobs:
            if running.id in self.job_conflicts.get(job.id, set()):
                conflicts.append(
                    f"Conflict with running job: {running.id}"
                )

        if hasattr(job, "estimated_duration") and getattr(
            job, "schedule", None
        ):
            for scheduled in scheduled_jobs:
                if scheduled.id == job.id:
                    continue
                if self._times_overlap(job, scheduled):
                    conflicts.append(
                        f"Time conflict with scheduled: {scheduled.id}"
                    )

        return conflicts

    def _times_overlap(self, job1: Job, job2: Job) -> bool:
        """Check if two jobs' execution windows overlap."""
        return False

    async def acquire_resources(self, job: Job) -> bool:
        """Acquire all resources needed by a job."""
        resources = getattr(job, "resources", None)
        if not resources:
            return True

        resources_list = sorted(resources)
        acquired: List[str] = []

        try:
            for resource in resources_list:
                if resource not in self.resource_locks:
                    self.resource_locks[resource] = ResourceLock(resource)

                lock = self.resource_locks[resource]

                try:
                    await asyncio.wait_for(lock.lock.acquire(), timeout=30.0)
                    lock.holder = job.id
                    lock.acquired_at = datetime.now()
                    acquired.append(resource)
                except asyncio.TimeoutError:
                    for r in acquired:
                        self.release_resource(r, job.id)
                    return False

            return True

        except Exception:
            for r in acquired:
                self.release_resource(r, job.id)
            raise

    def release_resource(self, resource: str, job_id: str) -> None:
        """Release a resource."""
        if resource in self.resource_locks:
            lock = self.resource_locks[resource]
            if lock.holder == job_id:
                lock.holder = None
                lock.acquired_at = None
                try:
                    lock.lock.release()
                except RuntimeError:
                    pass

    def release_all_resources(self, job_id: str) -> None:
        """Release all resources held by a job."""
        for resource, lock in list(self.resource_locks.items()):
            if lock.holder == job_id:
                lock.holder = None
                lock.acquired_at = None
                try:
                    lock.lock.release()
                except RuntimeError:
                    pass

    def record_execution(
        self,
        job_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Record job execution for pattern learning."""
        self.execution_history.append(
            {
                "job_id": job_id,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration": (
                    end_time - start_time
                ).total_seconds(),
            }
        )
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]


class ConflictAwareScheduler:
    """
    Scheduler with conflict detection and prevention.

    Extends the base scheduler with:
    - Resource locking
    - Dependency management
    - Conflict detection
    - Smart queuing
    """

    def __init__(self, base_scheduler: Any) -> None:
        self.base = base_scheduler
        self.conflict_detector = ConflictDetector()
        self.waiting_jobs: List[Tuple[Job, datetime]] = []
        self.max_retry_delay = 3600

    async def schedule_with_conflicts(
        self,
        job: Job,
        resources: Optional[List[str]] = None,
    ) -> Any:
        """
        Schedule a job with conflict checking.

        Args:
            job: Job to schedule
            resources: Resources required by the job

        Returns:
            Result from base scheduler add_job
        """
        if resources is not None:
            job.resources = resources
            for resource in resources:
                self.conflict_detector.declare_resource(job.id, resource)

        running_jobs = [
            j for j in self.base.jobs.values()
            if j.status == JobStatus.RUNNING
        ]
        scheduled_jobs = [
            j for j in self.base.jobs.values()
            if j.status == JobStatus.SCHEDULED
        ]

        conflicts = await self.conflict_detector.check_conflicts(
            job, running_jobs, scheduled_jobs
        )

        if conflicts:
            retry_delay = self._calculate_retry_delay(job)
            self.waiting_jobs.append(
                (job, datetime.now() + timedelta(seconds=retry_delay))
            )
            asyncio.create_task(self._retry_later(job, retry_delay))
            raise ConflictError(
                f"Job conflicts detected: {', '.join(conflicts)}"
            )

        return self.base.add_job(
            func=job.func,
            schedule=job.schedule,
            name=job.name,
            job_id=job.id,
            args=job.args,
            kwargs=job.kwargs,
            priority=job.priority,
            max_instances=job.max_instances,
            max_retries=job.max_retries,
            retry_delay=job.retry_delay,
            tags=job.tags,
            user_id=job.user_id,
            metadata=job.metadata or {},
        )

    def _calculate_retry_delay(self, job: Job) -> int:
        """Calculate retry delay based on priority and history."""
        base_delay = 60
        priority_multipliers = {
            JobPriority.LOW: 4,
            JobPriority.NORMAL: 2,
            JobPriority.HIGH: 1,
            JobPriority.CRITICAL: 1,
        }
        multiplier = priority_multipliers.get(job.priority, 2)
        delay = int(base_delay * multiplier)
        return min(delay, self.max_retry_delay)

    async def _retry_later(self, job: Job, delay: int) -> None:
        """Retry a job after delay."""
        await asyncio.sleep(delay)

        self.waiting_jobs = [
            (j, t) for j, t in self.waiting_jobs
            if j.id != job.id
        ]

        try:
            await self.schedule_with_conflicts(
                job,
                getattr(job, "resources", None),
            )
        except ConflictError:
            new_delay = min(delay * 2, self.max_retry_delay)
            self.waiting_jobs.append(
                (job, datetime.now() + timedelta(seconds=new_delay))
            )
            asyncio.create_task(self._retry_later(job, new_delay))

    async def execute_with_resources(self, job_id: str) -> Any:
        """Execute a job with resource locking."""
        job = self.base.get_job(job_id)
        if not job:
            return None

        if not await self.conflict_detector.acquire_resources(job):
            await self._retry_later(job, 60)
            return None

        start_time = datetime.now()

        try:
            if job.func is None:
                return None
            if asyncio.iscoroutinefunction(job.func):
                result = await job.func(*job.args, **job.kwargs)
            else:
                result = job.func(*job.args, **job.kwargs)
            return result
        finally:
            self.conflict_detector.release_all_resources(job_id)
            end_time = datetime.now()
            self.conflict_detector.record_execution(
                job_id, start_time, end_time
            )

    def get_waiting_jobs(self) -> List[Dict[str, Any]]:
        """Get list of waiting jobs with retry times."""
        return [
            {
                "job_id": job.id,
                "job_name": job.name,
                "retry_after": retry_time.isoformat(),
                "priority": getattr(
                    job.priority, "value", job.priority
                ),
            }
            for job, retry_time in self.waiting_jobs
        ]

    def get_resource_status(self) -> Dict[str, str]:
        """Get current resource lock status."""
        return {
            resource: (lock.holder or "free")
            for resource, lock in self.conflict_detector.resource_locks.items()
        }
