"""Rich output formatting for CLI."""

import asyncio
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console

# Windows cp1252 cannot encode Unicode symbols; use ASCII fallbacks
_SAFE_SYMBOLS = bool(
    sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "cp437")
)
if _SAFE_SYMBOLS:
    _OK = "[OK]"
    _ERR = "[X]"
    _WARN = "[!]"
    _INFO = "[i]"
else:
    _OK = "\u2713"  # check
    _ERR = "\u274c"  # cross
    _WARN = "\u26a0\ufe0f"  # warning
    _INFO = "\u2139\ufe0f"  # info
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()


def create_progress_callback() -> tuple[
    Callable[..., None],
    Callable[[], Any],
]:
    """
    Create a progress callback and live display for orchestrator runs.

    Returns:
        (callback, get_renderable) - callback for orchestrator, get_renderable for Live
    """
    state: Dict[str, Any] = {
        "step_num": 0,
        "total": 0,
        "action": "",
        "reasoning": "",
        "result_snippet": "",
        "status": "idle",
    }

    def callback(
        step_num: int = 0,
        total: int = 0,
        action: str = "",
        reasoning: str = "",
        result_snippet: str = "",
        status: str = "running",
    ) -> None:
        state["step_num"] = step_num
        state["total"] = total
        state["action"] = action
        state["reasoning"] = reasoning
        state["result_snippet"] = result_snippet
        state["status"] = status

    def get_renderable() -> Panel:
        s = state
        status_emoji = (
            "..." if s["status"] == "running"
            else _OK if s["status"] == "success"
            else _ERR if s["status"] == "error"
            else "?" if s["status"] == "confirm"
            else " "
        )
        content = Text()
        content.append(f"{status_emoji} Step {s['step_num']}/{s['total'] or 1}\n\n", style="bold cyan")
        content.append(f"Action: {s['action']}\n", style="yellow")
        if s["reasoning"]:
            content.append(f"Reasoning: {s['reasoning'][:100]}...\n", style="dim")
        if s["result_snippet"]:
            content.append(f"Result: {s['result_snippet'][:80]}...\n", style="green")
        return Panel(
            content,
            title="[bold]Orchestrator Progress[/]",
            border_style="blue",
        )

    return callback, get_renderable


@contextmanager
def live_progress_display():
    """
    Context manager for live progress during orchestrator run.

    Yields (callback, set_final) - use callback for progress, set_final for summary.
    """
    callback, get_renderable = create_progress_callback()
    final_summary: Optional[Dict[str, Any]] = None

    def set_final(summary: Dict[str, Any]) -> None:
        nonlocal final_summary
        final_summary = summary

    with Live(
        get_renderable(),
        console=console,
        refresh_per_second=4,
    ) as live:

        def wrapped(*args: Any, **kwargs: Any) -> None:
            callback(*args, **kwargs)
            live.update(get_renderable())

        yield wrapped, set_final

        if final_summary:
            live.update(
                Panel(
                    f"""[bold]Run Complete[/]
Status: {final_summary.get('status', '')}
Steps: {final_summary.get('steps_completed', 0)}/{final_summary.get('steps_total', 0)}
Duration: {final_summary.get('duration', 0):.2f}s
Episodes stored: {final_summary.get('episodes_added', 0)}""",
                    title="Summary",
                    border_style="green",
                )
            )


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[bold green]{_OK} {message}[/]")


def print_error(message: str) -> None:
    """Print error message."""
    console.print(f"[bold red]{_ERR} {message}[/]")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[bold yellow]{_WARN}  {message}[/]")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[bold blue]{_INFO}  {message}[/]")


async def confirm_action(
    prompt: str,
    default: bool = False,
    timeout_seconds: int = 30,
) -> bool:
    """
    Ask user to confirm an action with optional timeout.

    On timeout, returns default (typically False for safety).

    Args:
        prompt: Question text (e.g. "Approve this action? [y/N]").
        default: Default when user hits Enter or on timeout.
        timeout_seconds: Max seconds to wait (0 = no timeout).

    Returns:
        True if approved, False otherwise.
    """
    def _ask() -> bool:
        from rich.prompt import Confirm
        return Confirm.ask(prompt, default=default)

    try:
        if timeout_seconds > 0:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout_seconds,
            )
        return _ask()
    except asyncio.TimeoutError:
        return default
    except (EOFError, KeyboardInterrupt):
        return default


