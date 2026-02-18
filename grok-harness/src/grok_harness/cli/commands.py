"""CLI commands for Grok-Harness."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from ..browser.agent import GrokBrowserAgent
from ..core.config_manager import ConfigManager
from ..utils.errors import BrowserError
from ..core.grok_client import GrokClient
from ..core.providers import get_llm_client_from_config, get_provider, get_provider_names
from ..core.orchestrator import Orchestrator, RunOptions, RunResult
from ..core.types import BrowserConfig, FullConfig, GrokConfig
from ..memory.models import MemoryItemType
from ..memory.unified import UnifiedMemory
from ..scheduler.models import JobPriority
from ..scheduler.smart import SmartScheduler
from .interactive import InteractiveMode
from .output import (
    _safe_str,
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
  grok-harness weather Pensacola
  grok-harness time
  grok-harness chat "What is the weather?" --name Assistant
  grok-harness schedule add "0 9 * * *" "agent daily report" --name "Daily Report"
  grok-harness memory search "prices" --semantic
  grok-harness monitor health
  grok-harness interactive    Interactive mode with chat, agent, schedule
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

    # Onboard command
    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Onboarding wizard",
    )
    onboard_subparsers = onboard_parser.add_subparsers(
        dest="onboard_command",
        help="Onboarding steps",
        required=True,
    )
    onboard_llm = onboard_subparsers.add_parser(
        "llm",
        help="Configure LLM provider (Grok, Claude, etc.)",
    )
    onboard_llm.add_argument(
        "--provider",
        type=str,
        choices=get_provider_names(),
        default="grok",
        help="Provider to configure",
    )
    onboard_llm.add_argument(
        "--api-key",
        type=str,
        help="API key (or set via env var)",
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
        help="Configuration key (e.g., grok.model, llm.primary, llm.api_keys.grok)",
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

    setup_parser = subparsers.add_parser(
        "setup",
        help="Run interactive setup wizard",
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

    # Chat command
    chat_parser = subparsers.add_parser(
        "chat",
        help="Have a conversation with a named agent",
    )
    chat_parser.add_argument(
        "message",
        type=str,
        nargs="*",
        help="Optional initial message; omit to start loop directly",
    )
    chat_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Agent name (default: Assistant); 'chat MyBot' uses MyBot as name",
    )
    chat_parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Single message only, no interactive loop",
    )

    # Weather shortcut
    weather_parser = subparsers.add_parser(
        "weather",
        help="Quick weather check (no browser, no API key)",
    )
    weather_parser.add_argument(
        "location",
        type=str,
        nargs="?",
        default="",
        help="Location (e.g. Pensacola, London)",
    )
    weather_parser.add_argument(
        "--forecast",
        "-f",
        action="store_true",
        help="Show 3-day forecast",
    )

    # Time command
    subparsers.add_parser(
        "time",
        help="Show current local time and optional timezone",
    )

    # Date command
    subparsers.add_parser(
        "date",
        help="Get the verified current date",
    )

    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a website and get content-based insights",
    )
    analyze_parser.add_argument(
        "url",
        type=str,
        help="URL to analyze",
    )
    analyze_parser.add_argument(
        "--deep",
        action="store_true",
        help="Perform deep analysis (reserved for future use)",
    )

    # News command
    news_parser = subparsers.add_parser(
        "news",
        help="Get current news and headlines",
    )
    news_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of headlines to show",
    )

    # Session command group (multi-agent)
    session_parser = subparsers.add_parser(
        "session",
        help="Manage agent sessions (multi-agent)",
    )
    session_subparsers = session_parser.add_subparsers(
        dest="session_command",
        help="Session commands",
        required=True,
    )

    session_subparsers.add_parser(
        "list",
        help="List active sessions",
    )

    session_create = session_subparsers.add_parser(
        "create",
        help="Create a new agent session",
    )
    session_create.add_argument(
        "--name",
        type=str,
        required=True,
        help="Agent name",
    )
    session_create.add_argument(
        "--soul",
        type=str,
        help="Soul prompt for the agent",
    )
    session_create.add_argument(
        "--parent",
        type=str,
        help="Parent session ID",
    )

    session_send = session_subparsers.add_parser(
        "send",
        help="Send message to a session",
    )
    session_send.add_argument(
        "session_id",
        type=str,
        help="Target session ID",
    )
    session_send.add_argument(
        "message",
        type=str,
        nargs="+",
        help="Message to send",
    )

    session_terminate = session_subparsers.add_parser(
        "terminate",
        help="Terminate a session",
    )
    session_terminate.add_argument(
        "session_id",
        type=str,
        help="Session ID to terminate",
    )

    # Heartbeat command group
    heartbeat_parser = subparsers.add_parser(
        "heartbeat",
        help="Manage agent heartbeats (proactive behavior)",
    )
    heartbeat_subparsers = heartbeat_parser.add_subparsers(
        dest="heartbeat_command",
        help="Heartbeat commands",
        required=True,
    )

    heartbeat_start = heartbeat_subparsers.add_parser(
        "start",
        help="Start heartbeat engine",
    )
    heartbeat_start.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds (default: 1800)",
    )

    heartbeat_subparsers.add_parser(
        "stop",
        help="Stop heartbeat engine",
    )

    heartbeat_subparsers.add_parser(
        "status",
        help="Show heartbeat status",
    )

    heartbeat_config = heartbeat_subparsers.add_parser(
        "config",
        help="Configure heartbeat for a session",
    )
    heartbeat_config.add_argument(
        "session_id",
        type=str,
        help="Session ID",
    )
    heartbeat_config.add_argument(
        "--enable",
        action="store_true",
        help="Enable heartbeat",
    )
    heartbeat_config.add_argument(
        "--disable",
        action="store_true",
        help="Disable heartbeat",
    )
    heartbeat_config.add_argument(
        "--task",
        type=str,
        help="Custom heartbeat task prompt",
    )

    # Status command
    subparsers.add_parser(
        "status",
        help="Show system status (sessions, heartbeat, memory)",
    )

    # Daemon command
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Run GrokClaw daemon (sessions + heartbeat)",
    )
    daemon_parser.add_argument(
        "--config",
        type=str,
        help="Path to config file",
    )

    # Telegram command group
    telegram_parser = subparsers.add_parser(
        "telegram",
        help="Telegram integration",
    )
    telegram_subparsers = telegram_parser.add_subparsers(
        dest="telegram_command",
        help="Telegram commands",
        required=True,
    )

    telegram_onboard = telegram_subparsers.add_parser(
        "onboard",
        help="Configure Telegram bot",
    )
    telegram_onboard.add_argument(
        "--token",
        type=str,
        required=True,
        help="Bot token from @BotFather",
    )
    telegram_onboard.add_argument(
        "--chat-id",
        type=str,
        help="Default chat ID for notifications",
    )
    telegram_onboard.add_argument(
        "--no-encrypt",
        action="store_true",
        help="Disable token encryption (not recommended)",
    )

    telegram_test = telegram_subparsers.add_parser(
        "test",
        help="Test Telegram connection",
    )
    telegram_test.add_argument(
        "--message",
        type=str,
        default="Hello from GrokClaw!",
        help="Test message to send",
    )

    telegram_subparsers.add_parser(
        "status",
        help="Show Telegram status",
    )

    telegram_listen = telegram_subparsers.add_parser(
        "listen",
        help="Start Telegram listener (inbound messages)",
    )
    telegram_listen.add_argument(
        "--daemon",
        action="store_true",
        help="Run as daemon",
    )

    return parser


_chat_sessions: Dict[str, Any] = {}


async def run_chat(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Run chat mode with named agent."""
    from ..agent.named_agent import NamedAgent

    msg_parts = getattr(args, "message", []) or []
    # "chat Assistant" => name=Assistant, no message; "chat hi" => message="hi", name=Assistant
    if len(msg_parts) == 1 and not getattr(args, "name", None):
        single = msg_parts[0]
        if single[0].isupper() and len(single) < 20 and single.isalpha():
            name = single
            message = ""
        else:
            name = "Assistant"
            message = single
    else:
        name = getattr(args, "name", None) or "Assistant"
        message = " ".join(msg_parts)
    no_loop = getattr(args, "no_loop", False)

    llm_client = _get_llm_client(config)
    if llm_client:
        await llm_client.__aenter__()

    session_key = f"chat_{name}"
    if session_key in _chat_sessions:
        agent = _chat_sessions[session_key]
        console.print(f"[dim]Resuming chat with {name}...[/]")
    else:
        agent = NamedAgent(name=name, grok=llm_client)
        # Detect text-only mode if browser/Playwright unavailable
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()
        except Exception:
            agent.text_only_mode = True
        _chat_sessions[session_key] = agent
        console.print(f"\n[bold cyan]Chatting with {name}[/]")
        current_date = agent.get_current_date()
        if agent.user_provided_date:
            console.print(f"[dim]Current date: {current_date} (from previous session)[/]")
        else:
            console.print(f"[dim]Current date: {current_date} (system time)[/]")
        console.print(
            "[dim]Type /exit to quit, /reset to reset conversation, "
            "/setdate <date> to change date[/]\n"
        )

    try:
        if message:
            console.print(f"[bold green]You:[/] {message}")
            response = await agent.chat(message)
            console.print(response)
        elif no_loop:
            console.print("[dim]No message. Use 'chat \"hi\"' or 'chat Assistant' to start[/]")
            return

        if not no_loop:
            if not message:
                console.print("[dim]Type your message and press Enter.[/]")
            while True:
                try:
                    user_input = Prompt.ask(f"\n[bold green]You[/]")
                    if not user_input:
                        continue
                    if user_input.lower() == "/exit":
                        break
                    if user_input.lower() == "/reset":
                        await agent.reset_conversation()
                        agent.user_provided_date = None
                        agent.date_confirmed = False
                        agent._save_memory()
                        console.print("[dim]Conversation reset[/]")
                        continue
                    response = await agent.chat(user_input)
                    console.print(response)
                except (KeyboardInterrupt, EOFError):
                    break
    finally:
        if llm_client:
            await llm_client.__aexit__(None, None, None)


