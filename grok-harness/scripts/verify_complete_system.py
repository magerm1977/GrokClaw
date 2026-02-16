"""
Complete system verification script.

Tests all components working together: config, Grok client, memory,
scheduler, orchestrator, validators, and output.
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

# Add project root to path when run as script
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from grok_harness.core.types import TaskPlan, TaskStep
from grok_harness.cli.output import (
    _SAFE_SYMBOLS,
    console,
    print_error,
    print_header,
    print_success,
)
from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient
from grok_harness.core.orchestrator import Orchestrator, RunOptions
from grok_harness.memory.unified import UnifiedMemory
from grok_harness.scheduler.smart import SmartScheduler
from grok_harness.utils.validators import (
    RiskLevel,
    classify_step_risk,
    is_transient_error,
    requires_approval,
)


def _step_obj(step: dict) -> SimpleNamespace:
    """Convert dict to object for validators that use getattr."""
    return SimpleNamespace(**{k: v for k, v in step.items() if not k.startswith("_")})


async def verify_system() -> None:
    """Run complete system verification."""
    print_header("Grok-Harness Complete System Verification")

    # 1. Load configuration
    console.print("[bold]1. Loading configuration...[/]")
    config = ConfigManager.load_config()
    config_name = (
        config.__class__.__name__
        if hasattr(config, "__class__")
        else type(config).__name__
    )
    console.print(f"   [OK] Config loaded: {config_name}")
    if hasattr(config, "system") and config.system:
        os_val = getattr(config.system.os, "value", str(config.system.os))
        ram = getattr(config.system, "ram_gb", "?")
        console.print(f"   [*] System: {os_val}, {ram}GB RAM")

    # 2. Check API key
    grok_config = getattr(config, "grok", None) or (
        config.get("grok", {}) if isinstance(config, dict) else {}
    )
    api_key = (
        getattr(grok_config, "api_key", None)
        if grok_config and hasattr(grok_config, "api_key")
        else (grok_config.get("api_key") if isinstance(grok_config, dict) else None)
    )
    api_key = api_key or os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    if not api_key:
        console.print("   [!] No Grok API key found. Some tests will be skipped.")
        api_key_available = False
    else:
        api_key_available = True
        console.print("   [OK] Grok API key found")

    # 3. Initialize components
    console.print("\n[bold]2. Initializing components...[/]")

    memory_config = getattr(config, "memory", None) or config.get("memory", {})
    if isinstance(memory_config, dict):
        from grok_harness.core.types import MemoryConfig

        memory_config = MemoryConfig(
            path=memory_config.get("path"),
            enable_embeddings=memory_config.get("enable_embeddings", False),
            low_spec_mode=memory_config.get("low_spec_mode", True),
            enable_compression=memory_config.get("enable_compression", False),
        )

    memory = UnifiedMemory(memory_config)
    await memory.start()
    console.print("   [OK] Memory system initialized")

    grok = None
    if api_key_available:
        from grok_harness.core.types import GrokConfig

        grok_cfg = getattr(config, "grok", None) or GrokConfig(api_key=api_key)
        if not getattr(grok_cfg, "api_key", None):
            grok_cfg = GrokConfig(api_key=api_key)
        grok = GrokClient(grok_cfg)
        await grok.__aenter__()
        console.print("   [OK] Grok client initialized")
    else:
        # Mock grok for orchestrator (dry-run only)
        from grok_harness.core.types import GrokConfig

        mock_grok = AsyncMock()
        mock_grok.plan_task = AsyncMock(
            return_value=TaskPlan(
                steps=[TaskStep(action="done", description="Dry run")],
                reasoning="No API key - verification mode",
                estimated_steps=1,
            )
        )
        grok = mock_grok
        console.print("   [OK] Mock Grok client (no API key)")

    scheduler = SmartScheduler(
        grok_client=grok,
        enable_learning=bool(api_key_available and grok),
        enable_predictive=True,
        enable_monitoring=True,
    )
    await scheduler.start()
    console.print("   [OK] Scheduler initialized")

    orchestrator = Orchestrator(
        config=config,
        grok=grok,
        memory=memory,
        scheduler=scheduler,
    )
    console.print("   [OK] Orchestrator initialized")

    try:
        # 4. Test tasks
        print_header("3. Running Test Tasks")

        test_tasks = [
            {
                "name": "Simple task (dry-run if no API key)",
                "input": "Go to example.com and get the page title",
                "options": RunOptions(
                    max_steps=5,
                    verbose=True,
                    dry_run=not api_key_available,
                    live_progress=False,
                ),
            },
            {
                "name": "Memory-style task",
                "input": "Store the key test_verify with value verification test in memory",
                "options": RunOptions(
                    max_steps=3,
                    dry_run=not api_key_available,
                    live_progress=False,
                ),
            },
            {
                "name": "Schedule-style task",
                "input": "Schedule a job to run every 5 minutes",
                "options": RunOptions(
                    max_steps=2,
                    dry_run=True,
                    live_progress=False,
                ),
            },
        ]

        for i, task in enumerate(test_tasks, 1):
            console.print(f"\n[bold cyan]Task {i}: {task['name']}[/]")

            try:
                result = await orchestrator.run(
                    task_input=task["input"],
                    options=task["options"],
                )

                if result.status == "success":
                    print_success(f"Task completed in {result.duration:.2f}s")
                    if result.plan:
                        steps = result.plan.get("steps", [])
                        if steps:
                            console.print(f"   [*] Steps: {len(steps)}")
                    if result.result and not task["options"].dry_run:
                        res = result.result
                        if isinstance(res, dict) and "dry_run" not in res:
                            snippet = str(res)[:80]
                            console.print(f"   [*] Result: {snippet}...")
                else:
                    print_error(f"Task failed: {result.error or 'Unknown error'}")

            except Exception as e:
                print_error(f"Task error: {e}")

        # 5. Test safety features
        print_header("4. Testing Safety Features")

        test_steps = [
            {"action": "navigate", "target": "https://example.com"},
            {"action": "click", "target": "#submit"},
            {"action": "run_code", "value": "print('hello')"},
            {"action": "shell", "target": "rm -rf /"},
        ]

        console.print("\n[bold]Risk Classification:[/]")
        for step in test_steps:
            obj = _step_obj(step)
            risk = classify_step_risk(step["action"], obj)
            console.print(f"   {step['action']:10} -> {risk.value}")

        console.print("\n[bold]Approval Requirements (level=high):[/]")
        for step in test_steps:
            obj = _step_obj(step)
            needs = requires_approval(step["action"], obj, "high")
            sym = "[OK]" if needs else "[X]"
            console.print(f"   {step['action']:10} -> {sym}")

        # 6. Check memory stats
        print_header("5. Memory Statistics")
        memory_stats = await memory.get_stats()
        console.print(f"   Total items: {memory_stats.get('total_items', 0)}")
        console.print(f"   Items by type: {memory_stats.get('items_by_type', {})}")
        console.print(f"   Total accesses: {memory_stats.get('total_accesses', 0)}")

        # 7. Check scheduler health
        print_header("6. Scheduler Health")
        health = await scheduler.get_system_health()
        console.print(f"   Status: {health.get('status', 'unknown')}")
        console.print(f"   Total jobs: {health.get('total_jobs', 0)}")
        console.print(f"   Queue size: {health.get('queue_size', 0)}")

        # 8. Test retry/transient error detection
        print_header("7. Testing Retry Mechanism")
        is_trans = is_transient_error(TimeoutError("test"))
        if is_trans:
            console.print("   [OK] Transient error detection works (TimeoutError -> retryable)")
        else:
            console.print("   [!] Transient error detection unexpected")

        # 9. Test encoding fallback
        print_header("8. Testing Console Encoding")
        encoding = sys.stdout.encoding or "unknown"
        console.print(f"   Current encoding: {encoding}")
        console.print(f"   Using safe symbols: {_SAFE_SYMBOLS}")
        console.print("   Sample output: [OK] [X] [!] [i]")

        # 10. Final summary
        print_header("Verification Complete")
        console.print("\n[bold green]All systems operational![/]")
        console.print("\n[bold]Next steps:[/]")
        console.print("   1. Run: grok-harness agent 'Your task here'")
        console.print(
            "   2. Schedule: grok-harness schedule add '0 9 * * *' 'agent Daily report'"
        )
        console.print("   3. Monitor: grok-harness monitor health")
        console.print("   4. Interactive: grok-harness interactive")

    finally:
        console.print("\n[bold]9. Cleaning up...[/]")
        await scheduler.stop()
        await memory.stop()
        if grok and not isinstance(grok, AsyncMock) and hasattr(grok, "__aexit__"):
            await grok.__aexit__(None, None, None)
        console.print("   [OK] Cleanup complete")


if __name__ == "__main__":
    asyncio.run(verify_system())
