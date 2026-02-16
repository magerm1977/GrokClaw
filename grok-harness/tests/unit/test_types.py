"""Unit tests for core types."""

import pytest
from pathlib import Path

from grok_harness.core.types import (
    OS_TYPE,
    BrowserType,
    MemoryType,
    SystemInfo,
    BrowserInfo,
    GrokConfig,
    BrowserConfig,
    MemoryConfig,
    FullConfig,
    TaskStep,
    TaskPlan,
    ActionResult,
)


def test_system_info_low_spec() -> None:
    """Test low-spec detection."""
    low_ram = SystemInfo(
        os=OS_TYPE.WINDOWS,
        os_version="10",
        os_release="",
        machine="x64",
        python_version="3.9",
        ram_gb=4.0,
        ram_total_bytes=int(4e9),
        cpu_cores=2,
        cpu_physical=2,
        cpu_freq=None,
        disk_free_gb=5.0,
        disk_total_gb=100.0,
    )
    assert low_ram.is_low_spec is True

    high_ram = SystemInfo(
        os=OS_TYPE.WINDOWS,
        os_version="10",
        os_release="",
        machine="x64",
        python_version="3.9",
        ram_gb=16.0,
        ram_total_bytes=int(16e9),
        cpu_cores=8,
        cpu_physical=8,
        cpu_freq=None,
        disk_free_gb=50.0,
        disk_total_gb=500.0,
    )
    assert high_ram.is_low_spec is False


def test_grok_config_validation() -> None:
    """Test GrokConfig validation."""
    config = GrokConfig(
        temperature=0.3,
        max_tokens=4096,
        timeout_seconds=60,
    )
    assert config.validate() == []

    config.temperature = 1.5
    assert "temperature" in config.validate()[0]

    config.temperature = 0.3
    config.max_tokens = 0
    assert "max_tokens" in config.validate()[0]


def test_browser_config_paths() -> None:
    """Test BrowserConfig path handling."""
    config = BrowserConfig(session_dir="/tmp/sessions")
    assert config.session_dir is not None
    assert isinstance(config.session_dir, Path)
    assert "/tmp/sessions" in str(config.session_dir) or "sessions" in str(
        config.session_dir
    )

    config = BrowserConfig(session_dir=Path("/tmp/sessions"))
    assert isinstance(config.session_dir, Path)


def test_memory_config_type_conversion() -> None:
    """Test MemoryConfig enum conversion."""
    config = MemoryConfig(type="chromadb")
    assert config.type == MemoryType.CHROMA

    config = MemoryConfig(type=MemoryType.SQLITE)
    assert config.type == MemoryType.SQLITE


def test_full_config_roundtrip() -> None:
    """Test FullConfig to dict and back."""
    original = FullConfig(version="0.1.0", low_spec_mode=False)

    dict_data = original.to_dict()
    assert dict_data["version"] == "0.1.0"

    restored = FullConfig.from_dict(dict_data)
    assert restored.version == original.version
    assert restored.low_spec_mode == original.low_spec_mode


def test_task_step_creation() -> None:
    """Test TaskStep dataclass."""
    step = TaskStep(
        action="click",
        target="#submit",
        description="Click submit button",
    )
    assert step.action == "click"
    assert step.target == "#submit"
    assert step.description == "Click submit button"


def test_action_result() -> None:
    """Test ActionResult dataclass."""
    result = ActionResult(
        success=True,
        action="click",
        data={"element": "found"},
        duration_ms=150.5,
    )
    assert result.success is True
    assert result.data is not None
    assert result.data["element"] == "found"
    assert result.duration_ms == 150.5