async def run_weather(args: argparse.Namespace) -> None:
    """Quick weather check."""
    from ..tools.weather import WeatherTool

    location = (getattr(args, "location", None) or "").strip()
    if not location:
        location = "Pensacola"
    forecast = getattr(args, "forecast", False)

    if forecast:
        result = await WeatherTool.get_forecast(location, 3)
    else:
        result = await WeatherTool.get_current(location)

    if result.get("success"):
        console.print(_safe_str(result["data"]))
    else:
        print_error(f"Weather error: {result.get('error', 'Unknown')}")


async def run_analyze(
    args: argparse.Namespace,
) -> None:
    """Run site analysis."""
    from ..tools.site_analyzer import SiteAnalyzer

    url = getattr(args, "url", "").strip()
    if not url:
        print_error("Please provide a URL")
        return

    print_info(f"Analyzing {url}...")
    result = await SiteAnalyzer.analyze(url)

    if "error" in result:
        print_error(result["error"])
        return

    print_header("Site Analysis Results")
    console.print(f"[bold]URL:[/] {result['url']}")
    console.print(f"[bold]Title:[/] {_safe_str(result['title'])}")
    console.print(f"[bold]Description:[/] {_safe_str(result['description'][:200])}")

    print_header("Headlines")
    for level, headlines in result.get("headlines", {}).items():
        if headlines:
            console.print(f"[bold]{level.upper()}:[/]")
            for h in headlines[:3]:
                console.print(f"  - {_safe_str(h)}")

    if result.get("key_messages"):
        print_header("Key Messages")
        for msg in result["key_messages"][:5]:
            console.print(f"  - {_safe_str(msg)}")

    print_header("Purpose Detection")
    purpose = result["purpose_detection"]
    console.print(f"[bold]Primary:[/] {purpose['primary']}")
    console.print(f"[bold]Confidence:[/] {purpose['confidence']*100:.0f}%")


