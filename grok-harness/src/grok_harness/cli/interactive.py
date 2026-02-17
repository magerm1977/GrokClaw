"""Interactive REPL mode for Grok-Harness."""

from typing import Any, Dict, List, Optional, Union

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ..browser.agent import GrokBrowserAgent
from ..core.config_manager import ConfigManager
from ..core.grok_client import GrokClient
from ..core.types import FullConfig
from ..memory.unified import UnifiedMemory
from ..scheduler.smart import SmartScheduler
from .output import (
    console,
    print_error,
    print_header,
    print_info,
    print_job_table,
    print_success,
    print_system_health,
)


class InteractiveMode:
    """Interactive REPL for Grok-Harness."""

    def __init__(self, config: Union[FullConfig, Dict[str, Any]]) -> None:
        self.config = config
        self.grok: Optional[GrokClient] = None
        self.scheduler: Optional[SmartScheduler] = None
        self.memory: Optional[UnifiedMemory] = None
        self.running = True
        self.mode = "command"
        self.chat_agent = None

        self.commands = {
            "help": self.show_help,
            "exit": self.exit,
            "quit": self.exit,
            "agent": self.run_agent,
            "analyze": self.run_analyze,
            "chat": self._handle_chat_mode,
            "schedule": self.schedule_job,
            "jobs": self.list_jobs,
            "memory": self.search_memory,
            "health": self.show_health,
            "stats": self.show_stats,
            "clear": self.clear_screen,
        }

    async def run(self) -> None:
        """Run interactive mode."""
        print_header("Grok-Harness Interactive Mode")
        print_info("Type 'help' for commands, 'exit' to quit")

        if isinstance(self.config, FullConfig):
            api_key = (
                self.config.grok.api_key
                or __import__("os").environ.get("XAI_API_KEY")
                or __import__("os").environ.get("GROK_API_KEY")
            )
            if api_key:
                self.grok = GrokClient(self.config.grok)
                await self.grok.__aenter__()

            self.memory = UnifiedMemory(self.config.memory)
            await self.memory.start()

            self.scheduler = SmartScheduler(
                grok_client=self.grok,
                enable_learning=bool(self.grok),
                enable_predictive=True,
                enable_monitoring=True,
            )
            await self.scheduler.start()
        else:
            from ..core.types import MemoryConfig

            self.memory = UnifiedMemory(MemoryConfig())
            await self.memory.start()
            self.scheduler = SmartScheduler(
                grok_client=None,
                enable_learning=False,
                enable_predictive=True,
                enable_monitoring=True,
            )
            await self.scheduler.start()

        try:
            while self.running:
                try:
                    command = Prompt.ask("\n[bold cyan]grok>[/]")
                    await self.process_command(command.strip())
                except KeyboardInterrupt:
                    print_info("\nUse 'exit' to quit")
                except Exception as e:
                    print_error(f"Error: {e}")
        finally:
            await self.cleanup()

    async def process_command(self, command_line: str) -> None:
        """Process a command line."""
        if not command_line:
            return

        if self.mode == "chat":
            if command_line.strip().lower() == "/exit":
                self.mode = "command"
                print_info("Returned to command mode")
                return
            if self.chat_agent:
                response = await self.chat_agent.chat(command_line)
                console.print(response)
            return

        parts = command_line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in self.commands:
            handler = self.commands[cmd]
            if cmd == "exit" or cmd == "quit":
                handler(args)
            elif cmd == "clear":
                handler(args)
            else:
                await handler(args)
        else:
            print_error(f"Unknown command: {cmd}")
            print_info("Type 'help' for available commands, or 'chat [name]' to chat")

    async def show_help(self, args: List[str]) -> None:
        """Show help."""
        help_text = """
[bold cyan]Available Commands:[/]

[bold]agent [goal][/] - Run browser agent
  Example: agent "Get weather in London"

[bold]schedule [cron] [command][/] - Schedule a job
  Example: schedule "0 9 * * *" agent "Daily report"

[bold]jobs[/] - List recent jobs
[bold]jobs [job_id][/] - Show job details

[bold]memory [query][/] - Search memory
  Example: memory "product prices"

[bold]health[/] - Show system health
[bold]stats[/] - Show statistics
[bold]analyze [url][/] - Analyze a website
  Example: analyze https://coachframe.io
[bold]chat [name][/] - Chat with named agent (use /exit to return)
  Example: chat Fred
[bold]clear[/] - Clear screen
[bold]exit[/] - Exit interactive mode
        """
        console.print(Panel(help_text.strip(), title="Help", border_style="blue"))

    async def _handle_chat_mode(self, args: List[str]) -> None:
        """Switch to chat mode with named agent."""
        from ..agent.named_agent import NamedAgent

        name = args[0] if args else "Fred"
        self.chat_agent = NamedAgent(
            name=name,
            grok=self.grok,
            memory=self.memory,
        )
        self.mode = "chat"
        print_info(f"Switched to chat mode with {name}")
        console.print("[dim]Type messages naturally. Use /exit to return to command mode.[/]")

    async def run_agent(self, args: List[str]) -> None:
        """Run browser agent."""
        if not args:
            print_error("Please provide a goal")
            return

        goal = " ".join(args)

        if not self.grok:
            print_error("Grok client not initialized (no API key?)")
            return

        if isinstance(self.config, FullConfig):
            system_info = self.config.system
            browser_config = self.config.browser
        else:
            system_info = ConfigManager.detect_system_info()
            from ..core.types import BrowserConfig

            browser_config = BrowserConfig()

        async with GrokBrowserAgent(
            self.grok, browser_config, system_info
        ) as agent:
            print_info(f"Running agent: {goal}")

            result = await agent.run_task(
                goal=goal,
                interactive=True,
            )

            print_success("Task completed!")
            console.print(f"Steps taken: {result.steps_taken}")
            console.print(f"Duration: {result.duration_ms / 1000:.2f}s")

            if result.results:
                console.print("\n[bold]Results:[/]")
                for key, value in result.results.items():
                    console.print(f"  {key}: {value}")

    async def run_analyze(self, args: List[str]) -> None:
        """Analyze a website."""
        if not args:
            print_error("Usage: analyze <url>")
            return

        url = args[0].strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        from ..tools.site_analyzer import SiteAnalyzer
        from .output import _safe_str

        print_info(f"Analyzing {url}...")
        result = await SiteAnalyzer.analyze(url)

        if "error" in result:
            print_error(result["error"])
            return

        print_header("Site Analysis Results")
        console.print(f"[bold]URL:[/] {result['url']}")
        console.print(f"[bold]Title:[/] {_safe_str(result['title'])}")
        desc = result.get("description", "")
        console.print(f"[bold]Description:[/] {_safe_str(desc[:200])}")

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

    async def schedule_job(self, args: List[str]) -> None:
        """Schedule a job."""
        if len(args) < 2:
            print_error("Usage: schedule [cron] [command]")
            return

        cron = args[0]
        cmd = " ".join(args[1:])
        cmd_parts = cmd.split()
        cmd_type = cmd_parts[0] if cmd_parts else ""

        if cmd_type == "agent" and self.scheduler and self.grok:
            goal = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""

            async def job_func() -> Any:
                if isinstance(self.config, FullConfig):
                    async with GrokClient(self.config.grok) as grok:
                        async with GrokBrowserAgent(
                            grok,
                            self.config.browser,
                            self.config.system,
                        ) as agent:
                            result = await agent.run_task(goal, max_steps=30)
                            return result.results
                return None

            job = await self.scheduler.schedule(
                func=job_func,
                schedule=cron,
                name=f"Agent: {goal[:30]}",
            )

            print_success(f"Job scheduled with ID: {job.id}")
        else:
            print_error("Scheduling requires 'agent' command and API key")

    async def list_jobs(self, args: List[str]) -> None:
        """List jobs."""
        if not self.scheduler:
            return

        if args:
            job_id = args[0]
            job = self.scheduler.get_job(job_id)
            if job:
                stats = self.scheduler.get_job_stats(job_id)
                results = self.scheduler.get_recent_results(
                    job_id=job_id,
                    limit=5,
                )

                console.print(f"\n[bold cyan]Job: {job.name}[/]")
                console.print(f"ID: {job.id}")
                console.print(f"Status: {job.status.value}")
                if job.schedule:
                    console.print(
                        f"Schedule: {job.schedule.type.value}: {job.schedule.value}"
                    )
                console.print(f"Next Run: {job.next_run}")

                if stats:
                    console.print("\n[bold]Statistics:[/]")
                    console.print(f"  Total Runs: {stats.get('total_runs', 0)}")
                    console.print(
                        f"  Success Rate: {stats.get('success_rate', 0) * 100:.1f}%"
                    )
                    console.print(
                        f"  Avg Duration: {stats.get('avg_duration_ms', 0) / 1000:.2f}s"
                    )

                if results:
                    console.print("\n[bold]Recent Results:[/]")
                    for r in results:
                        status = "✅" if r.success else "❌"
                        console.print(
                            f"  {status} {r.start_time.strftime('%H:%M:%S')} - {r.duration_ms / 1000:.2f}s"
                        )
            else:
                print_error(f"Job {job_id} not found")
        else:
            jobs = self.scheduler.get_jobs()
            job_list = []
            for job in jobs[:10]:
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

    async def search_memory(self, args: List[str]) -> None:
        """Search memory."""
        if not args:
            print_error("Please provide a search query")
            return

        if not self.memory:
            return

        query = " ".join(args)
        results = await self.memory.search(
            query=query,
            limit=10,
            use_semantic=True,
        )

        if results:
            table = Table(title=f"Search Results: '{query}'")
            table.add_column("Type", style="cyan")
            table.add_column("Key", style="green")
            table.add_column("Preview", style="white")

            for item in results:
                content = item.content
                preview = (
                    str(content)[:80] + "..."
                    if len(str(content)) > 80
                    else str(content)
                )
                table.add_row(
                    item.type.value,
                    (item.key or "")[:30],
                    preview,
                )
            console.print(table)
        else:
            print_info("No results found")

    async def show_health(self, args: List[str]) -> None:
        """Show system health."""
        if self.scheduler:
            health = await self.scheduler.get_system_health()
            print_system_health(health)

    async def show_stats(self, args: List[str]) -> None:
        """Show statistics."""
        if self.scheduler:
            console.print("\n[bold cyan]Scheduler Statistics:[/]")
            for key, value in self.scheduler.stats.items():
                console.print(f"  {key}: {value}")

        if self.memory:
            memory_stats = await self.memory.get_stats()
            console.print("\n[bold cyan]Memory Statistics:[/]")
            console.print(f"  Total Items: {memory_stats.get('total_items', 'N/A')}")
            if "items_by_type" in memory_stats:
                console.print(
                    f"  By Type: {memory_stats.get('items_by_type', {})}"
                )

    def clear_screen(self, args: List[str]) -> None:
        """Clear screen."""
        console.clear()
        print_header("Grok-Harness Interactive Mode")

    def exit(self, args: List[str]) -> None:
        """Exit interactive mode."""
        self.running = False

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.scheduler:
            await self.scheduler.stop()
        if self.memory:
            await self.memory.stop()
        if self.grok and hasattr(self.grok, "__aexit__"):
            await self.grok.__aexit__(None, None, None)
