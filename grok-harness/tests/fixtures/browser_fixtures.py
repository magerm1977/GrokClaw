"""Browser test fixtures."""

from pathlib import Path

MOCK_BROWSER_PATHS = {
    "windows": {
        "chromium": Path(
            "C:/Program Files/Google/Chrome/Application/chrome.exe"
        ),
        "firefox": Path("C:/Program Files/Mozilla Firefox/firefox.exe"),
        "webkit": None,
    },
    "linux": {
        "chromium": Path("/usr/bin/google-chrome"),
        "firefox": Path("/usr/bin/firefox"),
        "webkit": None,
    },
    "darwin": {
        "chromium": Path(
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        ),
        "firefox": Path(
            "/Applications/Firefox.app/Contents/MacOS/firefox"
        ),
        "webkit": None,
    },
}

MOCK_BROWSER_VERSIONS = {
    "chromium": "120.0.6099.109",
    "firefox": "121.0",
    "webkit": "17.0",
}

MOCK_PLAYWRIGHT_INSTALL_OUTPUT = """
Downloading Chromium 120.0.6099.109 (playwright build v1084)...
Download completed.
Chromium 120.0.6099.109 downloaded to ~/Library/Caches/ms-playwright/chromium-1084
"""

MOCK_PLAYWRIGHT_VERSION_OUTPUT = """
Version 1.40.0
"""