async def run_session_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
    session_manager: Any,
) -> None:
    """Handle session commands."""
    if args.session_command == "list":
        sessions = session_manager.list_sessions()
        if sessions:
            table = Table(title="Active Agent Sessions")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Messages", style="blue")
            table.add_column("Parent", style="magenta")
            for s in sessions:
                table.add_row(
                    s["session_id"],
                    s["name"],
                    s["status"],
                    str(s["message_count"]),
                    s["parent"] or "-",
                )
            console.print(table)
        else:
            print_info("No active sessions")

    elif args.session_command == "create":
        soul = args.soul or f"You are a {args.name} agent. Be helpful and professional."
        try:
            session_id = await session_manager.create_session(
                name=args.name,
                soul_prompt=soul,
                parent_session_id=getattr(args, "parent", None),
            )
            print_success(f"Created session: {session_id} ({args.name})")
        except Exception as e:
            print_error(f"Failed to create session: {e}")

    elif args.session_command == "send":
        message = " ".join(args.message)
        try:
            result = await session_manager.send_message(args.session_id, message)
            if result.get("success"):
                res = result.get("result")
                if isinstance(res, dict):
                    console.print(
                        f"[bold green]{result['agent_name']}:[/] "
                        f"{_safe_str(res.get('result', res))}"
                    )
                else:
                    console.print(
                        f"[bold green]{result['agent_name']}:[/] {_safe_str(res)}"
                    )
            else:
                print_error(result.get("error", "Unknown error"))
        except ValueError as e:
            print_error(str(e))
        except Exception as e:
            print_error(f"Send failed: {e}")

    elif args.session_command == "terminate":
        try:
            success = await session_manager.terminate_session(args.session_id)
            if success:
                print_success(f"Session {args.session_id} terminated")
            else:
                print_error(f"Session {args.session_id} not found")
        except Exception as e:
            print_error(f"Terminate failed: {e}")


