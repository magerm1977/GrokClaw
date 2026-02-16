"""Integration tests for orchestrator end-to-end."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from grok_harness.core.orchestrator import Orchestrator, RunOptions, RunResult
from grok_harness.core.types import TaskPlan, TaskStep
from grok_harness.memory.unified import UnifiedMemory
from grok_harness.scheduler.smart import SmartScheduler


@pytest.fixture
def tmp_storage(tmp_path: Path) -> Path:
    """Temporary storage."""
    return tmp_path / "orch_test"


@pytest.fixture
def mock_grok() -> AsyncMock:
    """Mock Grok client."""
    grok = AsyncMock()
    grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.1, description="Brief wait"),
                TaskStep(action="done", description="Complete"),
            ],
            reasoning="Simple test",
            estimated_steps=2,
        )
    )
    return grok


@pytest.fixture
def mock_memory(tmp_storage: Path) -> UnifiedMemory:
    """Create real memory (lightweight)."""
    from grok_harness.core.types import MemoryConfig

    config = MemoryConfig(
        path=tmp_storage / "memory.db",
        enable_embeddings=False,
        low_spec_mode=True,
        enable_compression=False,
    )
    return UnifiedMemory(config)


@pytest.fixture
def mock_scheduler(tmp_storage: Path) -> SmartScheduler:
    """Create real scheduler (no Grok)."""
    return SmartScheduler(
        grok_client=None,
        storage_path=tmp_storage,
        enable_learning=False,
        enable_predictive=True,
        enable_monitoring=False,
    )


@pytest.fixture
def config():
    """Minimal config."""
    from grok_harness.core.config_manager import ConfigManager

    return ConfigManager.create_default_config()


@pytest.mark.asyncio
async def test_orchestrator_simple_task(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Simple task -> plan -> execute -> episode stored."""
    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)

    result = await orch.run("Do nothing", RunOptions(live_progress=False))

    assert result.status == "success"
    assert result.steps_completed >= 1
    assert result.episodes_added == 1
    assert result.duration >= 0

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_parse_string_input(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """String input is parsed to description."""
    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    parsed = orch._parse_input("Get weather")
    assert parsed["description"] == "Get weather"
    assert "task_id" in parsed

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_parse_dict_input(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Dict input is parsed."""
    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    parsed = orch._parse_input({"description": "Task X", "task_id": "custom-1"})
    assert parsed["description"] == "Task X"
    assert parsed["task_id"] == "custom-1"

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_wait_step(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Wait step executes asyncio.sleep."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.05, description="Wait"),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("wait test", RunOptions(live_progress=False))

    assert result.status == "success"
    assert result.steps_completed >= 1

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_done_step_shortcircuits(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Done step ends execution."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[TaskStep(action="done", description="Stop")],
            reasoning="",
            estimated_steps=1,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("done test", RunOptions(live_progress=False))

    assert result.status == "success"

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_fail_step(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Fail step sets failure."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[TaskStep(action="fail", description="Intentional fail")],
            reasoning="",
            estimated_steps=1,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("fail test", RunOptions(live_progress=False))

    assert result.status in ("failure", "partial")

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_run_code_step(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """run_code executes safe eval."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="run_code", value="1 + 2", description="Add"),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("run code", RunOptions(live_progress=False))

    assert result.status == "success"

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_memory_search_step(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """memory_search calls memory.search."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(
                    action="memory_search",
                    target="test query",
                    description="Search",
                ),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=2,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("memory search", RunOptions(live_progress=False))

    assert result.status == "success"

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_progress_callback(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Progress callback is invoked."""
    calls = []

    def progress(**kwargs):
        calls.append(kwargs)

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    orch.set_progress_callback(progress)

    await orch.run("progress test", RunOptions(live_progress=False))

    assert len(calls) >= 1
    assert any("action" in c for c in calls)

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_empty_input(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Empty input returns failure."""
    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("", RunOptions(live_progress=False))

    assert result.status == "failure"
    assert "Empty" in (result.error or "")

    mock_grok.plan_task.assert_not_called()

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_plan_failure(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """Plan failure returns structured result."""
    mock_grok.plan_task = AsyncMock(side_effect=Exception("API error"))

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("failing task", RunOptions(live_progress=False))

    assert result.status == "failure"
    assert "API error" in (result.error or "")

    await mock_scheduler.stop()
    await mock_memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_max_steps(
    mock_grok: AsyncMock,
    mock_memory: UnifiedMemory,
    mock_scheduler: SmartScheduler,
    config,
) -> None:
    """max_steps limits execution."""
    mock_grok.plan_task = AsyncMock(
        return_value=TaskPlan(
            steps=[
                TaskStep(action="wait", value=0.01),
                TaskStep(action="wait", value=0.01),
                TaskStep(action="wait", value=0.01),
                TaskStep(action="done"),
            ],
            reasoning="",
            estimated_steps=4,
        )
    )

    await mock_memory.start()
    await mock_scheduler.start()

    orch = Orchestrator(config, mock_grok, mock_memory, mock_scheduler)
    result = await orch.run("max steps", RunOptions(max_steps=2, live_progress=False))

    assert result.steps_completed <= 2

    await mock_scheduler.stop()
    await mock_memory.stop()
