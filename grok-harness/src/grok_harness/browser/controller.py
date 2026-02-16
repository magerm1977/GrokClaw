"""Core browser automation controller using Playwright."""

import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..core.types import BrowserConfig, SystemInfo
from ..utils.errors import (
    BrowserError,
    NavigationError,
    ResourceError,
    SecurityError,
)
from .fingerprint import BrowserFingerprint
from .setup import PlaywrightSetup
from .stealth import StealthEngine


class BrowserController:
    """
    Core browser automation controller using Playwright.

    Provides high-level methods for browser control with proper
    error handling, resource management, and safety features.
    """

    def __init__(
        self,
        config: BrowserConfig,
        system_info: SystemInfo,
        playwright_setup: Optional[PlaywrightSetup] = None,
    ) -> None:
        self.config = config
        self.system_info = system_info
        self.setup = playwright_setup or PlaywrightSetup(config)

        self.playwright: Any = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.pages: List[Page] = []
        self.current_page: Optional[Page] = None

        self._is_initialized = False
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._action_history: List[Dict[str, Any]] = []

        self.stealth: Optional[StealthEngine] = None
        self.fingerprint_manager = BrowserFingerprint()
        self.current_fingerprint: Optional[Dict[str, Any]] = None

    async def initialize(self) -> bool:
        """
        Initialize browser controller.

        Ensures Playwright is installed and launches browser.
        """
        if self._is_initialized:
            return True

        if not await self.setup.ensure_playwright():
            raise BrowserError("Failed to setup Playwright")

        self._check_resources()
        await self._launch_browser()

        self._is_initialized = True
        return True

    def _check_resources(self) -> None:
        """Check system resources before launching."""
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

    async def _launch_browser(self) -> None:
        """Launch browser with configured settings and stealth."""
        pw = await async_playwright().start()
        self.playwright = pw

        if self.config.stealth_mode:
            self.stealth = StealthEngine(
                os_type=self.system_info.os.value,
                browser_type="chrome",
            )
            self.current_fingerprint = self.stealth.get_fingerprint()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
        if self.config.headless:
            launch_args.append("--disable-gpu")

        self.browser = await pw.chromium.launch(
            headless=self.config.headless,
            args=launch_args,
            timeout=self.config.timeout_ms,
        )

        viewport = (
            self.current_fingerprint.get("viewport")
            if self.current_fingerprint
            else None
        ) or {"width": self.config.viewport_width, "height": self.config.viewport_height}
        user_agent = (
            self.current_fingerprint.get("user_agent")
            if self.current_fingerprint
            else None
        ) or self.config.user_agent or self._get_default_user_agent()
        locale = (
            (self.current_fingerprint.get("languages") or ["en-US"])[0]
            if self.current_fingerprint
            else "en-US"
        )
        timezone_id = (
            self.current_fingerprint.get("timezone")
            if self.current_fingerprint
            else "America/New_York"
        )

        self.context = await self.browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            accept_downloads=True,
            locale=locale,
            timezone_id=timezone_id,
        )

        if self.config.stealth_mode and self.stealth:
            await self.stealth.apply_to_context(self.context)

        self.current_page = await self.context.new_page()
        self.pages.append(self.current_page)

        if self.config.stealth_mode and self.stealth:
            await self.stealth.apply_to_page(self.current_page)

        self.current_page.set_default_timeout(self.config.timeout_ms)

    def _get_default_user_agent(self) -> str:
        """Get a realistic default user agent."""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    async def navigate(
        self, url: str, timeout: Optional[int] = None
    ) -> bool:
        """
        Navigate to a URL.

        Args:
            url: The URL to navigate to
            timeout: Override default timeout in ms

        Returns:
            True if navigation successful

        Raises:
            NavigationError: If navigation fails
            SecurityError: If URL is blocked
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        if not self._is_url_allowed(url):
            raise SecurityError(f"URL blocked by security policy: {url}")

        timeout_ms = timeout or self.config.timeout_ms

        try:
            response = await self.current_page.goto(
                url,
                timeout=timeout_ms,
                wait_until="domcontentloaded",
            )

            await asyncio.sleep(0.5)

            if response and not response.ok:
                raise NavigationError(
                    f"HTTP {response.status}: {response.status_text}",
                    details={"url": url, "status": response.status},
                )

            self._record_action("navigate", {"url": url, "success": True})
            return True

        except PlaywrightTimeoutError:
            raise NavigationError(
                f"Navigation timeout after {timeout_ms}ms: {url}"
            )
        except NavigationError:
            raise
        except Exception as e:
            raise NavigationError(f"Navigation failed: {str(e)}")

    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed by security policy."""
        url_lower = url.lower()
        for domain in self.config.high_risk_domains:
            if domain in url_lower:
                return False
        return True

    def _is_high_risk_url(self, url: str) -> bool:
        """Check if URL contains high-risk patterns."""
        url_lower = url.lower()
        high_risk_patterns = [
            "login",
            "signin",
            "account",
            "admin",
            "dashboard",
            "payment",
            "checkout",
            "bank",
        ]
        for pattern in high_risk_patterns:
            if pattern in url_lower:
                return True
        return False

    async def get_page_text(self) -> str:
        """Get visible text from current page."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")
        return await self.current_page.evaluate("document.body.innerText")

    async def get_page_html(self) -> str:
        """Get full HTML from current page."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")
        return await self.current_page.content()

    async def get_page_title(self) -> str:
        """Get page title."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")
        return await self.current_page.title()

    async def get_current_url(self) -> str:
        """Get current page URL."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")
        return self.current_page.url

    async def screenshot(self, full_page: bool = True) -> bytes:
        """
        Take a screenshot of current page.

        Args:
            full_page: Capture full scrollable page

        Returns:
            PNG image bytes
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")
        return await self.current_page.screenshot(full_page=full_page)

    async def screenshot_base64(self, full_page: bool = True) -> str:
        """Take screenshot and return as base64 string."""
        screenshot_bytes = await self.screenshot(full_page)
        return base64.b64encode(screenshot_bytes).decode()

    async def click(
        self, selector: str, timeout: Optional[int] = None
    ) -> bool:
        """
        Click an element by selector.

        Args:
            selector: CSS selector for the element
            timeout: Override default timeout

        Returns:
            True if click successful
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        timeout_ms = timeout or self.config.timeout_ms

        try:
            await self.current_page.wait_for_selector(
                selector,
                state="visible",
                timeout=timeout_ms,
            )
            await self.current_page.click(selector, timeout=timeout_ms)
            await asyncio.sleep(0.3)
            self._record_action("click", {"selector": selector})
            return True

        except PlaywrightTimeoutError:
            raise BrowserError(f"Element not clickable: {selector}")
        except Exception as e:
            raise BrowserError(f"Click failed: {str(e)}")

    async def type(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear_first: bool = True,
    ) -> bool:
        """
        Type text into an input field.

        Args:
            selector: CSS selector for the input
            text: Text to type
            delay_ms: Delay between keystrokes (for human-like typing)
            clear_first: Clear field before typing

        Returns:
            True if typing successful
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        try:
            await self.current_page.wait_for_selector(
                selector,
                state="visible",
                timeout=self.config.timeout_ms,
            )

            if clear_first:
                await self.current_page.fill(selector, "")

            if delay_ms > 0:
                await self.current_page.type(selector, text, delay=delay_ms)
            else:
                await self.current_page.fill(selector, text)

            self._record_action(
                "type", {"selector": selector, "text_length": len(text)}
            )
            return True

        except Exception as e:
            raise BrowserError(f"Type failed: {str(e)}")

    async def select_option(
        self,
        selector: str,
        value: Union[str, List[str]],
    ) -> List[str]:
        """
        Select option(s) from a dropdown.

        Args:
            selector: CSS selector for the select element
            value: Value(s) to select

        Returns:
            List of selected values
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        try:
            selected = await self.current_page.select_option(selector, value)
            self._record_action(
                "select", {"selector": selector, "value": value}
            )
            return selected or []

        except Exception as e:
            raise BrowserError(f"Select failed: {str(e)}")

    async def scroll(
        self,
        direction: str = "down",
        amount: Optional[int] = None,
    ) -> None:
        """
        Scroll the page.

        Args:
            direction: 'up', 'down', 'left', 'right'
            amount: Pixels to scroll (default: viewport size for vertical)
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        if direction in ["down", "up"]:
            if amount is None:
                mult = 1 if direction == "down" else -1
                script = (
                    f"window.scrollBy({{top: {mult} * window.innerHeight, "
                    "behavior: 'smooth'}});"
                )
            else:
                amt = amount if direction == "down" else -amount
                script = f"window.scrollBy({{top: {amt}, behavior: 'smooth'}});"
        else:
            if amount is None:
                amount = 500
            amt = amount if direction == "right" else -amount
            script = f"window.scrollBy({{left: {amt}, behavior: 'smooth'}});"

        await self.current_page.evaluate(script)
        await asyncio.sleep(0.3)
        self._record_action("scroll", {"direction": direction, "amount": amount})

    async def wait(self, seconds: float = 2) -> None:
        """Wait for specified seconds."""
        await asyncio.sleep(seconds)
        self._record_action("wait", {"seconds": seconds})

    async def execute_script(self, script: str, *args: Any) -> Any:
        """
        Execute JavaScript on the page.

        Args:
            script: JavaScript to execute
            args: Arguments to pass to the script

        Returns:
            Script return value
        """
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        try:
            result = await self.current_page.evaluate(script, *args)
            self._record_action("script", {"script_length": len(script)})
            return result

        except Exception as e:
            raise BrowserError(f"Script execution failed: {str(e)}")

    async def get_element_text(self, selector: str) -> Optional[str]:
        """Get text content of an element."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        element = await self.current_page.query_selector(selector)
        if element:
            return await element.text_content()
        return None

    async def get_element_attribute(
        self, selector: str, attribute: str
    ) -> Optional[str]:
        """Get attribute value of an element."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        element = await self.current_page.query_selector(selector)
        if element:
            return await element.get_attribute(attribute)
        return None

    async def element_exists(self, selector: str) -> bool:
        """Check if element exists on page."""
        if not self.current_page:
            raise BrowserError("Browser not initialized")

        element = await self.current_page.query_selector(selector)
        return element is not None

    async def new_page(self) -> Page:
        """Create a new page/tab."""
        if not self.context:
            raise BrowserError("Browser not initialized")

        page = await self.context.new_page()
        page.set_default_timeout(self.config.timeout_ms)
        self.pages.append(page)
        self.current_page = page
        return page

    async def close_page(self, page: Optional[Page] = None) -> None:
        """Close a page (default: current page)."""
        if page is None:
            page = self.current_page

        if page and page in self.pages:
            await page.close()
            self.pages.remove(page)

            if self.pages:
                self.current_page = self.pages[-1]
            else:
                self.current_page = None

    async def get_cookies(self) -> List[Dict[str, Any]]:
        """Get all cookies."""
        if not self.context:
            raise BrowserError("Browser not initialized")
        return await self.context.cookies()

    async def clear_cookies(self) -> None:
        """Clear all cookies."""
        if not self.context:
            raise BrowserError("Browser not initialized")
        await self.context.clear_cookies()

    async def save_session(self, path: Optional[Path] = None) -> Path:
        """
        Save browser session (cookies, local storage).

        Args:
            path: Path to save session data

        Returns:
            Path to saved session file
        """
        if not self.context or not self.current_page:
            raise BrowserError("Browser not initialized")

        if path is None:
            path = (
                Path.home()
                / ".grok-harness"
                / "sessions"
                / f"{self._session_id}.json"
            )

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        cookies = await self.context.cookies()
        local_storage_raw = await self.current_page.evaluate(
            "JSON.stringify(Object.assign({}, window.localStorage))"
        )

        try:
            local_storage = json.loads(local_storage_raw or "{}")
        except json.JSONDecodeError:
            local_storage = {}

        session_data = {
            "session_id": self._session_id,
            "timestamp": datetime.now().isoformat(),
            "url": self.current_page.url,
            "cookies": cookies,
            "local_storage": local_storage,
        }

        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)

        return path

    async def load_session(self, path: Path) -> None:
        """
        Load browser session from file.

        Args:
            path: Path to session file
        """
        if not self.context:
            raise BrowserError("Browser not initialized")

        path = Path(path)
        if not path.exists():
            raise BrowserError(f"Session file not found: {path}")

        with open(path, "r") as f:
            session_data = json.load(f)

        if "cookies" in session_data and session_data["cookies"]:
            await self.context.add_cookies(session_data["cookies"])

        if "url" in session_data and session_data["url"]:
            await self.navigate(session_data["url"])

            if "local_storage" in session_data and session_data["local_storage"]:
                for key, value in session_data["local_storage"].items():
                    escaped_value = str(value).replace("\\", "\\\\").replace(
                        "'", "\\'"
                    )
                    await self.current_page.evaluate(
                        f"localStorage.setItem('{key}', '{escaped_value}')"
                    )

    def _record_action(self, action: str, details: Dict[str, Any]) -> None:
        """Record action for history."""
        self._action_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "details": details,
                "url": self.current_page.url if self.current_page else None,
            }
        )

        if len(self._action_history) > 100:
            self._action_history = self._action_history[-100:]

    def get_action_history(self) -> List[Dict[str, Any]]:
        """Get action history."""
        return self._action_history.copy()

    async def close(self) -> None:
        """Close browser and clean up resources."""
        for page in self.pages:
            try:
                await page.close()
            except Exception:
                pass

        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass

        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass

        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

        self.pages = []
        self.current_page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self._is_initialized = False

    async def __aenter__(self) -> "BrowserController":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type,
        exc_val: BaseException,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()
