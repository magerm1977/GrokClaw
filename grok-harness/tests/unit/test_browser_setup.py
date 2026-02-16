"""Unit tests for browser setup."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.browser.setup import (
    BrowserManager,
    PlaywrightSetup,
    check_playwright_installed,
    get_playwright_version,
    install_playwright,
)
from grok_harness.core.types import BrowserConfig, OS_TYPE, SystemInfo
from grok_harness.utils.errors import BrowserError, ResourceError


@pytest.fixture
def browser_config() -> BrowserConfig:
    """Browser configuration fixture."""
    return BrowserConfig(
        headless=True,
        timeout_ms=30000,
        max_instances=2,
        require_approval=True,
    )


@pytest.fixture
def system_info() -> SystemInfo:
    """System info fixture."""
    return SystemInfo(
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
        disk_free_gb=100.0,
        disk_total_gb=500.0,
        has_gpu=False,
    )


@pytest.mark.asyncio
async def test_playwright_setup_init() -> None:
    """Test PlaywrightSetup initialization."""
    setup = PlaywrightSetup()
    assert setup.system in ["windows", "linux", "darwin"]
    assert setup._playwright_available is None


@pytest.mark.asyncio
async def test_check_playwright_installed_not_installed() -> None:
    """Test playwright check when not installed."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "playwright":
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", mock_import):
        setup = PlaywrightSetup()
        result = setup._check_playwright_installed()
        assert result is False


@pytest.mark.asyncio
async def test_check_playwright_installed_installed() -> None:
    """Test playwright check when installed."""
    mock_playwright = MagicMock()
    mock_playwright.__version__ = "1.40.0"
    with patch.dict(sys.modules, {"playwright": mock_playwright}):
        setup = PlaywrightSetup()
        result = setup._check_playwright_installed()
        assert result is True


@pytest.mark.asyncio
async def test_check_playwright_version_too_low() -> None:
    """Test playwright version check fails if too low."""
    mock_playwright = MagicMock()
    mock_playwright.__version__ = "1.30.0"
    with patch.dict(sys.modules, {"playwright": mock_playwright}):
        setup = PlaywrightSetup()
        result = setup._check_playwright_installed()
        assert result is False


@pytest.mark.asyncio
async def test_install_playwright_package_success() -> None:
    """Test playwright package installation success."""
    setup = PlaywrightSetup()

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_process,
    ):
        result = await setup._install_playwright_package()
        assert result is True


@pytest.mark.asyncio
async def test_install_playwright_package_failure() -> None:
    """Test playwright package installation failure."""
    setup = PlaywrightSetup()

    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))

    with patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_process,
    ):
        result = await setup._install_playwright_package()
        assert result is False


@pytest.mark.asyncio
async def test_install_browsers_success() -> None:
    """Test browser installation success."""
    setup = PlaywrightSetup()

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    setup._verify_browser = AsyncMock(return_value=True)

    with patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_process,
    ):
        result = await setup.install_browsers(["chromium"])
        assert result is True
        assert setup._browsers_installed.get("chromium") is True


@pytest.mark.asyncio
async def test_install_browsers_failure() -> None:
    """Test browser installation failure."""
    setup = PlaywrightSetup()

    mock_process = AsyncMock()
    mock_process.returncode = 1
    mock_process.communicate = AsyncMock(return_value=(b"", b"error"))

    with patch(
        "asyncio.create_subprocess_exec",
        return_value=mock_process,
    ):
        result = await setup.install_browsers(["chromium"])
        assert result is False


@pytest.mark.asyncio
async def test_verify_browser_success() -> None:
    """Test browser verification success."""
    setup = PlaywrightSetup()

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.__aenter__ = AsyncMock(
        return_value=mock_playwright
    )
    mock_playwright_instance.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "playwright.async_api.async_playwright",
        return_value=mock_playwright_instance,
    ):
        result = await setup._verify_browser("chromium")
        assert result is True


@pytest.mark.asyncio
async def test_get_browser_path() -> None:
    """Test getting browser executable path."""
    setup = PlaywrightSetup()

    mock_chromium = MagicMock()
    mock_chromium.executable_path = "/fake/path/chrome"

    mock_playwright = MagicMock()
    mock_playwright.chromium = mock_chromium

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.__aenter__ = AsyncMock(
        return_value=mock_playwright
    )
    mock_playwright_instance.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "playwright.async_api.async_playwright",
        return_value=mock_playwright_instance,
    ):
        with patch.object(Path, "exists", return_value=True):
            path = await setup.get_browser_path("chromium")
            assert path is not None
            assert path.as_posix() == "/fake/path/chrome"