async def run_heartbeat_command(
    args: argparse.Namespace,
    session_manager: Any,
    heartbeat_engine: Any,
) -> None:
    """Handle heartbeat commands."""
    if args.heartbeat_command == "start":
        if hasattr(args, "interval") and args.interval:
            heartbeat_engine.config.interval_seconds = args.interval
        await heartbeat_engine.start()
        print_success(
            f"Heartbeat engine started (interval: {heartbeat_engine.config.interval_seconds}s)"
        )

    elif args.heartbeat_command == "stop":
        await heartbeat_engine.stop()
        print_success("Heartbeat engine stopped")

    elif args.heartbeat_command == "status":
        stats = heartbeat_engine.get_stats()
        console.print("[bold]Heartbeat Status:[/]")
        console.print(f"  Running: {stats['running']}")
        console.print(f"  Total heartbeats: {stats['total_heartbeats']}")
        console.print(f"  Sessions monitored: {stats['sessions_monitored']}")
        if stats.get("last_heartbeats"):
            console.print("\n[bold]Last heartbeats:[/]")
            for sid, ts in list(stats["last_heartbeats"].items())[:5]:
                console.print(f"  {sid}: {ts}")

    elif args.heartbeat_command == "config":
        session = session_manager.get_session(args.session_id)
        if not session:
            print_error(f"Session {args.session_id} not found")
            return
        if args.enable:
            session.heartbeat_enabled = True
            print_success(f"Heartbeat enabled for session {args.session_id}")
        if args.disable:
            session.heartbeat_enabled = False
            print_success(f"Heartbeat disabled for session {args.session_id}")
        if getattr(args, "task", None):
            session.heartbeat_task = args.task
            print_success(f"Heartbeat task set for session {args.session_id}")


async def run_status_command(
    args: argparse.Namespace,
    session_manager: Any,
    heartbeat_engine: Optional[Any],
) -> None:
    """Show system status."""
    print_header("GrokClaw System Status")

    sessions = session_manager.list_sessions()
    console.print(f"[bold]Active Sessions:[/] {len(sessions)}")
    for s in sessions[:5]:
        console.print(f"  - {s['name']} ({s['session_id']}) - {s['status']}")

    if heartbeat_engine:
        hb_stats = heartbeat_engine.get_stats()
        status_str = "Running" if hb_stats["running"] else "Stopped"
        console.print(f"\n[bold]Heartbeat:[/] {status_str}")
        console.print(f"  Total heartbeats: {hb_stats['total_heartbeats']}")

        telegram_notifier = getattr(heartbeat_engine, "telegram_notifier", None)
    else:
        telegram_notifier = None

    tg_config_path = Path.home() / ".grok-harness" / "telegram.json"
    if tg_config_path.exists() or telegram_notifier:
        if telegram_notifier:
            console.print("\n[bold]Telegram:[/] Connected")
            tg_stats = telegram_notifier.get_stats()
            console.print(f"  Messages sent: {tg_stats.get('messages_sent', 0)}")
            console.print(f"  Queue size: {tg_stats.get('queue_size', 0)}")
        else:
            console.print("\n[bold]Telegram:[/] Configured (run daemon to connect)")

    if session_manager.sessions:
        first_session = list(session_manager.sessions.values())[0]
        try:
            memory_stats = await first_session.memory.get_stats()
            console.print("\n[bold]Memory:[/]")
            console.print(f"  Total items: {memory_stats.get('total_items', 0)}")
        except Exception:
            pass

    console.print("\n[bold]Queue:[/] 0 pending")


