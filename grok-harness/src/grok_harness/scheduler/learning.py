"""Grok pattern learning for scheduler optimization."""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import statistics

from ..core.grok_client import GrokClient
from ..utils.errors import LearningError
from .models import Job, Schedule, ScheduleType


class PatternLearner:
    """
    Learns from job execution patterns using Grok.

    Identifies:
    - Optimal execution times
    - Resource usage patterns
    - Conflict probabilities
    - Performance trends
    """

    def __init__(self, grok_client: GrokClient) -> None:
        self.grok = grok_client
        self.execution_history: List[Dict[str, Any]] = []
        self.learned_patterns: Dict[str, Any] = {}
        self.last_analysis: Optional[datetime] = None

    def record_execution(
        self,
        job: Job,
        success: bool,
        duration: float,
    ) -> None:
        """Record a job execution for learning."""
        self.execution_history.append(
            {
                "job_id": job.id,
                "job_name": job.name,
                "success": success,
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
                "day_of_week": datetime.now().weekday(),
                "hour_of_day": datetime.now().hour,
                "tags": job.tags,
            }
        )
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]

    async def analyze_patterns(
        self,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyze execution patterns using Grok.

        Returns:
            Dictionary of learned patterns and recommendations
        """
        if not force and self.last_analysis:
            if datetime.now() - self.last_analysis < timedelta(hours=1):
                return self.learned_patterns

        if len(self.execution_history) < 10:
            return {}

        analysis_data = self._prepare_analysis_data()

        prompt = f"""
Analyze these job execution patterns and provide recommendations:

{json.dumps(analysis_data, indent=2)}

Please provide:
1. Optimal times for each job based on success rates
2. Patterns in failures (time of day, day of week)
3. Resource contention predictions
4. Recommended schedule adjustments
5. Performance trends

Return as JSON with sections:
- optimal_times: dict of job_id -> recommended hour
- risk_periods: list of high-risk time windows
- conflict_predictions: list of potential conflicts
- schedule_adjustments: list of recommended changes
- trends: performance trends over time
"""

        try:
            response = await self.grok.chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a scheduler optimization AI. "
                            "Analyze patterns and provide JSON recommendations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            content = response["choices"][0]["message"]["content"]

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            patterns = json.loads(content.strip())
            self.learned_patterns = patterns
            self.last_analysis = datetime.now()

            return patterns

        except Exception as e:
            raise LearningError(f"Failed to analyze patterns: {e}") from e

    def _prepare_analysis_data(self) -> Dict[str, Any]:
        """Prepare execution data for analysis."""
        by_job: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for exec_item in self.execution_history:
            by_job[exec_item["job_id"]].append(exec_item)

        job_stats: Dict[str, Any] = {}
        for job_id, executions in by_job.items():
            success_rate = sum(
                1 for e in executions if e["success"]
            ) / len(executions)
            avg_duration = statistics.mean(
                e["duration"] for e in executions
            )

            by_hour: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
            for e in executions:
                by_hour[e["hour_of_day"]].append(e)

            hour_success = {
                hour: sum(1 for e in exes if e["success"]) / len(exes)
                for hour, exes in by_hour.items()
            }

            job_stats[job_id] = {
                "name": executions[0]["job_name"],
                "total_runs": len(executions),
                "success_rate": success_rate,
                "avg_duration": avg_duration,
                "success_by_hour": hour_success,
                "tags": executions[0]["tags"],
            }

        all_failures = [
            e for e in self.execution_history
            if not e["success"]
        ]

        return {
            "total_executions": len(self.execution_history),
            "time_span_days": self._get_time_span(),
            "job_statistics": job_stats,
            "failure_analysis": {
                "total_failures": len(all_failures),
                "failure_by_hour": self._count_by_hour(all_failures),
                "failure_by_day": self._count_by_day(all_failures),
            },
        }

    def _get_time_span(self) -> float:
        """Get time span of history in days."""
        if not self.execution_history:
            return 0.0
        first = datetime.fromisoformat(
            self.execution_history[0]["timestamp"]
        )
        last = datetime.fromisoformat(
            self.execution_history[-1]["timestamp"]
        )
        return (last - first).total_seconds() / 86400

    def _count_by_hour(
        self,
        executions: List[Dict[str, Any]],
    ) -> Dict[int, int]:
        """Count executions by hour."""
        counts: Dict[int, int] = defaultdict(int)
        for e in executions:
            counts[e["hour_of_day"]] += 1
        return dict(counts)

    def _count_by_day(
        self,
        executions: List[Dict[str, Any]],
    ) -> Dict[int, int]:
        """Count executions by day of week."""
        counts: Dict[int, int] = defaultdict(int)
        for e in executions:
            counts[e["day_of_week"]] += 1
        return dict(counts)

    async def suggest_optimal_schedule(
        self,
        job: Job,
    ) -> Optional[Schedule]:
        """
        Suggest optimal schedule for a job based on learned patterns.

        Args:
            job: Job to optimize

        Returns:
            Suggested schedule or None if no data
        """
        patterns = self.learned_patterns.get("optimal_times", {})
        if job.id not in patterns:
            return None

        optimal_hour = patterns[job.id]
        if isinstance(optimal_hour, dict):
            optimal_hour = optimal_hour.get("hour", 0)

        return Schedule(
            type=ScheduleType.CRON,
            value=f"0 {int(optimal_hour)} * * *",
            timezone="UTC",
        )

    def get_risk_periods(self) -> List[Dict[str, Any]]:
        """Get high-risk time periods."""
        return self.learned_patterns.get("risk_periods", [])

    def get_conflict_predictions(self) -> List[Dict[str, Any]]:
        """Get predicted conflicts between jobs."""
        return self.learned_patterns.get("conflict_predictions", [])

    def get_trends(self) -> Dict[str, Any]:
        """Get performance trends."""
        return self.learned_patterns.get("trends", {})


class AdaptiveScheduler:
    """
    Scheduler that adapts based on learned patterns.

    Combines conflict-aware scheduling with Grok learning
    to optimize job execution over time.
    """

    def __init__(
        self,
        base_scheduler: Any,
        grok_client: GrokClient,
        conflict_scheduler: Any,
    ) -> None:
        self.base = base_scheduler
        self.grok = grok_client
        self.conflict = conflict_scheduler
        self.learner = PatternLearner(grok_client)
        self.adaptation_enabled = True

    async def schedule_adaptive(
        self,
        job: Job,
        resources: Optional[List[str]] = None,
    ) -> Any:
        """Schedule a job with adaptive optimization."""
        if self.adaptation_enabled:
            optimal = await self.learner.suggest_optimal_schedule(job)
            if optimal is not None:
                job.schedule = optimal

        return await self.conflict.schedule_with_conflicts(
            job,
            resources,
        )

    def record_execution(
        self,
        job: Job,
        success: bool,
        duration: float,
    ) -> None:
        """Record execution for learning."""
        self.learner.record_execution(job, success, duration)

    async def analyze_and_adapt(self, force: bool = False) -> None:
        """Analyze patterns and adapt schedules."""
        patterns = await self.learner.analyze_patterns(force)

        if not patterns:
            return

        adjustments = patterns.get("schedule_adjustments", [])
        for adj in adjustments:
            await self._apply_adjustment(adj)

        conflicts = patterns.get("conflict_predictions", [])
        for conflict in conflicts:
            self._register_conflict(conflict)

    async def _apply_adjustment(self, adjustment: Dict[str, Any]) -> None:
        """Apply a schedule adjustment."""
        job_id = adjustment.get("job_id")
        if not job_id:
            return

        job = self.base.get_job(job_id)
        if not job:
            return

        new_schedule = adjustment.get("schedule")
        if new_schedule and isinstance(new_schedule, dict):
            job.schedule = Schedule.from_dict(new_schedule)
            await self.base.pause_job(job_id)
            await self.base.resume_job(job_id)

    def _register_conflict(self, conflict: Dict[str, Any]) -> None:
        """Register a predicted conflict."""
        job1 = conflict.get("job1")
        job2 = conflict.get("job2")
        if job1 and job2:
            self.conflict.conflict_detector.add_conflict(job1, job2)

    async def get_optimization_report(self) -> Dict[str, Any]:
        """Get optimization report."""
        return {
            "patterns": self.learner.learned_patterns,
            "waiting_jobs": self.conflict.get_waiting_jobs(),
            "resource_status": self.conflict.get_resource_status(),
            "adaptation_enabled": self.adaptation_enabled,
            "last_analysis": (
                self.learner.last_analysis.isoformat()
                if self.learner.last_analysis
                else None
            ),
        }