@pytest.mark.asyncio
async def test_browser_manager_init(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
) -> None:
    """Test BrowserManager initialization."""
    manager = BrowserManager(browser_config, system_info)
    assert manager.config == browser_config
    assert manager.system_info == system_info
    assert isinstance(manager.setup, PlaywrightSetup)


@pytest.mark.asyncio
async def test_browser_manager_initialize_success(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
) -> None:
    """Test BrowserManager initialize success."""
    manager = BrowserManager(browser_config, system_info)
    manager.setup.ensure_playwright = AsyncMock(return_value=True)

    result = await manager.initialize()
    assert result is True


@pytest.mark.asyncio
async def test_browser_manager_initialize_failure(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
) -> None:
    """Test BrowserManager initialize failure."""
    manager = BrowserManager(browser_config, system_info)
    manager.setup.ensure_playwright = AsyncMock(return_value=False)

    with pytest.raises(BrowserError):
        await manager.initialize()


@pytest.mark.asyncio
async def test_browser_manager_resource_check_ram(
    browser_config: BrowserConfig,
) -> None:
    """Test resource check fails with low RAM."""
    low_ram_system = SystemInfo(
        os=OS_TYPE.WINDOWS,
        os_version="10",
        os_release="",
        machine="x64",
        python_version="3.9",
        ram_gb=1.5,
        ram_total_bytes=int(1.5e9),
        cpu_cores=4,
        cpu_physical=4,
        cpu_freq=None,
        disk_free_gb=50.0,
        disk_total_gb=500.0,
    )

    manager = BrowserManager(browser_config, low_ram_system)

    with pytest.raises(ResourceError) as exc_info:
        manager._check_resources()
    assert "RAM" in str(exc_info.value)


@pytest.mark.asyncio
async def test_browser_manager_resource_check_disk(
    browser_config: BrowserConfig,
) -> None:
    """Test resource check fails with low disk space."""
    low_disk_system = SystemInfo(
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
        disk_free_gb=0.5,
        disk_total_gb=500.0,
    )

    manager = BrowserManager(browser_config, low_disk_system)

    with pytest.raises(ResourceError) as exc_info:
        manager._check_resources()
    assert "disk" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_browser_info(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
) -> None:
    """Test getting browser info."""
    manager = BrowserManager(browser_config, system_info)

    async def mock_get_path(browser: str) -> Path | None:
        return Path(f"/fake/path/{browser}") if browser == "chromium" else None

    async def mock_get_version(browser: str) -> str | None:
        return "120.0.0" if browser == "chromium" else None

    manager.setup.get_browser_path = AsyncMock(side_effect=mock_get_path)
    manager.setup.get_browser_version = AsyncMock(side_effect=mock_get_version)

    info = await manager.get_browser_info()

    assert "chromium" in info
    assert info["chromium"]["path"] is not None
    assert "chromium" in info["chromium"]["path"]
    assert info["chromium"]["version"] == "120.0.0"
    assert info["chromium"]["installed"] is True

    assert "firefox" in info
    assert info["firefox"]["installed"] is False


@pytest.mark.asyncio
async def test_cleanup(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
) -> None:
    """Test browser cleanup."""
    manager = BrowserManager(browser_config, system_info)

    mock_page = AsyncMock()
    mock_page.close = AsyncMock()
    manager._pages = [mock_page]

    mock_context = AsyncMock()
    mock_context.close = AsyncMock()
    manager._context = mock_context

    mock_browser = AsyncMock()
    mock_browser.close = AsyncMock()
    manager._browser_process = mock_browser

    await manager.cleanup()

    mock_page.close.assert_called_once()
    mock_context.close.assert_called_once()
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
async def test_install_playwright_convenience() -> None:
    """Test install_playwright convenience function."""
    with patch(
        "grok_harness.browser.setup.PlaywrightSetup"
    ) as mock_setup_class:
        mock_instance = MagicMock()
        mock_instance.ensure_playwright = AsyncMock(return_value=True)
        mock_setup_class.return_value = mock_instance

        result = await install_playwright()
        assert result is True
        mock_instance.ensure_playwright.assert_called_once_with(False)


def test_check_playwright_installed_convenience() -> None:
    """Test check_playwright_installed convenience function."""
    mock_playwright = MagicMock()
    with patch.dict(sys.modules, {"playwright": mock_playwright}):
        result = check_playwright_installed()
        assert result is True


def test_get_playwright_version_convenience() -> None:
    """Test get_playwright_version convenience function."""
    mock_playwright = MagicMock()
    mock_playwright.__version__ = "1.40.0"
    with patch.dict(sys.modules, {"playwright": mock_playwright}):
        version = get_playwright_version()
        assert version == "1.40.0"
