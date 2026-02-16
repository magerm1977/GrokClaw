"""Advanced stealth techniques to avoid bot detection."""

import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import BrowserContext, Page


class StealthEngine:
    """
    Advanced stealth techniques to avoid bot detection.

    Implements multiple evasion strategies used by real browsers
    to avoid detection by anti-bot systems.
    """

    USER_AGENTS = {
        "windows": {
            "chrome": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            ],
            "firefox": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            ],
            "edge": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            ],
        },
        "macos": {
            "chrome": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ],
            "safari": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
            ],
        },
        "linux": {
            "chrome": [
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ],
            "firefox": [
                "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            ],
        },
    }

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1280, "height": 720},
    ]

    TIMEZONES = [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Paris",
        "Asia/Tokyo",
        "Australia/Sydney",
    ]

    LANGUAGES = [
        ["en-US", "en"],
        ["en-GB", "en"],
        ["en-CA", "en"],
        ["en-AU", "en"],
    ]

    def __init__(self, os_type: str = "windows", browser_type: str = "chrome") -> None:
        self.os_type = os_type
        self.browser_type = browser_type
        self.fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """Generate a random but realistic browser fingerprint."""
        return {
            "user_agent": self._get_random_user_agent(),
            "viewport": random.choice(self.VIEWPORTS).copy(),
            "timezone": random.choice(self.TIMEZONES),
            "languages": random.choice(self.LANGUAGES).copy(),
            "platform": self._get_platform_string(),
            "hardware_concurrency": random.choice([2, 4, 6, 8, 12, 16]),
            "device_memory": random.choice([2, 4, 8, 16]),
            "screen_resolution": self._get_screen_resolution(),
            "color_depth": 24,
            "pixel_ratio": random.choice([1, 1.5, 2]),
            "do_not_track": random.choice([0, 1, None]),
            "accept_language": self._get_accept_language(),
        }

    def _get_random_user_agent(self) -> str:
        """Get random user agent for OS and browser."""
        agents = self.USER_AGENTS.get(self.os_type, {}).get(
            self.browser_type, []
        )
        if agents:
            return random.choice(agents)
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def _get_platform_string(self) -> str:
        """Get platform string based on OS."""
        platforms = {
            "windows": "Win32",
            "macos": "MacIntel",
            "linux": "Linux x86_64",
        }
        return platforms.get(self.os_type, "Win32")

    def _get_screen_resolution(self) -> Dict[str, int]:
        """Get realistic screen resolution."""
        resolutions = [
            {"width": 1920, "height": 1080},
            {"width": 2560, "height": 1440},
            {"width": 1366, "height": 768},
            {"width": 3840, "height": 2160},
        ]
        return random.choice(resolutions).copy()

    def _get_accept_language(self) -> str:
        """Get Accept-Language header value."""
        languages = [
            "en-US,en;q=0.9",
            "en-GB,en;q=0.8",
            "en-US,en;q=0.9,es;q=0.8",
            "en-US,en;q=0.9,fr;q=0.8",
        ]
        return random.choice(languages)

    async def apply_to_context(self, context: BrowserContext) -> None:
        """Apply stealth techniques to browser context."""
        await context.set_extra_http_headers(
            {
                "Accept-Language": self.fingerprint["accept_language"],
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/webp,*/*;q=0.8"
                ),
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )

        await self._apply_stealth_scripts(context)
        await self._override_permissions(context)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    async def _apply_stealth_scripts(self, context: BrowserContext) -> None:
        """Apply JavaScript stealth scripts."""
        platform = self.fingerprint.get("platform", "Win32")
        hw = self.fingerprint.get("hardware_concurrency", 8)
        mem = self.fingerprint.get("device_memory", 8)
        screen_res = self.fingerprint.get(
            "screen_resolution", {"width": 1920, "height": 1080}
        )
        sw = screen_res.get("width", 1920)
        sh = screen_res.get("height", 1080)

        await context.add_init_script(
            f"""
            Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {{
                get: () => undefined
            }});
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const plugins = [
                        {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', length: 1 }},
                        {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', length: 1 }},
                        {{ name: 'Native Client', filename: 'internal-nacl-plugin', length: 1 }}
                    ];
                    plugins.item = (i) => plugins[i] || null;
                    plugins.namedItem = (n) => plugins.find(p => p.name === n) || null;
                    return plugins;
                }}
            }});
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['en-US', 'en']
            }});
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}'
            }});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {hw}
            }});
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {mem}
            }});
            if (!window.chrome) {{
                window.chrome = {{ runtime: {{}}, loadTimes: function() {{}}, csi: function() {{}}, app: {{}} }};
            }}
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications' ?
                    Promise.resolve({{ state: typeof Notification !== 'undefined' ? Notification.permission : 'default' }}) :
                    origQuery(params)
            );
            const getParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {{
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return getParam.call(this, param);
            }};
            delete window.__playwright;
            delete window.__pwTestSelector;
            Object.defineProperty(screen, 'width', {{ get: () => {sw} }});
            Object.defineProperty(screen, 'height', {{ get: () => {sh} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {sw} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => 1040 }});
            Object.defineProperty(screen, 'colorDepth', {{ get: () => 24 }});
            Object.defineProperty(screen, 'pixelDepth', {{ get: () => 24 }});
            """
        )

    async def _override_permissions(self, context: BrowserContext) -> None:
        """Override browser permissions to appear normal."""
        try:
            await context.grant_permissions(
                ["geolocation", "notifications", "clipboard-read", "clipboard-write"]
            )
        except Exception:
            pass

    async def apply_to_page(self, page: Page) -> None:
        """Apply additional stealth to individual page."""
        await self._add_mouse_movements(page)
        await self._add_random_scrolls(page)
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def _add_mouse_movements(self, page: Page) -> None:
        """Simulate random mouse movements."""
        viewport = self.fingerprint["viewport"]
        width = viewport.get("width", 1280)
        height = viewport.get("height", 720)

        points: List[tuple] = []
        x, y = random.randint(0, width), random.randint(0, height)

        for _ in range(random.randint(3, 8)):
            x += random.randint(-100, 100)
            y += random.randint(-100, 100)
            x = max(0, min(width, x))
            y = max(0, min(height, y))
            points.append((x, y))

        for px, py in points:
            await page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(0.01, 0.05))

    async def _add_random_scrolls(self, page: Page) -> None:
        """Simulate random scrolling."""
        if random.random() < 0.3:
            scroll_amount = random.randint(100, 500)
            await page.evaluate(
                f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}})"
            )
            await asyncio.sleep(random.uniform(0.3, 0.8))

    def get_fingerprint(self) -> Dict[str, Any]:
        """Get current fingerprint."""
        return self.fingerprint.copy()


class StealthProfile:
    """Manage and persist stealth profiles."""

    def __init__(self, profile_path: Optional[Path] = None) -> None:
        self.profile_path = profile_path or Path.home() / ".grok-harness" / "stealth_profiles"
        self.profile_path.mkdir(parents=True, exist_ok=True)
        self.current_profile: Optional[Dict[str, Any]] = None

    async def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a saved stealth profile."""
        profile_file = self.profile_path / f"{name}.json"
        if profile_file.exists():
            with open(profile_file, "r") as f:
                return json.load(f)
        return None

    async def save_profile(self, name: str, fingerprint: Dict[str, Any]) -> None:
        """Save a stealth profile."""
        profile_file = self.profile_path / f"{name}.json"
        with open(profile_file, "w") as f:
            json.dump(fingerprint, f, indent=2)

    async def list_profiles(self) -> List[str]:
        """List available profiles."""
        return [f.stem for f in self.profile_path.glob("*.json")]

    async def delete_profile(self, name: str) -> None:
        """Delete a profile."""
        profile_file = self.profile_path / f"{name}.json"
        if profile_file.exists():
            profile_file.unlink()
