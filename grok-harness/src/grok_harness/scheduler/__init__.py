"""Scheduler system for task automation and recurring jobs."""

from .conflict import ConflictAwareScheduler, ConflictDetector, ResourceLock
from .core import Scheduler
from .jobs import (
    BrowserJob,
    CompressionJob,
    ExtractionJob,
    MemoryCleanupJob,
    TaskJob,
)
from .learning import AdaptiveScheduler, PatternLearner
from .models import (
    Job,
    JobPriority,
    JobResult,
    JobStats,
    JobStatus,
    Schedule,
    ScheduleType,
    TriggerInfo,
)
from .monitoring import Alert, JobMonitor
from .predictive import LoadPredictor, Prediction, PredictiveEngine
from .queue import PriorityJobQueue, QueueItem
from .smart import SmartScheduler

__all__ = [
    "AdaptiveScheduler",
    "Alert",
    "BrowserJob",
    "CompressionJob",
    "ConflictAwareScheduler",
    "ConflictDetector",
    "ExtractionJob",
    "Job",
    "JobMonitor",
    "JobPriority",
    "JobResult",
    "JobStats",
    "JobStatus",
    "LoadPredictor",
    "MemoryCleanupJob",
    "PatternLearner",
    "Prediction",
    "PredictiveEngine",
    "PriorityJobQueue",
    "QueueItem",
    "ResourceLock",
    "Schedule",
    "ScheduleType",
    "Scheduler",
    "SmartScheduler",
    "TaskJob",
    "TriggerInfo",
]
