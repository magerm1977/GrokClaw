"""Browser automation module for Grok-Harness."""

from .agent import GrokBrowserAgent
from .controller import BrowserController
from .fingerprint import BrowserFingerprint
from .setup import (
    BrowserManager,
    check_playwright_installed,
    get_playwright_version,
    install_playwright,
)
from .stealth import StealthEngine, StealthProfile

__all__ = [
    "install_playwright",
    "check_playwright_installed",
    "get_playwright_version",
    "BrowserManager",
    "BrowserController",
    "BrowserFingerprint",
    "GrokBrowserAgent",
    "StealthEngine",
    "StealthProfile",
]
