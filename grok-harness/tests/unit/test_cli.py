"""Unit tests for CLI."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.cli.commands import (
    create_parser,
    run_config_command,
    run_jobs_command,
    run_memory_command,
    run_monitor_command,
    run_schedule_command,
    _priority_from_str,
)
from grok_harness.cli.output import (
    console,
    print_error,
    print_header,
    print_info,
    print_job_details,
    print_job_table,
    print_memory_stats,
    print_result_table,
    print_success,
    print_system_health,
    print_warning,
)
from grok_harness.scheduler.models import JobPriority


def test_create_parser() -> None:
    """Test parser creation and basic structure."""
    parser = create_parser()
    args = parser.parse_args(
        ["agent", "test goal", "--headless"]
    )
    assert args.command == "agent"
    assert args.goal == "test goal"
    assert args.headless is True


def test_create_parser_schedule() -> None:
    """Test schedule subcommand parsing."""
    parser = create_parser()
    args = parser.parse_args(
        ["schedule", "list"]
    )
    assert args.command == "schedule"
    assert args.schedule_command == "list"


def test_create_parser_jobs() -> None:
    """Test jobs subcommand parsing."""
    parser = create_parser()
    args = parser.parse_args(
        ["jobs", "list", "--limit", "5"]
    )
    assert args.command == "jobs"
    assert args.jobs_command == "list"
    assert args.limit == 5


def test_create_parser_memory() -> None:
    """Test memory subcommand parsing."""
    parser = create_parser()
    args = parser.parse_args(
        ["memory", "search", "query", "--semantic"]
    )
    assert args.command == "memory"
    assert args.memory_command == "search"
    assert args.query == "query"
    assert args.semantic is True


def test_create_parser_monitor() -> None:
    """Test monitor subcommand parsing."""
    parser = create_parser()
    args = parser.parse_args(
        ["monitor", "health"]
    )
    assert args.command == "monitor"
    assert args.monitor_command == "health"


def test_create_parser_config() -> None:
    """Test config subcommand parsing."""
    parser = create_parser()
    args = parser.parse_args(
        ["config", "show"]
    )
    assert args.command == "config"
    assert args.config_command == "show"


def test_priority_from_str() -> None:
    """Test priority string conversion."""
    assert _priority_from_str("low") == JobPriority.LOW
    assert _priority_from_str("normal") == JobPriority.NORMAL
    assert _priority_from_str("high") == JobPriority.HIGH
    assert _priority_from_str("critical") == JobPriority.CRITICAL
    assert _priority_from_str("unknown") == JobPriority.NORMAL


def test_print_job_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Test job table output."""
    jobs = [
        {
            "id": "abc123",
            "name": "Test Job",
            "schedule": "0 9 * * *",
            "status": "scheduled",
            "next_run": "2025-01-15 09:00",
            "priority": "normal",
        }
    ]
    print_job_table(jobs)
    captured = capsys.readouterr()
    assert "Test Job" in captured.out
    assert "abc123" in captured.out


def test_print_result_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Test result table output."""
    from datetime import datetime

    results = [
        {
            "job_id": "xyz789",
            "start_time": datetime.now().strftime("%H:%M:%S"),
            "duration_ms": 1500,
            "success": True,
            "error": "",
        }
    ]
    print_result_table(results)
    captured = capsys.readouterr()
    assert "xyz789" in captured.out
    assert "1.50" in captured.out or "1.5" in captured.out


def test_print_system_health(capsys: pytest.CaptureFixture[str]) -> None:
    """Test system health output."""
    health = {
        "status": "running",
        "total_jobs": 5,
        "job_status": {"scheduled": 4, "running": 1},
        "queue_size": 0,
    }
    print_system_health(health)
    captured = capsys.readouterr()
    assert "running" in captured.out
    assert "5" in captured.out


def test_print_memory_stats(capsys: pytest.CaptureFixture[str]) -> None:
    """Test memory stats output."""
    stats = {
        "total_items": 100,
        "items_by_type": {"task_result": 50},
    }
    print_memory_stats(stats)
    captured = capsys.readouterr()
    assert "100" in captured.out


def test_print_job_details(capsys: pytest.CaptureFixture[str]) -> None:
    """Test job details output."""
    job = {
        "id": "job1",
        "name": "Test",
        "status": "scheduled",
        "schedule": {"type": "cron", "value": "0 * * * *"},
        "next_run": "",
        "priority": "normal",
        "tags": ["test"],
        "stats": {
            "total_runs": 10,
            "successful_runs": 8,
            "failed_runs": 2,
            "success_rate": 0.8,
            "avg_duration_ms": 1000,
        },
    }
    print_job_details(job)
    captured = capsys.readouterr()
    assert "job1" in captured.out
    assert "Test" in captured.out
    assert "10" in captured.out


@pytest.mark.asyncio
async def test_run_config_show(tmp_path: Path) -> None:
    """Test config show command."""
    from grok_harness.core.types import FullConfig

    config = FullConfig(version="0.1.0")
    args = MagicMock()
    args.config_command = "show"

    await run_config_command(args, config)
    # Should not raise; outputs config


@pytest.mark.asyncio
async def test_run_jobs_list() -> None:
    """Test jobs list command."""
    scheduler = MagicMock()
    scheduler.get_recent_results.return_value = []

    args = MagicMock()
    args.jobs_command = "list"
    args.limit = 20
    args.failed = False

    await run_jobs_command(args, scheduler)
    scheduler.get_recent_results.assert_called_once_with(limit=20)


@pytest.mark.asyncio
async def test_run_monitor_health() -> None:
    """Test monitor health command."""
    scheduler = AsyncMock()
    scheduler.get_system_health = AsyncMock(
        return_value={
            "status": "running",
            "total_jobs": 0,
            "job_status": {},
            "queue_size": 0,
        }
    )

    args = MagicMock()
    args.monitor_command = "health"

    await run_monitor_command(args, scheduler)
    scheduler.get_system_health.assert_called_once()


@pytest.mark.asyncio
async def test_run_schedule_list() -> None:
    """Test schedule list command."""
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []

    args = MagicMock()
    args.schedule_command = "list"
    args.status = None
    args.tag = None

    config = MagicMock()

    await run_schedule_command(args, config, scheduler)
    scheduler.get_jobs.assert_called_once()


@pytest.mark.asyncio
async def test_run_schedule_show_not_found() -> None:
    """Test schedule show when job not found."""
    scheduler = MagicMock()
    scheduler.get_job.return_value = None

    args = MagicMock()
    args.schedule_command = "show"
    args.job_id = "nonexistent"

    config = MagicMock()

    await run_schedule_command(args, config, scheduler)
    scheduler.get_job.assert_called_once_with("nonexistent")


def test_parser_help() -> None:
    """Test parser help exits cleanly."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0
