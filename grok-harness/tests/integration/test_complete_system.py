"""
Complete system integration test.

Verifies all components work together: config, Grok client, memory,
scheduler, orchestrator, and CLI parsing.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from grok_harness.cli.commands import create_parser
from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient
from grok_harness.core.types import MemoryConfig, TaskPlan, TaskStep
from grok_harness.memory.models import MemoryItem, MemoryMetadata, MemoryItemType
from grok_harness.memory.unified import UnifiedMemory
from grok_harness.scheduler.smart import SmartScheduler


@pytest.mark.asyncio
async def test_complete_system_integration(tmp_path: Path) -> None:
    """Test all components working together."""
    # 1. Configuration
    config = ConfigManager.create_default_config()
    config.grok.api_key = "test-key"

    # Override memory path for isolation
    config.memory = MemoryConfig(
        path=tmp_path / "memory.db",
        enable_embeddings=False,
        low_spec_mode=True,
        enable_compression=False,
    )

    # 2. Grok Client (mocked - test-key is not a real key)
    grok = GrokClient(config.grok)
    await grok.__aenter__()

    with patch.object(grok, "test_connection", AsyncMock(return_value=True)):
        assert await grok.test_connection() is True

    # 3. Memory System
    memory = UnifiedMemory(config.memory)
    await memory.start()

    try:
        item = MemoryItem(
            id="test1",
            key="test:integration",
            content={"test": "data"},
            type=MemoryItemType.SYSTEM,
            metadata=MemoryMetadata(tags=["test"]),
        )
        await memory.store(item)

        retrieved = await memory.retrieve("test:integration")
        assert retrieved is not None
        assert retrieved.key == "test:integration"

        # 4. Scheduler
        scheduler = SmartScheduler(
            grok_client=grok,
            storage_path=tmp_path / "scheduler",
            enable_learning=False,
            enable_predictive=True,
            enable_monitoring=False,
        )
        await scheduler.start()

        try:
            async def test_job() -> str:
                return "success"

            job = await scheduler.schedule(
                func=test_job,
                schedule="*/5 * * * *",
                name="test_job",
                tags=["test"],
            )

            assert job.id is not None
            assert job.name == "test_job"

            result = await scheduler.run_now(test_job)
            assert result.success is True
            assert result.result == "success"

            # 5. CLI Parser
            parser = create_parser()

            args = parser.parse_args(["agent", "test goal", "--headless"])
            assert args.command == "agent"
            assert args.goal == "test goal"
            assert args.headless is True

            args = parser.parse_args(
                [
                    "schedule",
                    "add",
                    "0 9 * * *",
                    "agent daily",
                    "--name",
                    "Daily",
                    "--priority",
                    "high",
                ]
            )
            assert args.schedule_command == "add"
            assert args.schedule == "0 9 * * *"
            assert args.name == "Daily"
            assert args.priority == "high"

            args = parser.parse_args(
                [
                    "memory",
                    "search",
                    "test query",
                    "--semantic",
                    "--limit",
                    "20",
                ]
            )
            assert args.memory_command == "search"
            assert args.query == "test query"
            assert args.semantic is True
            assert args.limit == 20

        finally:
            await scheduler.stop()

    finally:
        await memory.stop()
        await grok.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_orchestrator_integration(tmp_path: Path) -> None:
    """Test orchestrator with mocked Grok and real memory/scheduler."""
    from grok_harness.core.orchestrator import Orchestrator, RunOptions
    from grok_harness.core.config_manager import ConfigManager

    config = ConfigManager.create_default_config()
    config.grok.api_key = "test-key"

    memory_config = MemoryConfig(
        path=tmp_path / "memory.db",
        enable_embeddings=False,
        low_spec_mode=True,
        enable_compression=False,
    )
    memory = UnifiedMemory(memory_config)
    await memory.start()

    scheduler = SmartScheduler(
        grok_client=None,
        storage_path=tmp_path / "scheduler",
        enable_learning=False,
        enable_predictive=False,
        enable_monitoring=False,
    )
    await scheduler.start()

    mock_grok = AsyncMock()
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.05),
                TaskStep(action="done"),
            ],
            reasoning="Integration test",
            estimated_steps=2,
        )
    )

    try:
        orch = Orchestrator(config, mock_grok, memory, scheduler)
        result = await orch.run("Integration test task", RunOptions(live_progress=False))

        assert result.status == "success"
        assert result.steps_completed >= 1
        assert result.episodes_added == 1
    finally:
        await scheduler.stop()
        await memory.stop()


def test_main_entry_point() -> None:
    """Verify main entry point is importable."""
    from grok_harness.__main__ import main

    assert callable(main)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(test_complete_system_integration(Path(tmp)))
    print("All components integrated successfully")
