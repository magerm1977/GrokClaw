"""Core scheduler implementation."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
)
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..memory.unified import UnifiedMemory
from .models import (
    Job,
    JobResult,
    JobStats,
    JobStatus,
    Schedule,
    ScheduleType,
)


class Scheduler:
    """
    Core scheduler for managing and executing jobs.

    Built on APScheduler with:
    - Job persistence
    - Priority queues
    - Conflict prevention
    - Statistics tracking
    """

    def __init__(
        self,
        memory: Optional[UnifiedMemory] = None,
        storage_path: Optional[Path] = None,
        max_concurrent: int = 10,
        timezone: str = "UTC",
    ) -> None:
        self.memory = memory
        self.storage_path = (
            storage_path or Path.home() / ".grok-harness" / "scheduler"
        )
        self.storage_path = Path(self.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.max_concurrent = max_concurrent
        self.timezone = timezone
        self._running = False
        self._scheduler: Optional[AsyncIOScheduler] = None

        self.jobs: Dict[str, Job] = {}
        self.active_jobs: Dict[str, int] = {}
        self.job_locks: Dict[str, asyncio.Lock] = {}
        self.job_results: List[JobResult] = []
        self.max_results_kept = 1000

        self._event_handlers: Dict[str, List[Callable[..., Any]]] = {
            "job_start": [],
            "job_complete": [],
            "job_error": [],
            "job_missed": [],
        }

        self._load_jobs()

    def _load_jobs(self) -> None:
        """Load jobs from storage."""
        jobs_file = self.storage_path / "jobs.json"
        if jobs_file.exists():
            try:
                with open(jobs_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for job_data in data:
                        job = Job.from_dict(job_data)
                        self.jobs[job.id] = job
            except Exception:
                pass

    def _save_jobs(self) -> None:
        """Save jobs to storage."""
        jobs_file = self.storage_path / "jobs.json"
        try:
            with open(jobs_file, "w", encoding="utf-8") as f:
                data = [job.to_dict() for job in self.jobs.values()]
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {
            "coalesce": True,
            "max_instances": self.max_concurrent,
            "misfire_grace_time": 60,
        }

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.timezone,
        )

        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED
            | EVENT_JOB_ERROR
            | EVENT_JOB_MISSED
            | EVENT_JOB_SUBMITTED
            | EVENT_JOB_MAX_INSTANCES,
        )

        for job in self.jobs.values():
            if (
                job.status == JobStatus.SCHEDULED
                and job.schedule
                and job.func is not None
            ):
                self._schedule_job_in_apscheduler(job)

        self._scheduler.start()
        self._running = True

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown()
        self._scheduler = None
        self._running = False

    def _on_job_event(self, event: Any) -> None:
        """Handle APScheduler events."""
        job_id = getattr(event, "job_id", None)
        if job_id is None:
            return

        if event.code == EVENT_JOB_SUBMITTED:
            for h in self._event_handlers.get("job_start", []):
                try:
                    h(job_id)
                except Exception:
                    pass
        elif event.code == EVENT_JOB_EXECUTED:
            for h in self._event_handlers.get("job_complete", []):
                try:
                    h(job_id, success=True)
                except Exception:
                    pass
        elif event.code == EVENT_JOB_ERROR:
            err = str(getattr(event, "exception", ""))
            for h in self._event_handlers.get("job_error", []):
                try:
                    h(job_id, error=err)
                except Exception:
                    pass
        elif event.code == EVENT_JOB_MISSED:
            for h in self._event_handlers.get("job_missed", []):
                try:
                    h(job_id)
                except Exception:
                    pass

    def on(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Register event handler."""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].append(handler)

    def add_job(
        self,
        func: Callable[..., Any],
        schedule: Union[str, Schedule, Dict[str, Any]],
        name: Optional[str] = None,
        job_id: Optional[str] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        priority: Any = 1,
        max_instances: int = 1,
        max_retries: int = 3,
        retry_delay: int = 60,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Job:
        """Add a job to the scheduler."""
        from .models import JobPriority

        if isinstance(schedule, str):
            if " " in schedule and len(schedule.split()) >= 5:
                schedule_obj = Schedule(type=ScheduleType.CRON, value=schedule)
            else:
                schedule_obj = Schedule(
                    type=ScheduleType.INTERVAL, value=schedule
                )
        elif isinstance(schedule, dict):
            schedule_obj = Schedule.from_dict(schedule)
        else:
            schedule_obj = schedule

        if isinstance(priority, JobPriority):
            priority_enum = priority
        elif isinstance(priority, int):
            priority_enum = JobPriority(priority)
        else:
            priority_enum = JobPriority.NORMAL

        job = Job(
            id=job_id or str(uuid.uuid4()),
            name=name or getattr(func, "__name__", "unknown"),
            func=func,
            args=args or [],
            kwargs=kwargs or {},
            schedule=schedule_obj,
            priority=priority_enum,
            max_instances=max_instances,
            max_retries=max_retries,
            retry_delay=retry_delay,
            status=JobStatus.SCHEDULED,
            tags=tags or [],
            user_id=user_id,
            metadata=metadata or {},
        )

        self.jobs[job.id] = job
        self._save_jobs()

        if self._running and job.func is not None:
            self._schedule_job_in_apscheduler(job)

        return job

    def _schedule_job_in_apscheduler(self, job: Job) -> None:
        """Schedule a job in APScheduler."""
        if not self._scheduler or not job.schedule:
            return

        st = job.schedule.type
        if st == ScheduleType.ONCE:
            return

        trigger = None
        if st == ScheduleType.CRON:
            trigger = CronTrigger.from_crontab(
                job.schedule.value,
                timezone=job.schedule.timezone or self.timezone,
            )
        elif st == ScheduleType.INTERVAL:
            trigger = IntervalTrigger(
                seconds=int(job.schedule.value),
                timezone=job.schedule.timezone or self.timezone,
            )
        elif st == ScheduleType.DATE:
            run_date = datetime.fromisoformat(job.schedule.value)
            trigger = DateTrigger(run_date=run_date)

        if trigger is None:
            return

        async def job_wrapper() -> None:
            await self._execute_job(job.id)

        try:
            self._scheduler.add_job(
                job_wrapper,
                trigger=trigger,
                id=job.id,
                name=job.name,
                replace_existing=True,
                misfire_grace_time=60,
            )
            aps_job = self._scheduler.get_job(job.id)
            if aps_job and aps_job.next_run_time:
                job.next_run = aps_job.next_run_time
        except Exception:
            pass

    async def _execute_job(
        self,
        job_id: str,
        retry_count: int = 0,
    ) -> None:
        """Execute a job with conflict prevention."""
        if job_id not in self.jobs:
            return

        job = self.jobs[job_id]
        if job.func is None:
            return

        current = self.active_jobs.get(job_id, 0)
        if current >= job.max_instances:
            await asyncio.sleep(60)
            return

        if job_id not in self.job_locks:
            self.job_locks[job_id] = asyncio.Lock()

        async with self.job_locks[job_id]:
            self.active_jobs[job_id] = current + 1

            start_time = datetime.now()
            success = False
            error = None
            result = None

            try:
                job.status = JobStatus.RUNNING
                job.last_run = start_time
                job.total_runs += 1

                if asyncio.iscoroutinefunction(job.func):
                    result = await job.func(*job.args, **job.kwargs)
                else:
                    result = job.func(*job.args, **job.kwargs)

                success = True
                job.successful_runs += 1
                job.status = JobStatus.SCHEDULED
                for h in self._event_handlers.get("job_complete", []):
                    try:
                        h(job_id, success=True)
                    except Exception:
                        pass
            except Exception as e:
                error = str(e)
                job.failed_runs += 1
                for h in self._event_handlers.get("job_error", []):
                    try:
                        h(job_id, error=error)
                    except Exception:
                        pass

                if retry_count < job.max_retries:
                    job.status = JobStatus.RETRYING
                    await asyncio.sleep(job.retry_delay)
                    asyncio.create_task(
                        self._execute_job(job_id, retry_count + 1)
                    )
                else:
                    job.status = JobStatus.FAILED
            finally:
                self.active_jobs[job_id] = current
                if self.active_jobs[job_id] <= 0:
                    del self.active_jobs[job_id]

                end_time = datetime.now()
                result_obj = JobResult(
                    job_id=job_id,
                    success=success,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=(
                        end_time - start_time
                    ).total_seconds()
                    * 1000,
                    error=error,
                    result=result if success else None,
                    retry_count=retry_count,
                )
                self.job_results.append(result_obj)

                if len(self.job_results) > self.max_results_kept:
                    self.job_results = self.job_results[
                        -self.max_results_kept :
                    ]

                job.updated_at = datetime.now()
                self._save_jobs()

    async def run_once(
        self,
        func: Callable[..., Any],
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        delay: Optional[float] = None,
        job_id: Optional[str] = None,
    ) -> JobResult:
        """Run a job once immediately or after delay."""
        from .models import JobPriority

        if delay is not None:
            run_date = datetime.now() + timedelta(seconds=delay)
            schedule = Schedule(
                type=ScheduleType.DATE,
                value=run_date.isoformat(),
            )
        else:
            schedule = Schedule(type=ScheduleType.ONCE, value="now")

        job = self.add_job(
            func=func,
            schedule=schedule,
            name=f"run_once_{getattr(func, '__name__', 'job')}",
            job_id=job_id,
            args=args,
            kwargs=kwargs,
            max_instances=1,
            priority=JobPriority.NORMAL,
        )

        if delay is None:
            await self._execute_job(job.id)
            for r in reversed(self.job_results):
                if r.job_id == job.id:
                    return r

        return JobResult(
            job_id=job.id,
            success=False,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=0,
            error="Job scheduled with delay",
        )

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self.jobs.get(job_id)

    def get_jobs(
        self,
        status: Optional[JobStatus] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Job]:
        """Get jobs with filtering."""
        jobs = list(self.jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if user_id is not None:
            jobs = [j for j in jobs if j.user_id == user_id]
        if tags is not None:
            jobs = [
                j
                for j in jobs
                if any(t in j.tags for t in tags)
            ]
        return jobs[:limit]

    async def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        if job_id not in self.jobs:
            return False
        job = self.jobs[job_id]
        job.status = JobStatus.PAUSED
        if self._scheduler:
            try:
                self._scheduler.pause_job(job_id)
            except Exception:
                pass
        self._save_jobs()
        return True

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        if job_id not in self.jobs:
            return False
        job = self.jobs[job_id]
        job.status = JobStatus.SCHEDULED
        if self._scheduler:
            try:
                self._scheduler.resume_job(job_id)
            except Exception:
                pass
        self._save_jobs()
        return True

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job."""
        if job_id not in self.jobs:
            return False
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        del self.jobs[job_id]
        self._save_jobs()
        return True

    def get_job_stats(self, job_id: str) -> Optional[JobStats]:
        """Get statistics for a job."""
        job = self.jobs.get(job_id)
        if not job:
            return None
        return JobStats.from_job(job)

    def get_recent_results(
        self,
        job_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[JobResult]:
        """Get recent job results."""
        results = self.job_results
        if job_id is not None:
            results = [r for r in results if r.job_id == job_id]
        return list(reversed(results[-limit:]))

    async def cleanup(self) -> None:
        """Clean up old results and reset stuck jobs."""
        cutoff = datetime.now() - timedelta(days=7)
        self.job_results = [
            r for r in self.job_results
            if r.start_time > cutoff
        ]
        for job in self.jobs.values():
            if job.status == JobStatus.RUNNING and job.last_run:
                if (
                    datetime.now() - job.last_run
                    > timedelta(hours=1)
                ):
                    job.status = JobStatus.FAILED
                    job.failed_runs += 1
        self._save_jobs()
