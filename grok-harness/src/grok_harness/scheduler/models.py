"""Scheduler data models."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class JobStatus(Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"
    PAUSED = "paused"
    RETRYING = "retrying"


class JobPriority(Enum):
    """Job priority levels."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class ScheduleType(Enum):
    """Schedule type."""

    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"
    DATE = "date"
    HOOK = "hook"


@dataclass
class TriggerInfo:
    """Information about what triggered a job."""

    type: ScheduleType
    value: str
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    misfire_grace_time: int = 60


@dataclass
class Schedule:
    """Schedule configuration for a job."""

    type: ScheduleType
    value: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timezone: str = "UTC"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "value": self.value,
            "start_date": (
                self.start_date.isoformat()
                if self.start_date
                else None
            ),
            "end_date": (
                self.end_date.isoformat()
                if self.end_date
                else None
            ),
            "timezone": self.timezone,
        }

    @classmethod
    def from_cron(cls, cron_expr: str, timezone: str = "UTC") -> "Schedule":
        """Create schedule from cron expression."""
        return cls(
            type=ScheduleType.CRON,
            value=cron_expr,
            timezone=timezone,
        )

    @classmethod
    def from_interval(cls, interval_seconds: str, timezone: str = "UTC") -> "Schedule":
        """Create schedule from interval (seconds as string)."""
        return cls(
            type=ScheduleType.INTERVAL,
            value=str(interval_seconds),
            timezone=timezone,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schedule":
        """Create from dictionary."""
        return cls(
            type=ScheduleType(data["type"]),
            value=data["value"],
            start_date=(
                datetime.fromisoformat(data["start_date"])
                if data.get("start_date")
                else None
            ),
            end_date=(
                datetime.fromisoformat(data["end_date"])
                if data.get("end_date")
                else None
            ),
            timezone=data.get("timezone", "UTC"),
        )


@dataclass
class Job:
    """Base job definition."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    func: Optional[Callable[..., Any]] = None
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)

    schedule: Optional[Schedule] = None
    trigger_info: Optional[TriggerInfo] = None

    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    max_instances: int = 1
    max_retries: int = 3
    retry_delay: int = 60

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    tags: List[str] = field(default_factory=list)
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    resources: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "status": self.status.value,
            "priority": self.priority.value,
            "max_instances": self.max_instances,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run": (
                self.last_run.isoformat()
                if self.last_run
                else None
            ),
            "next_run": (
                self.next_run.isoformat()
                if self.next_run
                else None
            ),
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "tags": self.tags,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "resources": self.resources,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create from dictionary."""
        priority_val = data.get("priority", 1)
        if isinstance(priority_val, str):
            priority = JobPriority[priority_val.upper()]
        else:
            priority = JobPriority(priority_val)

        job = cls(
            id=data["id"],
            name=data.get("name", ""),
            status=JobStatus(data.get("status", "pending")),
            priority=priority,
            max_instances=data.get("max_instances", 1),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 60),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            last_run=(
                datetime.fromisoformat(data["last_run"])
                if data.get("last_run")
                else None
            ),
            next_run=(
                datetime.fromisoformat(data["next_run"])
                if data.get("next_run")
                else None
            ),
            total_runs=data.get("total_runs", 0),
            successful_runs=data.get("successful_runs", 0),
            failed_runs=data.get("failed_runs", 0),
            tags=data.get("tags", []),
            user_id=data.get("user_id"),
            metadata=data.get("metadata", {}),
            resources=data.get("resources"),
        )

        if data.get("schedule"):
            job.schedule = Schedule.from_dict(data["schedule"])

        return job


@dataclass
class JobResult:
    """Result of a job execution."""

    job_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_ms: float
    error: Optional[str] = None
    result: Optional[Any] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "success": self.success,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "result": (
                json.dumps(self.result)
                if self.result is not None
                else None
            ),
            "retry_count": self.retry_count,
        }


@dataclass
class JobStats:
    """Statistics for a job."""

    job_id: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    avg_duration_ms: float
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    success_rate: float

    @classmethod
    def from_job(cls, job: Job) -> "JobStats":
        """Create from job."""
        total = job.total_runs
        success = job.successful_runs
        return cls(
            job_id=job.id,
            total_runs=total,
            successful_runs=success,
            failed_runs=job.failed_runs,
            avg_duration_ms=0.0,
            last_run=job.last_run,
            next_run=job.next_run,
            success_rate=success / total if total > 0 else 0.0,
        )
