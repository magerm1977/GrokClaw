"""Unit tests for config_manager."""

import tempfile
from pathlib import Path

import pytest

from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.types import OS_TYPE, FullConfig


def test_detect_os() -> None:
    """OS detection returns valid enum value."""
    result = ConfigManager.detect_os()
    assert result in [OS_TYPE.WINDOWS, OS_TYPE.LINUX, OS_TYPE.MACOS, OS_TYPE.UNKNOWN]
    assert result.value in ["windows", "linux", "macos", "unknown"]


def test_detect_hardware() -> None:
    """Hardware detection returns RAM and CPU info."""
    hw = ConfigManager.detect_hardware()
    assert "ram_gb" in hw
    assert "cpu_cores" in hw
    assert "cpu_physical" in hw
    assert isinstance(hw["ram_gb"], (int, float))
    assert isinstance(hw["cpu_cores"], (int, type(None)))
    assert hw["ram_gb"] > 0
    assert hw["cpu_cores"] is None or hw["cpu_cores"] > 0


def test_detect_browsers() -> None:
    """Browser detection returns list of browser info dicts."""
    browsers = ConfigManager.detect_browsers()
    assert isinstance(browsers, list)
    for b in browsers:
        assert "type" in b
        assert "path" in b
        assert "version" in b
        assert b["type"] in ["chrome", "firefox"]


def test_detect_system_info() -> None:
    """System info detection returns SystemInfo with valid fields."""
    info = ConfigManager.detect_system_info()
    assert info.os in [OS_TYPE.WINDOWS, OS_TYPE.LINUX, OS_TYPE.MACOS, OS_TYPE.UNKNOWN]
    assert info.ram_gb > 0
    assert info.cpu_cores > 0
    assert info.disk_free_gb >= 0


def test_detect_browsers_info() -> None:
    """Browser info detection returns BrowserInfo objects."""
    browsers = ConfigManager.detect_browsers_info()
    assert isinstance(browsers, list)
    for b in browsers:
        assert hasattr(b, "browser_type")
        assert hasattr(b, "path")
        assert hasattr(b, "version")


def test_create_default_config() -> None:
    """Default config has expected structure (FullConfig)."""
    config = ConfigManager.create_default_config()
    assert isinstance(config, FullConfig)
    assert config.version == "0.1.0"
    assert config.system is not None
    assert config.grok is not None
    assert config.browser is not None
    assert config.memory is not None
    assert config.scheduler is not None
    assert config.system.os in [
        OS_TYPE.WINDOWS,
        OS_TYPE.LINUX,
        OS_TYPE.MACOS,
        OS_TYPE.UNKNOWN,
    ]
    assert config.system.ram_gb > 0
    assert config.system.cpu_cores > 0


def test_load_config_nonexistent_returns_default() -> None:
    """Loading nonexistent path returns default config."""
    config = ConfigManager.load_config("/nonexistent/path/config.yaml")
    assert isinstance(config, FullConfig)
    assert config.version == "0.1.0"
    assert config.system is not None


def test_load_save_config_yaml() -> None:
    """Can save and load YAML config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "config.yaml"
        original = ConfigManager.create_default_config()
        original.version = "0.2.0"
        ConfigManager.save_config(original, path)
        loaded = ConfigManager.load_config(str(path))
        assert isinstance(loaded, FullConfig)
        assert loaded.version == "0.2.0"


def test_load_save_config_json() -> None:
    """Can save and load JSON config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "config.json"
        original = ConfigManager.create_default_config()
        original.version = "0.3.0"
        ConfigManager.save_config(original, path)
        loaded = ConfigManager.load_config(str(path))
        assert isinstance(loaded, FullConfig)
        assert loaded.version == "0.3.0"
