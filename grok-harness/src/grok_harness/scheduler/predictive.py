"""Predictive analysis for job scheduling."""

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..core.grok_client import GrokClient
from ..utils.errors import PredictiveError
from .models import Job, JobResult, ScheduleType

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


@dataclass
class Prediction:
    """Prediction result for a job."""

    job_id: str
    estimated_duration: float
    confidence: float
    optimal_time: Optional[int] = None
    risk_level: str = "low"
    alternative_slots: List[int] = field(default_factory=list)


class PredictiveEngine:
    """
    Predictive analysis for job scheduling.

    Uses statistical analysis and Grok to predict:
    - Job durations
    - Optimal execution times
    - Failure probabilities
    - Resource contention
    """

    def __init__(self, grok_client: Optional[GrokClient] = None) -> None:
        self.grok = grok_client
        self.execution_history: List[Dict[str, Any]] = []
        self.predictions: Dict[str, Prediction] = {}

    def record_execution(self, job: Job, result: JobResult) -> None:
        """Record a job execution for prediction."""
        self.execution_history.append(
            {
                "job_id": job.id,
                "job_name": job.name,
                "duration": result.duration_ms / 1000,
                "success": result.success,
                "timestamp": result.start_time.isoformat(),
                "hour": result.start_time.hour,
                "day_of_week": result.start_time.weekday(),
                "tags": job.tags,
                "resources": getattr(job, "resources", []) or [],
            }
        )
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]

    def predict_duration(self, job: Job) -> Tuple[float, float]:
        """
        Predict job duration based on history.

        Returns:
            (estimated_duration_seconds, confidence)
        """
        job_history = [
            e
            for e in self.execution_history
            if e["job_id"] == job.id and e["success"]
        ]

        if len(job_history) < 3:
            return 60.0, 0.3

        durations = [e["duration"] for e in job_history]

        if NUMPY_AVAILABLE:
            q1, q3 = np.percentile(durations, [25, 75])
            iqr = q3 - q1
            filtered = [
                d
                for d in durations
                if q1 - 1.5 * iqr <= d <= q3 + 1.5 * iqr
            ]
        else:
            filtered = durations

        if not filtered:
            filtered = durations

        mean_duration = statistics.mean(filtered)
        std_duration = (
            statistics.stdev(filtered)
            if len(filtered) > 1
            else mean_duration * 0.3
        )

        confidence = min(
            0.9,
            len(job_history) / 100 + (1 - std_duration / mean_duration)
            if mean_duration > 0
            else 0.5,
        )

        return mean_duration, confidence

    def predict_optimal_time(self, job: Job) -> Optional[int]:
        """
        Predict optimal hour of day for this job.

        Returns:
            Hour (0-23) or None if insufficient data
        """
        success_history = [
            e
            for e in self.execution_history
            if e["job_id"] == job.id and e["success"]
        ]

        if len(success_history) < 5:
            return None

        by_hour: Dict[int, List[float]] = defaultdict(list)
        for e in success_history:
            by_hour[e["hour"]].append(e["duration"])

        best_hour = None
        best_avg = float("inf")

        for hour, durs in by_hour.items():
            if len(durs) >= 2:
                avg_duration = statistics.mean(durs)
                if avg_duration < best_avg:
                    best_avg = avg_duration
                    best_hour = hour

        return best_hour

    def predict_failure_probability(self, job: Job) -> float:
        """
        Predict probability of job failure.

        Returns:
            Probability between 0 and 1
        """
        all_executions = [
            e for e in self.execution_history if e["job_id"] == job.id
        ]

        if not all_executions:
            return 0.1

        failures = [e for e in all_executions if not e["success"]]
        base_rate = len(failures) / len(all_executions)

        current_hour = datetime.now().hour
        hour_failures = [e for e in failures if e["hour"] == current_hour]
        hour_total = [e for e in all_executions if e["hour"] == current_hour]

        if hour_total:
            hour_rate = len(hour_failures) / len(hour_total)
            weight = min(0.7, len(hour_total) / 20)
            return (1 - weight) * base_rate + weight * hour_rate

        return base_rate

    def predict_resource_contention(
        self,
        jobs: List[Job],
        time_window_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Predict resource contention between jobs.

        Args:
            jobs: List of jobs to analyze
            time_window_minutes: Look ahead window

        Returns:
            List of predicted contentions
        """
        contentions: List[Dict[str, Any]] = []
        resource_jobs: Dict[str, List[Job]] = defaultdict(list)

        for job in jobs:
            resources = getattr(job, "resources", None) or []
            for resource in resources:
                resource_jobs[resource].append(job)

        for resource, res_jobs in resource_jobs.items():
            if len(res_jobs) < 2:
                continue

            for i, job1 in enumerate(res_jobs):
                for job2 in res_jobs[i + 1 :]:
                    dur1, _ = self.predict_duration(job1)
                    dur2, _ = self.predict_duration(job2)

                    if self._would_overlap(job1, job2, dur1, dur2):
                        contentions.append(
                            {
                                "resource": resource,
                                "job1": job1.id,
                                "job2": job2.id,
                                "severity": (
                                    "high"
                                    if dur1 > 300 or dur2 > 300
                                    else "medium"
                                ),
                            }
                        )

        return contentions

    def _would_overlap(
        self,
        job1: Job,
        job2: Job,
        dur1: float,
        dur2: float,
    ) -> bool:
        """Check if two jobs might overlap in execution."""
        if not job1.schedule or not job2.schedule:
            return False
        return True

    async def analyze_with_grok(self, jobs: List[Job]) -> Dict[str, Any]:
        """
        Use Grok for advanced predictive analysis.

        Args:
            jobs: List of jobs to analyze

        Returns:
            Grok's analysis and recommendations
        """
        if not self.grok:
            raise PredictiveError(
                "Grok client required for advanced analysis"
            )

        job_summaries = []
        for job in jobs:
            duration, conf = self.predict_duration(job)
            failure_prob = self.predict_failure_probability(job)
            optimal_time = self.predict_optimal_time(job)

            job_summaries.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "estimated_duration": duration,
                    "duration_confidence": conf,
                    "failure_probability": failure_prob,
                    "optimal_hour": optimal_time,
                    "schedule": (
                        job.schedule.to_dict()
                        if job.schedule
                        else None
                    ),
                    "tags": job.tags,
                }
            )

        contentions = self.predict_resource_contention(jobs)

        prompt = f"""
Analyze these jobs and provide predictive recommendations:

Jobs:
{json.dumps(job_summaries, indent=2)}

Predicted Contentions:
{json.dumps(contentions, indent=2)}

Please provide JSON with sections:
- load_predictions: dict of time slots and expected load
- schedule_adjustments: list of recommended changes
- risk_assessment: dict of job_id -> risk level
- optimizations: list of suggestions
- capacity_recommendations: list of recommendations
"""

        try:
            response = await self.grok.chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a predictive scheduler AI. "
                            "Analyze jobs and provide JSON recommendations."
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

            return json.loads(content.strip())

        except Exception as e:
            raise PredictiveError(f"Grok analysis failed: {e}") from e

    def get_predictions(self, job_id: str) -> Optional[Prediction]:
        """Get predictions for a specific job."""
        return self.predictions.get(job_id)

    def update_predictions(self, job: Job) -> None:
        """Update predictions for a job."""
        duration, conf = self.predict_duration(job)
        optimal_time = self.predict_optimal_time(job)
        failure_prob = self.predict_failure_probability(job)

        if failure_prob > 0.3:
            risk = "high"
        elif failure_prob > 0.15:
            risk = "medium"
        else:
            risk = "low"

        self.predictions[job.id] = Prediction(
            job_id=job.id,
            estimated_duration=duration,
            confidence=conf,
            optimal_time=optimal_time,
            risk_level=risk,
        )


class LoadPredictor:
    """Predicts system load over time."""

    def __init__(self, predictive_engine: PredictiveEngine) -> None:
        self.engine = predictive_engine

    def predict_load(
        self,
        jobs: List[Job],
        hours_ahead: int = 24,
    ) -> Dict[int, float]:
        """
        Predict system load for each hour.

        Returns:
            Dict of hour -> expected load (0-1)
        """
        hourly_load: Dict[int, float] = defaultdict(float)

        for job in jobs:
            if not job.schedule:
                continue

            pred = self.engine.get_predictions(job.id)
            if not pred:
                self.engine.update_predictions(job)
                pred = self.engine.get_predictions(job.id)

            if not pred:
                continue

            for hour in range(hours_ahead):
                prob = self._execution_probability(job, hour)
                hourly_load[hour] += (
                    prob * (pred.estimated_duration / 3600)
                )

        max_load = max(hourly_load.values()) if hourly_load else 1
        if max_load > 0:
            hourly_load = {
                h: load / max_load
                for h, load in hourly_load.items()
            }

        return dict(hourly_load)

    def _execution_probability(self, job: Job, hour: int) -> float:
        """Calculate probability job runs in given hour."""
        if job.schedule:
            st = job.schedule.type
            if st == ScheduleType.INTERVAL:
                try:
                    interval = int(job.schedule.value)
                    if interval <= 3600:
                        return 0.5
                except (ValueError, TypeError):
                    pass
            elif st == ScheduleType.CRON:
                parts = job.schedule.value.split()
                if len(parts) >= 2 and parts[0] == "*" and parts[1] == "*":
                    return 0.5
        return 0.1
