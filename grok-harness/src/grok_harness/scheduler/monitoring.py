"""Job monitoring and alerts."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import Job, JobResult, JobStatus


class Alert:
    """Alert definition."""

    def __init__(
        self,
        name: str,
        condition: Callable[[Job, List[JobResult]], bool],
        message: str,
        severity: str = "warning",
    ) -> None:
        self.name = name
        self.condition = condition
        self.message = message
        self.severity = severity


class JobMonitor:
    """
    Monitors job execution and sends alerts.

    Features:
    - Failure alerts
    - Performance degradation alerts
    - Missed schedule alerts
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = (
            storage_path or Path.home() / ".grok-harness" / "monitoring"
        )
        self.storage_path = Path(self.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.alerts: List[Alert] = []
        self.alert_history: List[Dict[str, Any]] = []
        self.notification_handlers: Dict[str, List[Callable[..., Any]]] = {
            "email": [],
            "webhook": [],
            "log": [],
        }

        self._setup_default_alerts()

    def _setup_default_alerts(self) -> None:
        """Setup default alert conditions."""

        self.add_alert(
            Alert(
                name="consecutive_failures",
                condition=lambda job, history: (
                    self._consecutive_failures(job, history) >= 3
                ),
                message="Job {job.name} has failed 3 times in a row",
                severity="error",
            )
        )

        self.add_alert(
            Alert(
                name="slow_execution",
                condition=lambda job, history: (
                    self._avg_duration_increase(job, history) > 1.5
                ),
                message="Job {job.name} is running 50% slower than average",
                severity="warning",
            )
        )

        self.add_alert(
            Alert(
                name="missed_schedule",
                condition=lambda job, history: self._missed_schedule(
                    job, history
                ),
                message="Job {job.name} may have missed its scheduled time",
                severity="warning",
            )
        )

    def add_alert(self, alert: Alert) -> None:
        """Add a custom alert."""
        self.alerts.append(alert)

    def register_handler(
        self,
        handler_type: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register a notification handler."""
        if handler_type in self.notification_handlers:
            self.notification_handlers[handler_type].append(handler)

    async def check_job(
        self,
        job: Job,
        recent_results: List[JobResult],
        all_results: List[JobResult],
    ) -> List[Dict[str, Any]]:
        """
        Check a job for alert conditions.

        Returns:
            List of triggered alerts
        """
        triggered: List[Dict[str, Any]] = []

        for alert in self.alerts:
            try:
                if alert.condition(job, recent_results):
                    alert_data = {
                        "alert": alert.name,
                        "job_id": job.id,
                        "job_name": job.name,
                        "severity": alert.severity,
                        "message": alert.message.format(job=job),
                        "timestamp": datetime.now().isoformat(),
                    }
                    triggered.append(alert_data)
                    self.alert_history.append(alert_data)
                    await self._send_notifications(alert_data)
            except Exception:
                pass

        return triggered

    def _consecutive_failures(
        self,
        job: Job,
        history: List[JobResult],
    ) -> int:
        """Count consecutive failures."""
        count = 0
        for result in reversed(history[-10:]):
            if result.job_id == job.id:
                if not result.success:
                    count += 1
                else:
                    break
        return count

    def _avg_duration_increase(
        self,
        job: Job,
        history: List[JobResult],
    ) -> float:
        """Calculate average duration increase ratio."""
        job_results = [
            r for r in history
            if r.job_id == job.id and r.success
        ]

        if len(job_results) < 5:
            return 1.0

        recent = [r.duration_ms for r in job_results[-3:]]
        historical = [r.duration_ms for r in job_results[:-3]]

        if not historical:
            return 1.0

        recent_avg = sum(recent) / len(recent)
        historical_avg = sum(historical) / len(historical)

        return (
            recent_avg / historical_avg
            if historical_avg > 0
            else 1.0
        )

    def _missed_schedule(
        self,
        job: Job,
        history: List[JobResult],
    ) -> bool:
        """Check if job may have missed its schedule."""
        if not job.schedule or not job.next_run:
            return False

        now = datetime.now()
        next_ts = job.next_run

        if next_ts < now and job.status != JobStatus.RUNNING:
            delta = (now - next_ts).total_seconds()
            if delta > 300:
                return True

        return False

    async def _send_notifications(
        self,
        alert: Dict[str, Any],
    ) -> None:
        """Send notifications for alert."""
        log_entry = (
            f"[{alert['severity'].upper()}] {alert['message']}"
        )

        log_file = self.storage_path / "alerts.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert) + "\n")

        for handler in self.notification_handlers.get("log", []):
            try:
                handler(alert)
            except Exception:
                pass

    def get_alert_history(
        self,
        job_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get alert history."""
        history = self.alert_history

        if job_id:
            history = [a for a in history if a["job_id"] == job_id]

        if severity:
            history = [a for a in history if a["severity"] == severity]

        return history[-limit:]

    def get_job_health(
        self,
        job: Job,
        history: List[JobResult],
    ) -> Dict[str, Any]:
        """Get health metrics for a job."""
        job_results = [r for r in history if r.job_id == job.id]

        if not job_results:
            return {"status": "unknown", "metrics": {}}

        total = len(job_results)
        successes = sum(1 for r in job_results if r.success)
        failures = total - successes

        recent = (
            job_results[-10:]
            if len(job_results) > 10
            else job_results
        )
        recent_successes = sum(1 for r in recent if r.success)

        durations = [r.duration_ms for r in job_results if r.success]
        avg_duration = (
            sum(durations) / len(durations)
            if durations
            else 0
        )

        recent_durations = [
            r.duration_ms for r in recent if r.success
        ]
        recent_avg = (
            sum(recent_durations) / len(recent_durations)
            if recent_durations
            else 0
        )

        if failures > successes:
            health = "critical"
        elif recent_successes / len(recent) < 0.7:
            health = "degraded"
        elif recent_avg > avg_duration * 1.5 and avg_duration > 0:
            health = "slow"
        else:
            health = "healthy"

        return {
            "status": health,
            "metrics": {
                "total_runs": total,
                "success_rate": (
                    successes / total if total > 0 else 0
                ),
                "recent_success_rate": (
                    recent_successes / len(recent)
                    if recent
                    else 0
                ),
                "avg_duration_ms": avg_duration,
                "recent_avg_duration_ms": recent_avg,
                "consecutive_failures": self._consecutive_failures(
                    job, history
                ),
            },
        }
