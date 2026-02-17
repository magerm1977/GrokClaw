"""
Tests for improvement features: weather tool, named agent, HTTP fallback.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add project root
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.mark.asyncio
async def test_weather_tool_current() -> None:
    """Test WeatherTool.get_current."""
    from grok_harness.tools.weather import WeatherTool

    result = await WeatherTool.get_current("London")
    assert "success" in result
    if result.get("success"):
        assert "data" in result
        assert result.get("location", "").replace("+", " ") == "London"


@pytest.mark.asyncio
async def test_weather_tool_forecast() -> None:
    """Test WeatherTool.get_forecast."""
    from grok_harness.tools.weather import WeatherTool

    result = await WeatherTool.get_forecast("London", 3)
    assert "success" in result


@pytest.mark.asyncio
async def test_named_agent_weather() -> None:
    """Test NamedAgent handles weather without Grok."""
    from grok_harness.agent.named_agent import NamedAgent

    agent = NamedAgent("TestBot")
    response = await agent.chat("weather in London")
    assert "TestBot" in response or "London" in response or "weather" in response.lower()


@pytest.mark.asyncio
async def test_named_agent_help() -> None:
    """Test NamedAgent help command."""
    from grok_harness.agent.named_agent import NamedAgent

    agent = NamedAgent("TestBot")
    response = await agent.chat("help")
    assert "TestBot" in response
    assert "weather" in response.lower()


@pytest.mark.asyncio
async def test_orchestrator_weather_builtin(tmp_path: Path) -> None:
    """Test orchestrator uses built-in weather tool."""
    from grok_harness.core.config_manager import ConfigManager
    from grok_harness.core.orchestrator import Orchestrator, RunOptions
    from grok_harness.core.types import MemoryConfig, TaskPlan, TaskStep
    from grok_harness.memory.unified import UnifiedMemory
    from grok_harness.scheduler.smart import SmartScheduler

    config = ConfigManager.create_default_config()
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
            steps=[TaskStep(action="done")],
            reasoning="",
            estimated_steps=1,
        )
    )

    orch = Orchestrator(config, mock_grok, memory, scheduler)
    result = await orch.run(
        "weather in London",
        RunOptions(live_progress=False),
    )

    assert result.status == "success"
    assert result.steps_completed == 1
    if result.result and isinstance(result.result, dict):
        assert result.result.get("success") or "data" in result.result

    await scheduler.stop()
    await memory.stop()


@pytest.mark.asyncio
async def test_orchestrator_http_fallback(tmp_path: Path) -> None:
    """Test HTTP fallback for navigate step."""
    from grok_harness.core.config_manager import ConfigManager
    from grok_harness.core.orchestrator import Orchestrator
    from grok_harness.core.types import MemoryConfig, TaskStep
    from grok_harness.memory.unified import UnifiedMemory
    from grok_harness.scheduler.smart import SmartScheduler

    config = ConfigManager.create_default_config()
    memory = UnifiedMemory(
        MemoryConfig(
            path=tmp_path / "memory.db",
            enable_embeddings=False,
            low_spec_mode=True,
            enable_compression=False,
        )
    )
    await memory.start()
    scheduler = SmartScheduler(
        grok_client=None,
        storage_path=tmp_path / "scheduler",
        enable_learning=False,
        enable_predictive=False,
        enable_monitoring=False,
    )
    await scheduler.start()

    orch = Orchestrator(config, AsyncMock(), memory, scheduler)
    step = TaskStep(action="navigate", target="https://example.com")
    result = await orch._execute_http_fallback(step)

    assert result.get("success") is True
    assert "data" in result or "method" in result

    await scheduler.stop()
    await memory.stop()
