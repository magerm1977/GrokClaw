"""Playwright installation and browser management."""

import asyncio
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.types import BrowserConfig, SystemInfo
from ..utils.errors import BrowserError, ResourceError


class PlaywrightSetup:
    """Manages Playwright installation and browser binaries."""

    MIN_PLAYWRIGHT_VERSION = "1.40.0"

    BROWSER_DOWNLOAD_URLS = {
        "chromium": {
            "windows": "https://playwright.azureedge.net/builds/chromium/1084/chromium-win64.zip",
            "linux": "https://playwright.azureedge.net/builds/chromium/1084/chromium-linux.zip",
            "darwin": "https://playwright.azureedge.net/builds/chromium/1084/chromium-mac.zip",
        }
    }

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        self.config = config or BrowserConfig()
        self.system = platform.system().lower()
        self.architecture = platform.machine()
        self._playwright_available: Optional[bool] = None
        self._browsers_installed: Dict[str, bool] = {}

    async def ensure_playwright(self, force_reinstall: bool = False) -> bool:
        """
        Ensure Playwright is installed and ready.

        Returns:
            True if Playwright is available and ready
        """
        if not force_reinstall and self._check_playwright_installed():
            if await self._check_browsers_installed():
                return True
            return await self.install_browsers()

        if not await self._install_playwright_package(force_reinstall):
            return False

        return await self.install_browsers()

    def _check_playwright_installed(self) -> bool:
        """Check if playwright package is installed."""
        try:
            import playwright

            version = getattr(playwright, "__version__", "0.0.0")

            try:
                from packaging import version as version_parser

                if version_parser.parse(version) < version_parser.parse(
                    self.MIN_PLAYWRIGHT_VERSION
                ):
                    return False
            except ImportError:
                if version < self.MIN_PLAYWRIGHT_VERSION:
                    return False

            self._playwright_available = True
            return True
        except ImportError:
            self._playwright_available = False
            return False

    async def _install_playwright_package(
        self, force_reinstall: bool = False
    ) -> bool:
        """Install playwright via pip."""
        cmd = [sys.executable, "-m", "pip", "install"]
        if force_reinstall:
            cmd.append("--force-reinstall")
        cmd.append(f"playwright>={self.MIN_PLAYWRIGHT_VERSION}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return False

            return True

        except Exception:
            return False

    async def install_browsers(
        self, browsers: Optional[List[str]] = None
    ) -> bool:
        """
        Install Playwright browsers.

        Args:
            browsers: List of browsers to install (default: ['chromium'])
        """
        if browsers is None:
            browsers = ["chromium"]

        try:
            if self.system == "linux":
                deps_cmd = [sys.executable, "-m", "playwright", "install-deps"]
                deps_process = await asyncio.create_subprocess_exec(
                    *deps_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await deps_process.communicate()

            cmd = [sys.executable, "-m", "playwright", "install"] + browsers
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return False

            for browser in browsers:
                self._browsers_installed[browser] = await self._verify_browser(
                    browser
                )

            return True

        except Exception:
            return False

    async def _verify_browser(self, browser: str) -> bool:
        """Verify a specific browser is installed correctly."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                if browser == "chromium":
                    browser_obj = await p.chromium.launch(headless=True)
                elif browser == "firefox":
                    browser_obj = await p.firefox.launch(headless=True)
                elif browser == "webkit":
                    browser_obj = await p.webkit.launch(headless=True)
                else:
                    return False

                await browser_obj.close()
                return True

        except Exception:
            return False

    async def _check_browsers_installed(self) -> bool:
        """Check if browsers are already installed."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                    await browser.close()
                    self._browsers_installed["chromium"] = True
                    return True
                except Exception:
                    return False

        except Exception:
            return False

    async def get_browser_path(self, browser: str = "chromium") -> Optional[Path]:
        """Get the filesystem path to browser executable."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                if browser == "chromium":
                    executable_path = p.chromium.executable_path
                elif browser == "firefox":
                    executable_path = p.firefox.executable_path
                elif browser == "webkit":
                    executable_path = p.webkit.executable_path
                else:
                    return None

                if executable_path and Path(executable_path).exists():
                    return Path(executable_path)

        except Exception:
            pass

        return None

    async def get_browser_version(
        self, browser: str = "chromium"
    ) -> Optional[str]:
        """Get installed browser version."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                if browser == "chromium":
                    browser_obj = await p.chromium.launch(headless=True)
                elif browser == "firefox":
                    browser_obj = await p.firefox.launch(headless=True)
                elif browser == "webkit":
                    browser_obj = await p.webkit.launch(headless=True)
                else:
                    return None

                version = browser_obj.version
                await browser_obj.close()
                return version

        except Exception:
            return None


class BrowserManager:
    """High-level browser management."""

    def __init__(self, config: BrowserConfig, system_info: SystemInfo) -> None:
        self.config = config
        self.system_info = system_info
        self.setup = PlaywrightSetup(config)
        self._browser_process: Any = None
        self._context: Any = None
        self._pages: List[Any] = []

    async def initialize(self) -> bool:
        """Initialize browser environment."""
        if not await self.setup.ensure_playwright():
            raise BrowserError("Failed to setup Playwright")

        self._check_resources()
        return True

    def _check_resources(self) -> None:
        """Check if system has enough resources for browser."""
        if self.system_info.ram_gb < 2:
            raise ResourceError(
                f"Insufficient RAM for browser: "
                f"{self.system_info.ram_gb}GB < 2GB minimum"
            )

        if self.system_info.disk_free_gb < 1:
            raise ResourceError(
                f"Insufficient disk space: "
                f"{self.system_info.disk_free_gb}GB < 1GB minimum"
            )

    async def get_playwright_version(self) -> str:
        """Get installed Playwright version."""
        try:
            import playwright

            return playwright.__version__
        except ImportError:
            return "not installed"

    async def get_browser_info(self) -> Dict[str, Any]:
        """Get information about installed browsers."""
        info: Dict[str, Any] = {}

        for browser in ["chromium", "firefox", "webkit"]:
            path = await self.setup.get_browser_path(browser)
            version = await self.setup.get_browser_version(browser)

            if path or version:
                info[browser] = {
                    "path": str(path) if path else None,
                    "version": version,
                    "installed": path is not None,
                }
            else:
                info[browser] = {
                    "path": None,
                    "version": None,
                    "installed": False,
                }

        return info

    async def cleanup(self) -> None:
        """Clean up browser resources."""
        for page in self._pages:
            try:
                await page.close()
            except Exception:
                pass

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass

        if self._browser_process:
            try:
                await self._browser_process.close()
            except Exception:
                pass


async def install_playwright(force_reinstall: bool = False) -> bool:
    """One-shot function to install Playwright."""
    setup = PlaywrightSetup()
    return await setup.ensure_playwright(force_reinstall)


def check_playwright_installed() -> bool:
    """Quick check if playwright is installed."""
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def get_playwright_version() -> Optional[str]:
    """Get installed playwright version."""
    try:
        import playwright

        return playwright.__version__
    except ImportError:
        return None
