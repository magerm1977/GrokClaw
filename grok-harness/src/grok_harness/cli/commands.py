"""CLI commands for Grok-Harness."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from ..browser.agent import GrokBrowserAgent
from ..core.config_manager import ConfigManager
from ..core.grok_client import GrokClient
from ..core.orchestrator import Orchestrator, RunOptions, RunResult
from ..core.types import BrowserConfig, FullConfig, GrokConfig
from ..memory.models import MemoryItemType
from ..memory.unified import UnifiedMemory
from ..scheduler.models import JobPriority
from ..scheduler.smart import SmartScheduler
from .interactive import InteractiveMode
from .output import (
    console,
    live_progress_display,
    print_error,
    print_header,
    print_info,
    print_job_details,
    print_job_table,
    print_memory_stats,
    print_optimization_report,
    print_result_table,
    print_success,
    print_system_health,
    print_warning,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        description="Grok-Harness - AI-Powered Automation Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  grok-harness agent "Get weather in London" --headless
  grok-harness schedule add "0 9 * * *" "agent daily report" --name "Daily Report"
  grok-harness jobs list
  grok-harness memory search "prices" --semantic
  grok-harness monitor health
  grok-harness interactive
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="Commands",
        required=True,
    )

    # Agent command
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run autonomous browser agent",
    )
    agent_parser.add_argument(
        "goal",
        type=str,
        help="What you want the agent to accomplish",
    )
    agent_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Ask for approval before each action",
    )
    agent_parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum number of actions",
    )
    agent_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    agent_parser.add_argument(
        "--save-results",
        type=str,
        help="Save results to file",
    )
    agent_parser.add_argument(
        "--no-live",
        action="store_true",
        help="Disable live progress display",
    )
    agent_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full Grok reasoning and step details",
    )
    agent_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only, do not execute steps",
    )

    # Schedule command group
    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Schedule management",
    )
    schedule_subparsers = schedule_parser.add_subparsers(
        dest="schedule_command",
        help="Schedule commands",
        required=True,
    )

    schedule_add = schedule_subparsers.add_parser(
        "add",
        help="Add a scheduled job",
    )
    schedule_add.add_argument(
        "schedule",
        type=str,
        help='Cron expression (e.g., "0 9 * * *") or interval in seconds',
    )
    schedule_add.add_argument(
        "command",
        type=str,
        help='Command to run (e.g., "agent Get weather")',
    )
    schedule_add.add_argument(
        "--name",
        type=str,
        help="Job name",
    )
    schedule_add.add_argument(
        "--priority",
        choices=["low", "normal", "high", "critical"],
        default="normal",
        help="Job priority",
    )
    schedule_add.add_argument(
        "--resources",
        type=str,
        nargs="+",
        help="Required resources",
    )
    schedule_add.add_argument(
        "--tags",
        type=str,
        nargs="+",
        help="Job tags",
    )

    schedule_list = schedule_subparsers.add_parser(
        "list",
        help="List scheduled jobs",
    )
    schedule_list.add_argument(
        "--status",
        choices=["scheduled", "running", "paused", "failed"],
        help="Filter by status",
    )
    schedule_list.add_argument(
        "--tag",
        type=str,
        help="Filter by tag",
    )

    for cmd in ["pause", "resume", "remove"]:
        p = schedule_subparsers.add_parser(
            cmd,
            help=f"{cmd.capitalize()} a job",
        )
        p.add_argument(
            "job_id",
            type=str,
            help="Job ID",
        )

    schedule_show = schedule_subparsers.add_parser(
        "show",
        help="Show job details",
    )
    schedule_show.add_argument(
        "job_id",
        type=str,
        help="Job ID",
    )

    # Jobs command group
    jobs_parser = subparsers.add_parser(
        "jobs",
        help="Job management",
    )
    jobs_subparsers = jobs_parser.add_subparsers(
        dest="jobs_command",
        help="Job commands",
        required=True,
    )

    jobs_list = jobs_subparsers.add_parser(
        "list",
        help="List recent jobs",
    )
    jobs_list.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of jobs to show",
    )
    jobs_list.add_argument(
        "--failed",
        action="store_true",
        help="Show only failed jobs",
    )

    jobs_results = jobs_subparsers.add_parser(
        "results",
        help="Show job results",
    )
    jobs_results.add_argument(
        "job_id",
        type=str,
        nargs="?",
        help="Job ID (show all if omitted)",
    )
    jobs_results.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of results to show",
    )

    # Memory command group
    memory_parser = subparsers.add_parser(
        "memory",
        help="Memory management",
    )
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command",
        help="Memory commands",
        required=True,
    )

    memory_search = memory_subparsers.add_parser(
        "search",
        help="Search memory",
    )
    memory_search.add_argument(
        "query",
        type=str,
        help="Search query",
    )
    memory_search.add_argument(
        "--semantic",
        action="store_true",
        help="Use semantic search",
    )
    memory_search.add_argument(
        "--type",
        choices=["task", "extraction", "session", "all"],
        default="all",
        help="Memory type to search",
    )
    memory_search.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of results",
    )

    memory_subparsers.add_parser(
        "stats",
        help="Show memory statistics",
    )

    memory_clear = memory_subparsers.add_parser(
        "clear",
        help="Clear memory",
    )
    memory_clear.add_argument(
        "--type",
        choices=["task", "extraction", "session", "all"],
        default="all",
        help="Memory type to clear",
    )
    memory_clear.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation",
    )

    # Monitor command group
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="System monitoring",
    )
    monitor_subparsers = monitor_parser.add_subparsers(
        dest="monitor_command",
        help="Monitor commands",
        required=True,
    )

    monitor_subparsers.add_parser(
        "health",
        help="Show system health",
    )

    monitor_alerts = monitor_subparsers.add_parser(
        "alerts",
        help="Show alert history",
    )
    monitor_alerts.add_argument(
        "--job",
        type=str,
        help="Filter by job ID",
    )
    monitor_alerts.add_argument(
        "--severity",
        choices=["warning", "error"],
        help="Filter by severity",
    )
    monitor_alerts.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of alerts",
    )

    monitor_subparsers.add_parser(
        "optimize",
        help="Show optimization report",
    )

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Configuration management",
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_command",
        help="Config commands",
        required=True,
    )

    config_subparsers.add_parser(
        "show",
        help="Show current configuration",
    )

    config_set = config_subparsers.add_parser(
        "set",
        help="Set configuration value",
    )
    config_set.add_argument(
        "key",
        type=str,
        help="Configuration key (e.g., grok.model)",
    )
    config_set.add_argument(
        "value",
        type=str,
        help="Configuration value",
    )

    subparsers.add_parser(
        "interactive",
        help="Start interactive mode",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="REPL loop calling orchestrator (plan, execute, remember)",
    )
    run_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Require approval for high-risk actions",
    )

    return parser


def _priority_from_str(s: str) -> JobPriority:
    """Convert priority string to enum."""
    return {
        "low": JobPriority.LOW,
        "normal": JobPriority.NORMAL,
        "high": JobPriority.HIGH,
        "critical": JobPriority.CRITICAL,
    }.get(s.lower(), JobPriority.NORMAL)


async def run_agent(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Run the browser agent via orchestrator (plan, execute, remember)."""
    if isinstance(config, FullConfig):
        grok_config = config.grok
        browser_config = config.browser
    else:
        grok_config = GrokConfig()
        browser_config = BrowserConfig()

    api_key = (
        grok_config.api_key
        or os.environ.get("XAI_API_KEY")
        or os.environ.get("GROK_API_KEY")
    )
    if not api_key:
        print_error("No Grok API key found. Set XAI_API_KEY or configure in config.")
        return

    if args.headless:
        browser_config.headless = True

    memory_config = config.memory if isinstance(config, FullConfig) else ConfigManager.create_default_config().memory
    memory = UnifiedMemory(memory_config)
    await memory.start()

    grok_client = GrokClient(grok_config)
    await grok_client.__aenter__()

    scheduler = SmartScheduler(
        grok_client=grok_client,
        enable_learning=bool(grok_client),
        enable_predictive=True,
        enable_monitoring=False,
    )
    await scheduler.start()

    orchestrator = Orchestrator(config, grok_client, memory, scheduler)

    opts = RunOptions(
        interactive=args.interactive,
        max_steps=args.max_steps,
        live_progress=not getattr(args, "no_live", False),
        verbose=getattr(args, "verbose", False),
        dry_run=getattr(args, "dry_run", False),
    )

    try:
        if opts.live_progress:
            with live_progress_display() as (progress_cb, set_final):
                orchestrator.set_progress_callback(progress_cb)
                result = await orchestrator.run(args.goal, opts)
                set_final({
                    "status": result.status,
                    "steps_completed": result.steps_completed,
                    "steps_total": result.steps_total,
                    "duration": result.duration,
                    "episodes_added": result.episodes_added,
                })
        else:
            result = await orchestrator.run(args.goal, opts)

        if result.status == "success":
            print_success("Task completed!")
        else:
            print_warning(f"Task ended with status: {result.status}")

        console.print(f"Steps: {result.steps_completed}/{result.steps_total}")
        console.print(f"Duration: {result.duration:.2f}s")

        if result.result:
            console.print("\n[bold]Results:[/]")
            res = result.result
            if isinstance(res, dict):
                for key, value in res.items():
                    if key != "screenshot" and key != "error":
                        console.print(f"  {key}: {value}")
            else:
                console.print(f"  {res}")

        if args.save_results:
            with open(args.save_results, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "goal": args.goal,
                        "results": result.result,
                        "steps": result.steps_completed,
                        "duration": result.duration,
                        "action_history": result.action_history,
                    },
                    f,
                    indent=2,
                )
            print_success(f"Results saved to {args.save_results}")
    finally:
        await scheduler.stop()
        await memory.stop()
        await grok_client.__aexit__(None, None, None)