def print_header(title: str) -> None:
    """Print section header."""
    console.print(f"\n[bold cyan]{'=' * 60}[/]")
    console.print(f"[bold cyan]{title.center(60)}[/]")
    console.print(f"[bold cyan]{'=' * 60}[/]\n")


def print_job_table(jobs: List[Dict[str, Any]]) -> None:
    """Print jobs in a table."""
    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Schedule", style="yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Next Run", style="blue")
    table.add_column("Priority", style="white")

    for job in jobs:
        schedule = job.get("schedule", "")
        if hasattr(schedule, "value"):
            schedule = str(schedule)
        next_run = job.get("next_run", "")
        if hasattr(next_run, "isoformat"):
            next_run = str(next_run)[:19] if next_run else ""
        table.add_row(
            str(job.get("id", ""))[:8],
            str(job.get("name", "")),
            str(schedule),
            str(job.get("status", "")),
            str(next_run),
            str(job.get("priority", "")),
        )

    console.print(table)


def print_result_table(results: List[Dict[str, Any]]) -> None:
    """Print job results in a table."""
    table = Table(title="Recent Job Results")
    table.add_column("Job ID", style="cyan")
    table.add_column("Time", style="white")
    table.add_column("Duration", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Error", style="red")

    for result in results:
        start = result.get("start_time", "")
        if hasattr(start, "strftime"):
            start = start.strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(
            str(result.get("job_id", ""))[:8],
            str(start),
            f"{result.get('duration_ms', 0) / 1000:.2f}s",
            _OK if result.get("success") else _ERR,
            (str(result.get("error", "")) or "")[:30],
        )

    console.print(table)


def _fmt_schedule(schedule: Optional[Any]) -> str:
    """Format schedule for display."""
    if schedule is None:
        return ""
    if isinstance(schedule, dict):
        return f"{schedule.get('type', '')}: {schedule.get('value', '')}"
    if hasattr(schedule, "value"):
        return str(schedule)
    return str(schedule)


def print_job_details(job: Dict[str, Any]) -> None:
    """Print detailed job information."""
    schedule = _fmt_schedule(job.get("schedule"))

    next_run = job.get("next_run")
    if next_run is None:
        next_run = ""
    elif hasattr(next_run, "isoformat"):
        next_run = str(next_run)[:19]
    else:
        next_run = str(next_run)

    info = f"""
[bold]ID:[/] {job.get('id')}
[bold]Name:[/] {job.get('name')}
[bold]Status:[/] {job.get('status')}
[bold]Schedule:[/] {schedule}
[bold]Next Run:[/] {next_run}
[bold]Priority:[/] {job.get('priority')}
[bold]Tags:[/] {', '.join(job.get('tags', []))}
    """

    console.print(Panel(info.strip(), title="Job Details", border_style="blue"))

    if "stats" in job:
        stats = job["stats"]
        stats_table = Table(title="Statistics")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="green")

        stats_table.add_row("Total Runs", str(stats.get("total_runs", 0)))
        stats_table.add_row("Successful", str(stats.get("successful_runs", 0)))
        stats_table.add_row("Failed", str(stats.get("failed_runs", 0)))
        stats_table.add_row(
            "Success Rate",
            f"{stats.get('success_rate', 0) * 100:.1f}%",
        )
        stats_table.add_row(
            "Avg Duration",
            f"{stats.get('avg_duration_ms', 0) / 1000:.2f}s",
        )

        console.print(stats_table)

    if "predictions" in job:
        pred = job["predictions"]
        pred_panel = Panel(
            f"""
[bold]Estimated Duration:[/] {pred.get('estimated_duration', 0):.1f}s
[bold]Confidence:[/] {pred.get('confidence', 0) * 100:.1f}%
[bold]Optimal Time:[/] {pred.get('optimal_time', 'Unknown')}:00
[bold]Risk Level:[/] {pred.get('risk_level', 'unknown')}
            """.strip(),
            title="Predictions",
            border_style="yellow",
        )
        console.print(pred_panel)


