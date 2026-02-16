"""Smart scheduler with predictive, adaptive, and monitoring capabilities."""

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.grok_client import GrokClient
from .conflict import ConflictAwareScheduler
from .core import Scheduler as BaseScheduler
from .learning import AdaptiveScheduler, PatternLearner
from .models import (
    Job,
    JobPriority,
    JobResult,
    JobStatus,
    Schedule,
)
from .monitoring import JobMonitor
from .predictive import LoadPredictor, PredictiveEngine
from .queue import PriorityJobQueue


class SmartScheduler:
    """
    Intelligent scheduler with predictive, adaptive, and monitoring.

    Combines:
    - Base scheduling (APScheduler)
    - Conflict detection and resolution
    - Pattern learning (Grok)
    - Predictive analysis
    - Job monitoring and alerts
    - Priority queueing
    """

    def __init__(
        self,
        grok_client: Optional[GrokClient] = None,
        storage_path: Optional[Path] = None,
        max_concurrent: int = 10,
        enable_learning: bool = True,
        enable_predictive: bool = True,
        enable_monitoring: bool = True,
    ) -> None:
        self.grok = grok_client
        self.storage_path = (
            storage_path or Path.home() / ".grok-harness" / "scheduler"
        )
        self.storage_path = Path(self.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.base_scheduler = BaseScheduler(
            storage_path=self.storage_path / "base",
            max_concurrent=max_concurrent,
        )

        self.conflict_scheduler = ConflictAwareScheduler(self.base_scheduler)

        if enable_learning and grok_client:
            self.learner = PatternLearner(grok_client)
            self.adaptive = AdaptiveScheduler(
                self.base_scheduler,
                grok_client,
                self.conflict_scheduler,
            )
        else:
            self.learner = None
            self.adaptive = None

        if enable_predictive:
            self.predictive = PredictiveEngine(grok_client)
            self.load_predictor = LoadPredictor(self.predictive)
        else:
            self.predictive = None
            self.load_predictor = None

        if enable_monitoring:
            self.monitor = JobMonitor(self.storage_path / "monitoring")
        else:
            self.monitor = None

        self.queue = PriorityJobQueue()

        self.stats: Dict[str, int] = {
            "jobs_scheduled": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "predictions_made": 0,
            "alerts_triggered": 0,
            "adaptations_applied": 0,
        }

        self._background_tasks: List[asyncio.Task[Any]] = []
        self._running = False

    async def start(self) -> None:
        """Start all scheduler components."""
        self.base_scheduler.start()

        def _on_complete(job_id: str, success: bool = True) -> None:
            job = self.base_scheduler.get_job(job_id)
            if job and (self.predictive or self.learner):
                results = self.base_scheduler.get_recent_results(
                    job_id=job_id, limit=1
                )
                if results:
                    r = results[0]
                    if self.predictive:
                        self.predictive.record_execution(
                            job,
                            JobResult(
                                job_id=r.job_id,
                                success=r.success,
                                start_time=r.start_time,
                                end_time=r.end_time,
                                duration_ms=r.duration_ms,
                                error=r.error,
                            ),
                        )
                    if self.learner:
                        self.learner.record_execution(
                            job,
                            r.success,
                            r.duration_ms / 1000,
                        )

        def _on_error(job_id: str, error: str = "") -> None:
            job = self.base_scheduler.get_job(job_id)
            if job and (self.predictive or self.learner):
                results = self.base_scheduler.get_recent_results(
                    job_id=job_id, limit=1
                )
                if results:
                    r = results[0]
                    if self.predictive:
                        self.predictive.record_execution(job, r)
                    if self.learner:
                        self.learner.record_execution(
                            job, False, r.duration_ms / 1000
                        )

        self.base_scheduler._event_handlers["job_complete"].append(
            _on_complete
        )
        self.base_scheduler._event_handlers["job_error"].append(_on_error)

        self._running = True
        self._background_tasks = [
            asyncio.create_task(self._process_queue()),
            asyncio.create_task(self._periodic_analysis()),
            asyncio.create_task(self._health_check()),
        ]

    async def stop(self) -> None:
        """Stop all scheduler components."""
        self._running = False

        for task in self._background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.base_scheduler.stop()

    async def schedule(
        self,
        func: Callable[..., Any],
        schedule: str,
        name: Optional[str] = None,
        job_id: Optional[str] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        priority: JobPriority = JobPriority.NORMAL,
        resources: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        adaptive: bool = True,
    ) -> Job:
        """
        Schedule a job with optimizations.

        Args:
            func: Function to execute
            schedule: Cron or interval string
            name: Job name
            job_id: Optional custom ID
            args: Positional arguments
            kwargs: Keyword arguments
            priority: Job priority
            resources: Required resources
            tags: Tags for grouping
            user_id: Owner
            metadata: Additional data
            adaptive: Whether to apply adaptive scheduling

        Returns:
            Created job
        """
        schedule_obj = (
            Schedule.from_cron(schedule)
            if " " in schedule
            else Schedule.from_interval(schedule)
        )

        job = Job(
            id=job_id or str(uuid.uuid4()),
            name=name or getattr(func, "__name__", "job"),
            func=func,
            args=args or [],
            kwargs=kwargs or {},
            schedule=schedule_obj,
            priority=priority,
            tags=tags or [],
            user_id=user_id,
            metadata=metadata or {},
        )

        if resources:
            job.resources = resources

        if adaptive and self.adaptive:
            job = await self.adaptive.schedule_adaptive(job, resources)
        else:
            job = await self.conflict_scheduler.schedule_with_conflicts(
                job, resources
            )

        if self.predictive:
            self.predictive.update_predictions(job)
            self.stats["predictions_made"] += 1

        self.stats["jobs_scheduled"] += 1
        return job

    async def run_now(
        self,
        func: Callable[..., Any],
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        priority: JobPriority = JobPriority.HIGH,
        resources: Optional[List[str]] = None,
        delay: Optional[float] = None,
    ) -> JobResult:
        """
        Run a job immediately or with delay.

        Args:
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            priority: Job priority
            resources: Required resources
            delay: Delay in seconds

        Returns:
            Job result
        """
        job = Job(
            name=f"run_now_{getattr(func, '__name__', 'job')}",
            func=func,
            args=args or [],
            kwargs=kwargs or {},
            priority=priority,
        )

        if resources:
            job.resources = resources

        if delay is not None:
            await self.queue.put(job, delay)
            return JobResult(
                job_id=job.id,
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_ms=0,
                error="Job queued with delay",
            )

        if resources:
            try:
                acquired = await self.conflict_scheduler.conflict_detector.acquire_resources(
                    job
                )
                if not acquired:
                    await self.queue.put(job)
                    return JobResult(
                        job_id=job.id,
                        success=False,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        duration_ms=0,
                        error="Resources busy, queued",
                    )
            except Exception as e:
                await self.queue.put(job)
                return JobResult(
                    job_id=job.id,
                    success=False,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_ms=0,
                    error=f"Resources busy, queued: {e}",
                )

        start = datetime.now()
        success = True
        error = None
        result = None

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*job.args, **job.kwargs)
            else:
                result = func(*job.args, **job.kwargs)
        except Exception as e:
            success = False
            error = str(e)
            result = None
        finally:
            if resources:
                self.conflict_scheduler.conflict_detector.release_all_resources(
                    job.id
                )

        end = datetime.now()
        duration_ms = (end - start).total_seconds() * 1000

        job_result = JobResult(
            job_id=job.id,
            success=success,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            error=error,
            result=result,
        )

        if self.learner:
            self.learner.record_execution(job, success, duration_ms / 1000)
        if self.predictive:
            self.predictive.record_execution(job, job_result)

        self.stats["jobs_completed" if success else "jobs_failed"] += 1
        return job_result

    async def _process_queue(self) -> None:
        """Background task to process the priority queue."""
        while self._running:
            try:
                job = await self.queue.get(timeout=5.0)
                if job:
                    asyncio.create_task(
                        self.run_now(
                            job.func,
                            job.args,
                            job.kwargs,
                            job.priority,
                            getattr(job, "resources", None),
                        )
                    )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                await asyncio.sleep(1)

    async def _periodic_analysis(self) -> None:
        """Background task for periodic analysis."""
        while self._running:
            try:
                await asyncio.sleep(3600)

                if self.adaptive:
                    await self.adaptive.analyze_and_adapt()
                    self.stats["adaptations_applied"] += 1

                if self.predictive and self.load_predictor:
                    for job in list(self.base_scheduler.jobs.values()):
                        self.predictive.update_predictions(job)

                    jobs = list(self.base_scheduler.jobs.values())
                    load = self.load_predictor.predict_load(jobs)

                    load_file = self.storage_path / "load_predictions.json"
                    with open(load_file, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "predictions": load,
                            },
                            f,
                        )
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _health_check(self) -> None:
        """Background task for health monitoring."""
        while self._running:
            try:
                await asyncio.sleep(300)

                if not self.monitor:
                    continue

                recent_results = self.base_scheduler.get_recent_results(
                    limit=100
                )
                all_results = self.base_scheduler.get_recent_results(
                    limit=1000
                )

                for job in list(self.base_scheduler.jobs.values()):
                    alerts = await self.monitor.check_job(
                        job,
                        recent_results,
                        all_results,
                    )
                    if alerts:
                        self.stats["alerts_triggered"] += len(alerts)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self.base_scheduler.get_job(job_id)

    def get_jobs(self, **kwargs: Any) -> List[Job]:
        """Get jobs with filtering."""
        return self.base_scheduler.get_jobs(**kwargs)

    async def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        return await self.base_scheduler.pause_job(job_id)

    async def resume_job(self, job_id: str) -> bool:
        """Resume a job."""
        return await self.base_scheduler.resume_job(job_id)

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job."""
        return await self.base_scheduler.remove_job(job_id)

    def get_job_stats(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job statistics with predictions."""
        stats = self.base_scheduler.get_job_stats(job_id)
        if stats is None:
            return None

        out: Dict[str, Any] = {
            "job_id": stats.job_id,
            "total_runs": stats.total_runs,
            "successful_runs": stats.successful_runs,
            "failed_runs": stats.failed_runs,
            "avg_duration_ms": stats.avg_duration_ms,
            "last_run": (
                stats.last_run.isoformat() if stats.last_run else None
            ),
            "next_run": (
                stats.next_run.isoformat() if stats.next_run else None
            ),
            "success_rate": stats.success_rate,
        }

        if self.predictive:
            pred = self.predictive.get_predictions(job_id)
            if pred:
                out["predictions"] = {
                    "job_id": pred.job_id,
                    "estimated_duration": pred.estimated_duration,
                    "confidence": pred.confidence,
                    "optimal_time": pred.optimal_time,
                    "risk_level": pred.risk_level,
                    "alternative_slots": pred.alternative_slots,
                }
        return out

    def get_recent_results(
        self,
        job_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[JobResult]:
        """Get recent job results."""
        return self.base_scheduler.get_recent_results(job_id, limit)

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return await self.queue.get_stats()

    async def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health."""
        jobs = list(self.base_scheduler.jobs.values())

        status_counts: Dict[str, int] = defaultdict(int)
        for job in jobs:
            status_counts[job.status.value] += 1

        job_health: Dict[str, Any] = {}
        if self.monitor:
            recent = self.base_scheduler.get_recent_results(limit=1000)
            for job in jobs:
                job_health[job.id] = self.monitor.get_job_health(
                    job, recent
                )

        queue_size = await self.queue.size()

        return {
            "status": "running" if self._running else "stopped",
            "total_jobs": len(jobs),
            "job_status": dict(status_counts),
            "job_health": job_health,
            "stats": dict(self.stats),
            "queue_size": queue_size,
            "timestamp": datetime.now().isoformat(),
        }

    async def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report."""
        report: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "system_health": await self.get_system_health(),
            "queue_stats": await self.get_queue_stats(),
        }

        if self.adaptive:
            report["adaptive"] = await self.adaptive.get_optimization_report()

        if self.predictive and self.load_predictor:
            jobs = list(self.base_scheduler.jobs.values())
            report["load_predictions"] = self.load_predictor.predict_load(
                jobs
            )

        if self.monitor:
            report["alert_history"] = self.monitor.get_alert_history(
                limit=10
            )

        return report

    async def cleanup(self) -> None:
        """Clean up old data."""
        await self.base_scheduler.cleanup()

        if self.predictive:
            valid_ids = set(self.base_scheduler.jobs)
            self.predictive.predictions = {
                k: v
                for k, v in self.predictive.predictions.items()
                if k in valid_ids
            }

        state_file = self.storage_path / "smart_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "stats": self.stats,
                    "timestamp": datetime.now().isoformat(),
                },
                f,
            )