async def run_schedule_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
    scheduler: SmartScheduler,
) -> None:
    """Run schedule commands."""
    if args.schedule_command == "add":
        cmd_parts = args.command.split()
        cmd_type = cmd_parts[0] if cmd_parts else ""

        if cmd_type == "agent":
            goal = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""

            async def job_func() -> Any:
                if isinstance(config, FullConfig):
                    grok_cfg = config.grok
                    browser_cfg = config.browser
                    sys_info = config.system
                else:
                    grok_cfg = GrokConfig()
                    browser_cfg = BrowserConfig()
                    sys_info = ConfigManager.detect_system_info()

                async with GrokClient(grok_cfg) as grok:
                    async with GrokBrowserAgent(
                        grok, browser_cfg, sys_info
                    ) as agent:
                        result = await agent.run_task(goal, max_steps=30)
                        return result.results

            job = await scheduler.schedule(
                func=job_func,
                schedule=args.schedule,
                name=args.name or f"Agent: {goal[:30]}",
                priority=_priority_from_str(args.priority),
                resources=args.resources,
                tags=args.tags,
            )

            print_success(f"Job scheduled with ID: {job.id}")
        else:
            print_error(f"Unknown command type: {cmd_type}")

    elif args.schedule_command == "list":
        from ..scheduler.models import JobStatus

        status_map = {
            "scheduled": JobStatus.SCHEDULED,
            "running": JobStatus.RUNNING,
            "paused": JobStatus.PAUSED,
            "failed": JobStatus.FAILED,
        }
        status = status_map.get(args.status) if args.status else None
        tags = [args.tag] if args.tag else None

        jobs = scheduler.get_jobs(status=status, tags=tags)
        job_list = []
        for job in jobs:
            sched_str = (
                f"{job.schedule.type.value}: {job.schedule.value}"
                if job.schedule
                else ""
            )
            job_list.append({
                "id": job.id,
                "name": job.name,
                "schedule": sched_str,
                "status": job.status.value,
                "next_run": str(job.next_run)[:19] if job.next_run else "",
                "priority": job.priority.value,
            })
        print_job_table(job_list)

    elif args.schedule_command == "pause":
        if await scheduler.pause_job(args.job_id):
            print_success(f"Job {args.job_id} paused")
        else:
            print_error(f"Job {args.job_id} not found")

    elif args.schedule_command == "resume":
        if await scheduler.resume_job(args.job_id):
            print_success(f"Job {args.job_id} resumed")
        else:
            print_error(f"Job {args.job_id} not found")

    elif args.schedule_command == "remove":
        if await scheduler.remove_job(args.job_id):
            print_success(f"Job {args.job_id} removed")
        else:
            print_error(f"Job {args.job_id} not found")

    elif args.schedule_command == "show":
        job = scheduler.get_job(args.job_id)
        if job:
            stats = scheduler.get_job_stats(args.job_id)
            job_dict = job.to_dict()
            if stats:
                job_dict["stats"] = {
                    "total_runs": stats.get("total_runs", 0),
                    "successful_runs": stats.get("successful_runs", 0),
                    "failed_runs": stats.get("failed_runs", 0),
                    "success_rate": stats.get("success_rate", 0),
                    "avg_duration_ms": stats.get("avg_duration_ms", 0),
                }
                if "predictions" in stats:
                    job_dict["predictions"] = stats["predictions"]
            print_job_details(job_dict)
        else:
            print_error(f"Job {args.job_id} not found")


