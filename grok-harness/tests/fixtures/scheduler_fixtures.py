"""Scheduler test fixtures."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Sample cron expressions
CRON_EXPRESSIONS = {
    "minutely": "* * * * *",
    "every_5_min": "*/5 * * * *",
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
}

# Sample interval values (seconds)
INTERVAL_VALUES = {
    "1_min": 60,
    "5_min": 300,
    "1_hour": 3600,
}

# Sample job metadata
SAMPLE_JOB_METADATA = {
    "source": "test",
    "created_by": "fixture",
}

# Sample job definitions for testing
SAMPLE_JOBS = [
    {
        "name": "test_cron_job",
        "schedule": "*/5 * * * *",
        "tags": ["test", "cron"],
    },
    {
        "name": "test_interval_job",
        "schedule": "300",
        "tags": ["test", "interval"],
    },
]
