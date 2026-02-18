#!/usr/bin/env python
"""
Test Playwright installation.
Run this to verify Playwright is working.
"""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run Playwright installation checks."""
    print("Testing Playwright Installation")
    print("=" * 50)

    # Check Python environment
    print(f"\n[Python] {sys.executable}")
    print(f"[Virtual env] {sys.prefix != sys.base_prefix}")
    print(f"[Current directory] {Path.cwd()}")

    # Check if playwright is installed
    try:
        import playwright

        version = getattr(playwright, "__version__", "installed")
        print(f"\n[OK] Playwright package installed: {version}")
    except ImportError as e:
        print(f"\n[FAIL] Playwright not installed: {e}")
        print("\nInstalling now...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright>=1.40.0"]
        )
        print("Please run this script again.")
        return

    # Check if browsers are installed
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            chromium_path = p.chromium.executable_path
            print(f"\n[OK] Chromium found at: {chromium_path}")

            # Try launching
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://example.com")
            title = page.title()
            browser.close()
            print(f"[OK] Browser test passed! Got title: '{title}'")

    except Exception as e:
        print(f"\n[FAIL] Browser test failed: {e}")
        print("\nAttempting to install browsers...")

        try:
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"]
            )
            print("[OK] Browsers installed! Please run this script again.")
        except Exception as install_error:
            print(f"[FAIL] Installation failed: {install_error}")
            print("\nManual steps:")
            print("  1. pip install playwright")
            print("  2. playwright install chromium")
            print(
                "  3. If on Windows: Set-ExecutionPolicy RemoteSigned -Scope Process"
            )
            return

    print("\n[OK] Playwright is ready!")


if __name__ == "__main__":
    main()
