"""Predefined job types for the scheduler."""

from typing import Any, Dict, List, Optional

from .models import Job, Schedule, ScheduleType


class TaskJob:
    """Job for running Grok tasks."""

    @staticmethod
    def create(
        task_runner: Any,
        goal: str,
        schedule: str = "0 * * * *",  # hourly
        job_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Job:
        """Create a task job."""
        schedule_obj = (
            Schedule(type=ScheduleType.CRON, value=schedule)
            if " " in schedule and len(schedule.split()) >= 5
            else Schedule(type=ScheduleType.INTERVAL, value=schedule)
        )
        return Job(
            id=job_id or "",
            name=f"task:{goal[:50]}",
            func=TaskJob._run,
            args=[task_runner, goal],
            kwargs=kwargs,
            schedule=schedule_obj,
            tags=["task", "grok"],
        )

    @staticmethod
    async def _run(task_runner: Any, goal: str, **kwargs: Any) -> Any:
        """Execute the task."""
        if hasattr(task_runner, "run_task"):
            return await task_runner.run_task(goal, **kwargs)
        return None


class BrowserJob:
    """Job for browser automation tasks."""

    @staticmethod
    def create(
        browser_agent: Any,
        url: str,
        action: str = "navigate",
        schedule: str = "*/30 * * * *",
        **kwargs: Any,
    ) -> Job:
        """Create a browser job."""
        schedule_obj = (
            Schedule(type=ScheduleType.CRON, value=schedule)
            if " " in schedule and len(schedule.split()) >= 5
            else Schedule(type=ScheduleType.INTERVAL, value=schedule)
        )
        return Job(
            name=f"browser:{action}:{url[:30]}",
            func=BrowserJob._run,
            args=[browser_agent, url, action],
            kwargs=kwargs,
            schedule=schedule_obj,
            tags=["browser", "automation"],
        )

    @staticmethod
    async def _run(
        browser_agent: Any,
        url: str,
        action: str,
        **kwargs: Any,
    ) -> Any:
        """Execute the browser action."""
        if action == "navigate" and hasattr(browser_agent, "navigate"):
            return await browser_agent.navigate(url, **kwargs)
        return None


class ExtractionJob:
    """Job for data extraction."""

    @staticmethod
    def create(
        extractor: Any,
        url: str,
        data_type: str = "prices",
        schedule: str = "0 */2 * * *",
        **kwargs: Any,
    ) -> Job:
        """Create an extraction job."""
        schedule_obj = (
            Schedule(type=ScheduleType.CRON, value=schedule)
            if " " in schedule and len(schedule.split()) >= 5
            else Schedule(type=ScheduleType.INTERVAL, value=schedule)
        )
        return Job(
            name=f"extract:{data_type}:{url[:30]}",
            func=ExtractionJob._run,
            args=[extractor, url, data_type],
            kwargs=kwargs,
            schedule=schedule_obj,
            tags=["extraction", data_type],
        )

    @staticmethod
    async def _run(
        extractor: Any,
        url: str,
        data_type: str,
        **kwargs: Any,
    ) -> Any:
        """Execute the extraction."""
        if hasattr(extractor, "extract"):
            return await extractor.extract(url, data_type, **kwargs)
        return None


class MemoryCleanupJob:
    """Job for memory cleanup."""

    @staticmethod
    def create(
        memory: Any,
        schedule: str = "0 3 * * *",
        **kwargs: Any,
    ) -> Job:
        """Create a memory cleanup job."""
        schedule_obj = (
            Schedule(type=ScheduleType.CRON, value=schedule)
            if " " in schedule and len(schedule.split()) >= 5
            else Schedule(type=ScheduleType.INTERVAL, value=schedule)
        )
        return Job(
            name="memory_cleanup",
            func=MemoryCleanupJob._run,
            args=[memory],
            kwargs=kwargs,
            schedule=schedule_obj,
            tags=["memory", "cleanup"],
        )

    @staticmethod
    async def _run(memory: Any, **kwargs: Any) -> Any:
        """Execute memory cleanup."""
        if hasattr(memory, "vacuum"):
            await memory.vacuum()
        if hasattr(memory, "cleanup"):
            await memory.cleanup()
        return None


class CompressionJob:
    """Job for memory compression."""

    @staticmethod
    def create(
        memory: Any,
        schedule: str = "0 4 * * *",
        **kwargs: Any,
    ) -> Job:
        """Create a compression job."""
        schedule_obj = (
            Schedule(type=ScheduleType.CRON, value=schedule)
            if " " in schedule and len(schedule.split()) >= 5
            else Schedule(type=ScheduleType.INTERVAL, value=schedule)
        )
        return Job(
            name="memory_compression",
            func=CompressionJob._run,
            args=[memory],
            kwargs=kwargs,
            schedule=schedule_obj,
            tags=["memory", "compression"],
        )

    @staticmethod
    async def _run(memory: Any, **kwargs: Any) -> Any:
        """Execute compression (if memory has auto_compressor)."""
        auto = getattr(memory, "auto_compressor", None)
        if auto and hasattr(auto, "_check_and_compress"):
            await auto._check_and_compress()
        return None