async def run_jobs_command(
    args: argparse.Namespace,
    scheduler: SmartScheduler,
) -> None:
    """Run jobs commands."""
    if args.jobs_command == "list":
        results = scheduler.get_recent_results(limit=args.limit)
        if args.failed:
            results = [r for r in results if not r.success]

        result_list = []
        for r in results:
            result_list.append({
                "job_id": r.job_id,
                "start_time": r.start_time.strftime("%H:%M:%S"),
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error": r.error or "",
            })
        print_result_table(result_list)

    elif args.jobs_command == "results":
        results = scheduler.get_recent_results(
            job_id=args.job_id,
            limit=args.limit,
        )
        result_list = []
        for r in results:
            result_list.append({
                "job_id": r.job_id,
                "start_time": r.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error": r.error or "",
            })
        print_result_table(result_list)


async def run_memory_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Run memory commands."""
    if isinstance(config, FullConfig):
        memory_config = config.memory
    else:
        from ..core.types import MemoryConfig

        memory_config = MemoryConfig()

    memory = UnifiedMemory(memory_config)
    await memory.start()

    try:
        if args.memory_command == "search":
            type_filter = None
            if args.type != "all":
                type_map = {
                    "task": MemoryItemType.TASK_RESULT,
                    "extraction": MemoryItemType.EXTRACTED_DATA,
                    "session": MemoryItemType.SESSION,
                }
                type_filter = type_map.get(args.type)

            results = await memory.search(
                query=args.query,
                limit=args.limit,
                use_semantic=args.semantic,
                type_filter=type_filter,
            )

            if results:
                table = Table(title="Search Results")
                table.add_column("Type", style="cyan")
                table.add_column("Key", style="green")
                table.add_column("Content Preview", style="white")

                for item in results:
                    content = item.content
                    if isinstance(content, dict):
                        preview = str(content)[:50] + "..."
                    else:
                        preview = str(content)[:50] + "..." if content else ""
                    table.add_row(
                        item.type.value,
                        item.key[:30] if item.key else "",
                        preview,
                    )
                console.print(table)
            else:
                print_info("No results found")

        elif args.memory_command == "stats":
            stats = await memory.get_stats()
            print_memory_stats(stats)

        elif args.memory_command == "clear":
            if not args.force:
                if not Confirm.ask(
                    f"Are you sure you want to clear {args.type} memory?"
                ):
                    return

            type_map = {
                "task": MemoryItemType.TASK_RESULT,
                "extraction": MemoryItemType.EXTRACTED_DATA,
                "session": MemoryItemType.SESSION,
                "all": None,
            }
            await memory.clear(type_map[args.type])
            print_success("Memory cleared")

    finally:
        await memory.stop()


async def run_monitor_command(
    args: argparse.Namespace,
    scheduler: SmartScheduler,
) -> None:
    """Run monitor commands."""
    if args.monitor_command == "health":
        health = await scheduler.get_system_health()
        print_system_health(health)

    elif args.monitor_command == "alerts":
        if hasattr(scheduler, "monitor") and scheduler.monitor:
            alerts = scheduler.monitor.get_alert_history(
                job_id=args.job,
                severity=args.severity,
                limit=args.limit,
            )

            if alerts:
                table = Table(title="Alert History")
                table.add_column("Time", style="white")
                table.add_column("Severity", style="red")
                table.add_column("Job", style="cyan")
                table.add_column("Message", style="yellow")

                for alert in alerts:
                    table.add_row(
                        str(alert.get("timestamp", ""))[-19:],
                        f"[{'red' if alert.get('severity') == 'error' else 'yellow'}]{alert.get('severity', '')}[/]",
                        str(alert.get("job_id", ""))[:8],
                        str(alert.get("message", ""))[:50],
                    )
                console.print(table)
            else:
                print_info("No alerts found")
        else:
            print_warning("Monitoring not enabled")

    elif args.monitor_command == "optimize":
        report = await scheduler.get_optimization_report()
        print_optimization_report(report)


async def run_run_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """REPL loop calling orchestrator repeatedly."""
    from rich.prompt import Prompt

    grok_cfg = config.grok if isinstance(config, FullConfig) else GrokConfig()
    api_key = (
        grok_cfg.api_key
        or os.environ.get("XAI_API_KEY")
        or os.environ.get("GROK_API_KEY")
    )
    if not api_key:
        print_error("No Grok API key. Set XAI_API_KEY or configure.")
        return

    memory = UnifiedMemory(config.memory if isinstance(config, FullConfig) else ConfigManager.create_default_config().memory)
    await memory.start()

    grok = GrokClient(grok_cfg)
    await grok.__aenter__()

    scheduler = SmartScheduler(
        grok_client=grok,
        enable_learning=True,
        enable_predictive=True,
        enable_monitoring=False,
    )
    await scheduler.start()

    orchestrator = Orchestrator(config, grok, memory, scheduler)
    opts = RunOptions(interactive=args.interactive, live_progress=True)

    print_header("Orchestrator REPL")
    print_info("Enter a task (or 'exit' to quit)")

    try:
        while True:
            try:
                task = Prompt.ask("\n[bold cyan]task>[/]")
                if not task or task.strip().lower() in ("exit", "quit"):
                    break

                with live_progress_display() as (progress_cb, set_final):
                    orchestrator.set_progress_callback(progress_cb)
                    result = await orchestrator.run(task.strip(), opts)
                    set_final({
                        "status": result.status,
                        "steps_completed": result.steps_completed,
                        "steps_total": result.steps_total,
                        "duration": result.duration,
                        "episodes_added": result.episodes_added,
                    })

                if result.status == "success":
                    print_success("Done!")
                else:
                    print_warning(f"Status: {result.status}")
            except KeyboardInterrupt:
                print_info("\nUse 'exit' to quit")
    finally:
        await scheduler.stop()
        await memory.stop()
        await grok.__aexit__(None, None, None)


async def run_config_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Run config commands."""
    if args.config_command == "show":
        if hasattr(config, "to_dict"):
            config_dict = config.to_dict()
        else:
            config_dict = config

        def _serialize(obj: Any) -> Any:
            if hasattr(obj, "value") and not isinstance(obj, type):
                return obj.value
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(v) for v in obj]
            return obj

        config_dict = _serialize(config_dict)
        syntax = Syntax(
            json.dumps(config_dict, indent=2),
            "json",
            theme="monokai",
        )
        console.print(syntax)

    elif args.config_command == "set":
        parts = args.key.split(".")
        current: Any = config
        for part in parts[:-1]:
            if hasattr(current, part):
                current = getattr(current, part)
            else:
                print_error(f"Invalid key: {args.key}")
                return

        last_part = parts[-1]
        current_val = (
            getattr(current, last_part)
            if hasattr(current, last_part)
            else None
        )

        if isinstance(current_val, bool):
            value: Any = args.value.lower() in ["true", "yes", "1"]
        elif isinstance(current_val, int):
            value = int(args.value)
        elif isinstance(current_val, float):
            value = float(args.value)
        else:
            value = args.value

        setattr(current, last_part, value)

        config_path = (
            Path(args.config)
            if args.config
            else Path.home() / ".grok-harness" / "config.yaml"
        )
        ConfigManager.save_config(config, config_path)
        print_success(f"Set {args.key} = {value}")


