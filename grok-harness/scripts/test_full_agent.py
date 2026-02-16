"""
Quick test script to verify the complete Grok-Harness agent system.

Usage:
    Set XAI_API_KEY or GROK_API_KEY env var for live API tests.
    Without a key, runs a dry verification (imports + mocked components).

    uv run python scripts/test_full_agent.py
"""

import asyncio
import logging
import os
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_dry_verification() -> bool:
    """Verify all components load and agent can be instantiated (no API)."""
    logger.info("Running dry verification (no API key required)...")

    try:
        from grok_harness.browser.agent import GrokBrowserAgent
        from grok_harness.core.types import (
            BrowserConfig,
            GrokConfig,
            OS_TYPE,
            SystemInfo,
        )
        from grok_harness.core.grok_client import GrokClient

        grok_config = GrokConfig(api_key="dry-test-key")
        browser_config = BrowserConfig(
            headless=True,
            timeout_ms=5000,
            stealth_mode=True,
            screenshot_on_error=True,
        )
        system_info = SystemInfo(
            os=OS_TYPE.WINDOWS,
            os_version="10",
            ram_gb=16,
            cpu_cores=8,
            disk_free_gb=100,
        )

        agent = GrokBrowserAgent(
            grok_client=GrokClient(grok_config),
            config=browser_config,
            system_info=system_info,
        )

        assert agent.grok is not None
        assert agent.config is not None
        assert agent.fingerprint_manager is not None

        logger.info("  - All imports OK")
        logger.info("  - GrokBrowserAgent instantiated")
        return True

    except Exception as e:
        logger.error(f"Dry verification failed: {e}")
        return False


async def test_agent_live(
    grok_config,
    browser_config,
    system_info,
) -> bool:
    """Test the complete agent system with live API."""
    from grok_harness.browser.agent import GrokBrowserAgent
    from grok_harness.core.grok_client import GrokClient

    tasks = [
        {
            "name": "Get page title",
            "goal": "Go to example.com and get the page title",
            "max_steps": 5,
        },
        {
            "name": "Check for emails",
            "goal": "Find any email addresses on example.com",
            "max_steps": 5,
        },
        {
            "name": "Extract links",
            "goal": "Extract all links from example.com",
            "max_steps": 5,
        },
    ]

    async with GrokClient(grok_config) as grok:
        async with GrokBrowserAgent(
            grok, browser_config, system_info
        ) as agent:
            for task in tasks:
                logger.info("\nRunning task: %s", task["name"])

                try:
                    result = await agent.run_task(
                        goal=task["goal"],
                        max_steps=task["max_steps"],
                    )

                    logger.info("  Success: %s", result.success)
                    logger.info("  Steps taken: %s", result.steps_taken)
                    logger.info(
                        "  Duration: %.2fs",
                        result.duration_ms / 1000,
                    )

                    if result.results:
                        logger.info("  Results:")
                        for key, value in result.results.items():
                            logger.info("    %s: %s", key, value)

                    state_path = Path(
                        f"agent_state_{task['name'].replace(' ', '_')}.json"
                    )
                    await agent.save_state(state_path)
                    logger.info("  State saved to %s", state_path)

                except Exception as e:
                    logger.error("  Task failed: %s", e)
                    return False

            logger.info("\nLearned domain patterns:")
            for domain, patterns in agent.domain_patterns.items():
                actions = patterns.get("actions", [])
                logger.info("  %s: %s actions learned", domain, len(actions))

    return True


async def main() -> None:
    """Run verification."""
    logger.info("Testing Grok-Harness Agent System")

    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")

    grok_config = None
    if api_key:
        from grok_harness.core.types import GrokConfig

        grok_config = GrokConfig(
            api_key=api_key,
            model="grok-4-1-fast-reasoning",
            temperature=0.3,
        )

    browser_config = None
    system_info = None
    if api_key:
        from grok_harness.core.types import (
            BrowserConfig,
            OS_TYPE,
            SystemInfo,
        )
        from grok_harness.core.config_manager import ConfigManager

        browser_config = BrowserConfig(
            headless=True,
            timeout_ms=30000,
            stealth_mode=True,
            screenshot_on_error=True,
        )
        system_info = ConfigManager.detect_system_info()

    # Always run dry verification
    if not await test_dry_verification():
        raise SystemExit(1)

    if api_key and grok_config and browser_config and system_info:
        logger.info("\nRunning live agent tests (API key detected)...")
        if not await test_agent_live(
            grok_config, browser_config, system_info
        ):
            raise SystemExit(1)
        logger.info("\nAll verification tests passed!")
    else:
        logger.info(
            "\nSkipping live tests (set XAI_API_KEY or GROK_API_KEY to enable)"
        )
        logger.info("Dry verification passed.")


if __name__ == "__main__":
    asyncio.run(main())