async def run_telegram_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Handle Telegram commands."""
    from pathlib import Path as PathLib

    config_path = PathLib.home() / ".grok-harness" / "telegram.json"

    if args.telegram_command == "onboard":
        from ..messaging.telegram_outbound import TelegramNotifier
        from ..utils.encryption import encrypt_value

        notifier = TelegramNotifier(
            bot_token=args.token,
            default_chat_id=getattr(args, "chat_id", None),
            encrypt_token=not getattr(args, "no_encrypt", False),
        )
        try:
            await notifier.initialize()
            print_success("Telegram connection successful!")

            save_data: Dict[str, Any] = {
                "default_chat_id": getattr(args, "chat_id", None),
                "encrypt": not getattr(args, "no_encrypt", False),
            }
            if not getattr(args, "no_encrypt", False):
                save_data["bot_token"] = encrypt_value(args.token)
                save_data["encrypted"] = True
            else:
                save_data["bot_token"] = args.token
                save_data["encrypted"] = False

            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(save_data, f, indent=2)
            print_success(f"Telegram configuration saved to {config_path}")

            if getattr(args, "chat_id", None):
                await notifier.send_message(
                    text="GrokClaw Telegram integration configured successfully!",
                    chat_id=args.chat_id,
                )
                await asyncio.sleep(1)
                print_success("Test message sent!")
        except Exception as e:
            print_error(f"Telegram configuration failed: {e}")
        finally:
            await notifier.shutdown()

    elif args.telegram_command == "test":
        if not config_path.exists():
            print_error(
                "Telegram not configured. Run 'grok-harness telegram onboard' first."
            )
            return
        with open(config_path) as f:
            telegram_config = json.load(f)
        from ..utils.encryption import decrypt_value
        from ..messaging.telegram_outbound import TelegramNotifier

        token = telegram_config["bot_token"]
        if telegram_config.get("encrypted"):
            token = decrypt_value(token)
        notifier = TelegramNotifier(
            bot_token=token,
            default_chat_id=telegram_config.get("default_chat_id"),
            encrypt_token=False,
        )
        await notifier.initialize()
        msg = getattr(args, "message", "Hello from GrokClaw!")
        success = await notifier.send_message(
            text=msg,
            chat_id=telegram_config.get("default_chat_id"),
        )
        await asyncio.sleep(1)
        if success:
            print_success("Test message queued/sent!")
        else:
            print_error("Failed to send test message")
        await notifier.shutdown()

    elif args.telegram_command == "status":
        if not config_path.exists():
            print_error("Telegram not configured")
            return
        with open(config_path) as f:
            telegram_config = json.load(f)
        from ..utils.encryption import decrypt_value
        from ..messaging.telegram_outbound import TelegramNotifier

        token = telegram_config["bot_token"]
        if telegram_config.get("encrypted"):
            token = decrypt_value(token)
        notifier = TelegramNotifier(
            bot_token=token,
            default_chat_id=telegram_config.get("default_chat_id"),
            encrypt_token=False,
        )
        await notifier.initialize()
        stats = notifier.get_stats()
        print_header("Telegram Status")
        console.print(f"Default Chat ID: {telegram_config.get('default_chat_id')}")
        console.print(f"Encrypted: {telegram_config.get('encrypted', False)}")
        console.print(f"Messages Sent: {stats.get('messages_sent', 0)}")
        console.print(f"Messages Failed: {stats.get('messages_failed', 0)}")
        console.print(f"Queue Size: {stats.get('queue_size', 0)}")
        if stats.get("last_message_time"):
            console.print(f"Last Message: {stats['last_message_time']}")
        await notifier.shutdown()

    elif args.telegram_command == "listen":
        if not config_path.exists():
            print_error(
                "Telegram not configured. Run 'grok-harness telegram onboard' first."
            )
            return
        with open(config_path) as f:
            telegram_config = json.load(f)
        from ..utils.encryption import decrypt_value
        from ..messaging.telegram_outbound import TelegramNotifier
        from ..core.session_manager import SessionManager

        token = telegram_config["bot_token"]
        if telegram_config.get("encrypted"):
            token = decrypt_value(token)

        grok_client = _get_llm_client(config)
        if not grok_client:
            print_error("Listen requires LLM API key (XAI_API_KEY or ANTHROPIC_API_KEY)")
            return

        await grok_client.__aenter__()

        session_manager = SessionManager(config, grok_client)
        notifier = TelegramNotifier(
            bot_token=token,
            default_chat_id=telegram_config.get("default_chat_id"),
            encrypt_token=False,
        )
        await notifier.initialize()
        listener = notifier.create_listener(
            session_manager=session_manager,
            default_session_id=None,
        )
        print_success("Telegram listener started. Press Ctrl+C to stop.")
        await listener.start()
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await listener.stop()
            await notifier.shutdown()
            await grok_client.__aexit__(None, None, None)


async def run_news(args: argparse.Namespace) -> None:
    """Get current news headlines."""
    from datetime import datetime

    from ..tools.current_events import CurrentEventsTool

    limit = getattr(args, "limit", 5) or 5
    news = await CurrentEventsTool.get_current_news(limit=limit)

    if news:
        print_header(
            f"Current Headlines (as of {datetime.now().strftime('%B %d, %Y')})"
        )
        for i, item in enumerate(news, 1):
            console.print(f"{i}. [bold]{_safe_str(item['title'])}[/]")
            if item.get("url"):
                console.print(f"   [dim]{item['source']} - {item['url']}[/]")
        console.print()
    else:
        print_warning("Could not fetch current news")


async def run_date(args: argparse.Namespace) -> None:
    """Get verified current date."""
    from ..tools.current_events import CurrentEventsTool

    date_info = await CurrentEventsTool.get_current_date()

    if date_info["success"]:
        print_success(f"Verified Current Date: {date_info['date']}")
        print_info(f"Source: {date_info['source']}")
        if date_info.get("warning"):
            print_warning(date_info["warning"])
    else:
        print_error("Could not verify current date")


async def run_time_command() -> None:
    """Show current time with optional timezone."""
    from datetime import datetime

    tz_name = os.environ.get("TZ", "local")
    if tz_name != "local":
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()
            tz_name = "local"
    else:
        now = datetime.now()

    console.print(f"[bold]Local time:[/] {now.strftime('%Y-%m-%d %H:%M:%S')}")
    if tz_name != "local":
        console.print(f"[dim]Timezone: {tz_name}[/]")
    console.print("[dim]Set TZ for timezone (e.g. TZ=America/New_York)[/]")


def _get_llm_client(config: Union[FullConfig, Dict[str, Any]]) -> Any:
    """Create LLM client from config (Grok, Claude, etc.). Returns client or None on error."""
    try:
        return get_llm_client_from_config(config)
    except (ValueError, ImportError):
        return None


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
        browser_config = config.browser
    else:
        browser_config = BrowserConfig()

    llm_client = _get_llm_client(config)
    if not llm_client:
        primary = getattr(getattr(config, "llm", None), "primary", "grok")
        print_error(
            f"No API key for {primary}. Set XAI_API_KEY, ANTHROPIC_API_KEY, "
            "or configure llm.api_keys in config."
        )
        return

    await llm_client.__aenter__()

    if args.headless:
        browser_config.headless = True
    # Show Playwright install messages when running agent from CLI
    browser_config.verbose_playwright_setup = True

    memory_config = config.memory if isinstance(config, FullConfig) else ConfigManager.create_default_config().memory
    memory = UnifiedMemory(memory_config)
    await memory.start()

    scheduler = SmartScheduler(
        grok_client=llm_client,
        enable_learning=bool(llm_client),
        enable_predictive=True,
        enable_monitoring=False,
    )
    await scheduler.start()

    orchestrator = Orchestrator(config, llm_client, memory, scheduler)

    opts = RunOptions(
        interactive=args.interactive,
        max_steps=args.max_steps,
        live_progress=not getattr(args, "no_live", False),
        verbose=getattr(args, "verbose", False),
        dry_run=getattr(args, "dry_run", False),
    )

    try:
        await _run_agent_inner(args, config, llm_client, memory, scheduler, opts)
    except BrowserError as e:
        if "Playwright" in str(e):
            print_warning("Browser automation needs setup")
            answer = Prompt.ask(
                "Would you like to install Playwright now?",
                choices=["y", "n"],
                default="y",
            )
            if answer == "y":
                print_info("📦 Installing Playwright...")
                try:
                    subprocess.check_call(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "playwright>=1.40.0",
                        ]
                    )
                    subprocess.check_call(
                        [
                            sys.executable,
                            "-m",
                            "playwright",
                            "install",
                            "chromium",
                        ]
                    )
                    print_success("Playwright installed! Please try again.")
                except subprocess.CalledProcessError as install_err:
                    print_error(f"Install failed: {install_err}")
                    print_info("You can install manually with: playwright install chromium")
            else:
                print_info("You can install manually with: playwright install chromium")
        else:
            print_error(f"Browser error: {e}")
    finally:
        await scheduler.stop()
        await memory.stop()
        await llm_client.__aexit__(None, None, None)


async def _run_agent_inner(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
    llm_client: Any,
    memory: Any,
    scheduler: SmartScheduler,
    opts: RunOptions,
) -> None:
    """Inner run_agent logic (extracted for Playwright error handling)."""
    orchestrator = Orchestrator(config, llm_client, memory, scheduler)
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
        # Minimal progress when --no-live
        def _minimal_progress(
            step_num: int = 0,
            total: int = 0,
            action: str = "",
            status: str = "running",
            **kwargs: Any,
        ) -> None:
            if step_num and total:
                sym = "[OK]" if status == "success" else "[X]" if status == "error" else "..."
                console.print(f"  Step {step_num}/{total}: {action} {sym}")

        orchestrator.set_progress_callback(_minimal_progress)
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
                    console.print(f"  {key}: {_safe_str(value)}")
        else:
            console.print(f"  {_safe_str(res)}")

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

    llm_client = _get_llm_client(config)
    if not llm_client:
        print_error("No LLM API key. Set XAI_API_KEY, ANTHROPIC_API_KEY, or configure.")
        return

    await llm_client.__aenter__()

    memory = UnifiedMemory(config.memory if isinstance(config, FullConfig) else ConfigManager.create_default_config().memory)
    await memory.start()

    scheduler = SmartScheduler(
        grok_client=llm_client,
        enable_learning=True,
        enable_predictive=True,
        enable_monitoring=False,
    )
    await scheduler.start()

    orchestrator = Orchestrator(config, llm_client, memory, scheduler)
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
        await llm_client.__aexit__(None, None, None)


async def run_onboard_command(
    args: argparse.Namespace,
    config: Union[FullConfig, Dict[str, Any]],
) -> None:
    """Handle onboard commands."""
    from ..core.types import LLMConfig

    if args.onboard_command != "llm":
        return

    provider = getattr(args, "provider", "grok")
    api_key = getattr(args, "api_key", None)
    prov = get_provider(provider)
    env_var = prov.env_var if prov else "XAI_API_KEY"
    if not api_key:
        api_key = os.environ.get(env_var)
    if not api_key:
        print_error(
            f"Provide --api-key or set {env_var}. "
            "Get keys from x.ai (Grok) or console.anthropic.com (Claude)."
        )
        return

    if isinstance(config, FullConfig):
        if not config.llm:
            config.llm = LLMConfig()
        config.llm.primary = provider
        if not config.llm.api_keys:
            config.llm.api_keys = {}
        config.llm.api_keys[provider] = api_key
        config_path = Path.home() / ".grok-harness" / "config.yaml"
        ConfigManager.save_config(config, config_path)
        print_success(f"Configured {provider} as primary LLM. Saved to {config_path}")
        llm_client = _get_llm_client(config)
        if llm_client:
            await llm_client.__aenter__()
            try:
                r = await llm_client.chat_completion(
                    [{"role": "user", "content": "Say OK if you can hear me."}],
                    max_tokens=10,
                )
                content = r["choices"][0]["message"]["content"]
                if "ok" in content.lower():
                    print_success("Connection test passed!")
                else:
                    print_info(f"Response: {content[:80]}")
            finally:
                await llm_client.__aexit__(None, None, None)
    else:
        print_error("Config format not supported for onboard")


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
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                print_error(f"Invalid key: {args.key}")
                return
            if current is None:
                print_error(f"Invalid key: {args.key}")
                return

        last_part = parts[-1]
        if isinstance(current, dict):
            current_val = current.get(last_part)
        else:
            current_val = getattr(current, last_part, None)

        if isinstance(current_val, bool):
            value: Any = args.value.lower() in ["true", "yes", "1"]
        elif isinstance(current_val, int):
            value = int(args.value)
        elif isinstance(current_val, float):
            value = float(args.value)
        else:
            value = args.value

        if isinstance(current, dict):
            current[last_part] = value
        else:
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
            grok_client = _get_llm_client(config)
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

        elif args.command == "onboard":
            await run_onboard_command(args, config)

        elif args.command == "setup":
            from .setup_wizard import SetupWizard

            wizard = SetupWizard()
            await wizard.run()

        elif args.command == "config":
            await run_config_command(args, config)

        elif args.command == "interactive":
            interactive = InteractiveMode(config)
            await interactive.run()

        elif args.command == "run":
            await run_run_command(args, config)

        elif args.command == "chat":
            await run_chat(args, config)

        elif args.command == "weather":
            await run_weather(args)

        elif args.command == "date":
            await run_date(args)

        elif args.command == "time":
            await run_time_command()

        elif args.command == "analyze":
            await run_analyze(args)

        elif args.command == "news":
            await run_news(args)

        elif args.command == "heartbeat":
            from ..core.session_manager import SessionManager
            from ..core.heartbeat import HeartbeatEngine, HeartbeatConfig

            grok_for_sm = _get_llm_client(config)
            if grok_for_sm:
                await grok_for_sm.__aenter__()

            session_manager = SessionManager(config, grok_for_sm)
            heartbeat_engine = HeartbeatEngine(session_manager)

            if args.heartbeat_command == "start":
                if getattr(args, "interval", None):
                    heartbeat_engine.config.interval_seconds = args.interval
                await heartbeat_engine.start()
                print_success(
                    f"Heartbeat engine started "
                    f"(interval: {heartbeat_engine.config.interval_seconds}s)"
                )
                print_info("Press Ctrl+C to stop")
                try:
                    while True:
                        await asyncio.sleep(60)
                except KeyboardInterrupt:
                    await heartbeat_engine.stop()
                    print_info("Heartbeat stopped")
            else:
                await run_heartbeat_command(args, session_manager, heartbeat_engine)

            if grok_for_sm:
                await grok_for_sm.__aexit__(None, None, None)

        elif args.command == "status":
            from ..core.session_manager import SessionManager
            from ..core.heartbeat import HeartbeatEngine

            session_manager = SessionManager(config, None)
            heartbeat_engine = HeartbeatEngine(session_manager)
            await run_status_command(args, session_manager, heartbeat_engine)

        elif args.command == "telegram":
            await run_telegram_command(args, config)

        elif args.command == "daemon":
            from ..daemon import GrokClawDaemon

            config_path = getattr(args, "config", None)
            daemon = GrokClawDaemon(config_path=config_path)
            print_info("Starting GrokClaw daemon (Ctrl+C to stop)...")
            await daemon.run()

        elif args.command == "session":
            from ..core.session_manager import SessionManager

            llm_client_check = _get_llm_client(config)
            needs_llm = args.session_command in ("create", "send")
            if needs_llm and not llm_client_check:
                print_error(
                    "Session create/send requires Grok API key. "
                    "Set XAI_API_KEY or configure in config."
                )
                return 1

            if llm_client_check and grok_client is None:
                grok_client = llm_client_check
                await grok_client.__aenter__()

            session_manager = SessionManager(config, grok_client)
            await run_session_command(args, config, session_manager)

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