async def main_async() -> int:
    """Async main function."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    config = ConfigManager.load_config(args.config)
    if not isinstance(config, FullConfig):
        config = ConfigManager.create_default_config()

    grok_client = None
    scheduler = None

    try:
        if args.command in ["schedule", "jobs", "monitor"]:
            api_key = (
                config.grok.api_key
                or os.environ.get("XAI_API_KEY")
                or os.environ.get("GROK_API_KEY")
            )
            grok_client = GrokClient(config.grok) if api_key else None
            storage = Path.home() / ".grok-harness" / "scheduler"
            scheduler = SmartScheduler(
                grok_client=grok_client,
                storage_path=storage,
                enable_learning=bool(grok_client),
                enable_predictive=True,
                enable_monitoring=True,
            )
            await scheduler.start()

        if args.command == "agent":
            await run_agent(args, config)

        elif args.command == "schedule":
            if scheduler is None:
                print_error("Scheduler not initialized")
                return 1
            await run_schedule_command(args, config, scheduler)

        elif args.command == "jobs":
            if scheduler is None:
                print_error("Scheduler not initialized")
                return 1
            await run_jobs_command(args, scheduler)

        elif args.command == "memory":
            await run_memory_command(args, config)

        elif args.command == "monitor":
            if scheduler is None:
                print_error("Scheduler not initialized")
                return 1
            await run_monitor_command(args, scheduler)

        elif args.command == "config":
            await run_config_command(args, config)

        elif args.command == "interactive":
            interactive = InteractiveMode(config)
            await interactive.run()

        elif args.command == "run":
            await run_run_command(args, config)

    finally:
        if scheduler is not None:
            await scheduler.stop()
        if grok_client is not None and hasattr(grok_client, "__aexit__"):
            await grok_client.__aexit__(None, None, None)

    return 0


def main() -> None:
    """Main entry point."""
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Error: {e}")
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