def print_system_health(health: Dict[str, Any]) -> None:
    """Print system health dashboard."""
    print_header("System Health")

    status = health.get("status", "unknown")
    status_color = "green" if status == "running" else "red"
    console.print(f"Status: [bold {status_color}]{status}[/]")
    console.print(f"Total Jobs: [bold]{health.get('total_jobs', 0)}[/]")

    if "job_status" in health:
        statuses = health["job_status"]
        status_tree = Tree("Job Status")
        for s, count in statuses.items():
            status_tree.add(f"[cyan]{s}:[/] {count}")
        console.print(status_tree)

    if "queue_size" in health:
        console.print(f"Queue Size: [bold]{health['queue_size']}[/]")

    if "job_health" in health:
        health_table = Table(title="Job Health")
        health_table.add_column("Job", style="cyan")
        health_table.add_column("Status", style="yellow")
        health_table.add_column("Success Rate", style="green")
        health_table.add_column("Recent Success", style="blue")

        for job_id, job_health in health["job_health"].items():
            metrics = job_health.get("metrics", {})
            hstatus = job_health.get("status", "unknown")
            status_emoji = (
                _OK if hstatus == "healthy"
                else _WARN if hstatus == "degraded"
                else _ERR
            )

            health_table.add_row(
                str(job_id)[:8],
                f"{status_emoji} {hstatus}",
                f"{metrics.get('success_rate', 0) * 100:.1f}%",
                f"{metrics.get('recent_success_rate', 0) * 100:.1f}%",
            )

        console.print(health_table)


def print_optimization_report(report: Dict[str, Any]) -> None:
    """Print optimization report."""
    print_header("Optimization Report")

    if "load_predictions" in report:
        load = report["load_predictions"]
        load_table = Table(title="Load Predictions (Next 24h)")
        load_table.add_column("Hour", style="cyan")
        load_table.add_column("Load", style="yellow")

        for hour in sorted(load.keys())[:12]:
            load_val = load[hour]
            bar = "█" * int(load_val * 20)
            load_table.add_row(f"{hour}:00", f"{bar} {load_val * 100:.0f}%")

        console.print(load_table)

    if "adaptive" in report:
        adaptive = report["adaptive"]
        if "patterns" in adaptive and adaptive["patterns"]:
            console.print("[bold]Learned Patterns:[/]")
            for key, value in adaptive["patterns"].items():
                console.print(f"  [cyan]{key}:[/] {value}")

    if "alert_history" in report and report["alert_history"]:
        alerts = report["alert_history"]
        alert_table = Table(title="Recent Alerts")
        alert_table.add_column("Time", style="white")
        alert_table.add_column("Severity", style="red")
        alert_table.add_column("Message", style="yellow")

        for alert in alerts[-5:]:
            alert_table.add_row(
                str(alert.get("timestamp", ""))[-8:],
                f"[{'red' if alert.get('severity') == 'error' else 'yellow'}]{alert.get('severity', '')}[/]",
                str(alert.get("message", ""))[:60],
            )

        console.print(alert_table)


def print_memory_stats(stats: Dict[str, Any]) -> None:
    """Print memory statistics."""
    table = Table(title="Memory Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    skip_keys = {"embeddings", "compression", "operations", "timestamp"}
    for key, value in stats.items():
        if key not in skip_keys:
            table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)

    if stats.get("embeddings"):
        embed_table = Table(title="Embeddings")
        embed_table.add_column("Metric", style="cyan")
        embed_table.add_column("Value", style="green")
        for k, v in stats["embeddings"].items():
            embed_table.add_row(str(k), str(v))
        console.print(embed_table)

    if stats.get("compression"):
        comp_table = Table(title="Compression")
        comp_table.add_column("Metric", style="cyan")
        comp_table.add_column("Value", style="green")
        for k, v in stats["compression"].items():
            comp_table.add_row(str(k), str(v))
        console.print(comp_table)
