"""Unit tests for browser agent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.browser.agent import GrokBrowserAgent
from grok_harness.core.grok_client import GrokClient
from grok_harness.core.types import (
    BrowserConfig,
    OS_TYPE,
    SystemInfo,
    TaskPlan,
    TaskStep,
)
from grok_harness.utils.errors import BrowserError


@pytest.fixture
def browser_config() -> BrowserConfig:
    """Browser configuration fixture."""
    return BrowserConfig(
        headless=True,
        timeout_ms=30000,
        viewport_width=1280,
        viewport_height=720,
        stealth_mode=True,
        screenshot_on_error=True,
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


@pytest.fixture
def mock_grok_client() -> AsyncMock:
    """Mock Grok client."""
    client = AsyncMock(spec=GrokClient)

    client.plan_task.return_value = TaskPlan(
        steps=[
            TaskStep(
                action="navigate",
                target="https://example.com",
                description="Go to site",
            ),
            TaskStep(
                action="extract",
                target="title",
                description="Get title",
            ),
        ],
        reasoning="Simple two-step plan",
        estimated_steps=2,
        requires_browser=True,
    )

    client.chat_completion.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "action": "extract",
                            "target": "title",
                            "reasoning": "Get the page title",
                            "confidence": 0.95,
                        }
                    )
                }
            }
        ]
    }

    return client


@pytest.fixture
def mock_browser_controller() -> AsyncMock:
    """Mock browser controller."""
    browser = AsyncMock()
    browser.initialize = AsyncMock()

    browser.get_page_text = AsyncMock(return_value="Sample page text")
    browser.get_page_html = AsyncMock(
        return_value="<html><body>Test</body></html>"
    )
    browser.get_page_title = AsyncMock(return_value="Test Page")
    browser.get_current_url = AsyncMock(return_value="https://example.com")
    browser.screenshot_base64 = AsyncMock(return_value="base64_image_data")
    browser.get_cookies = AsyncMock(return_value=[])
    browser.get_action_history = MagicMock(return_value=[])

    browser.navigate = AsyncMock()
    browser.click = AsyncMock()
    browser.type = AsyncMock()
    browser.select_option = AsyncMock()
    browser.scroll = AsyncMock()
    browser.wait = AsyncMock()
    browser.close = AsyncMock()

    browser.current_page = AsyncMock()
    browser.current_page.query_selector_all = AsyncMock(return_value=[])
    browser.current_page.evaluate = AsyncMock()

    return browser


@pytest.mark.asyncio
async def test_agent_initialize(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test agent initialization."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        agent = GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        )
        await agent.initialize()

        assert agent.browser is not None
        mock_browser_controller.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_run_task_success(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test successful task execution."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent._get_page_state = AsyncMock(
                return_value={
                    "url": "https://example.com",
                    "title": "Test Page",
                    "text_preview": "Sample text",
                    "text_length": 100,
                    "html_length": 500,
                    "screenshot": None,
                    "cookies_count": 0,
                    "step": 0,
                }
            )

            agent._decide_next_action = AsyncMock(
                side_effect=[
                    {
                        "action": "extract",
                        "target": "title",
                        "confidence": 0.9,
                    },
                    {"action": "done"},
                ]
            )

            agent._extract_results = AsyncMock(
                return_value={"title": "Test Page"}
            )

            result = await agent.run_task("Get page title", max_steps=5)

            assert result.success is True
            assert result.steps_taken > 0
            assert "title" in result.results


@pytest.mark.asyncio
async def test_run_task_with_plan(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test task execution with initial plan."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent._get_page_state = AsyncMock(
                return_value={"url": "https://example.com"}
            )
            agent._decide_next_action = AsyncMock(
                return_value={"action": "done"}
            )
            agent._extract_results = AsyncMock(return_value={})

            await agent.run_task("Test task")

            mock_grok_client.plan_task.assert_called_once()


@pytest.mark.asyncio
async def test_get_page_state(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test getting page state."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            state = await agent._get_page_state()

            assert "url" in state
            assert "title" in state
            assert "text_preview" in state
            mock_browser_controller.get_page_text.assert_called_once()


@pytest.mark.asyncio
async def test_decide_next_action(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
) -> None:
    """Test action decision making."""
    agent = GrokBrowserAgent(mock_grok_client, browser_config, system_info)

    page_state = {
        "url": "https://example.com",
        "title": "Test",
        "text_preview": "Sample",
        "text_length": 100,
        "html_length": 500,
        "screenshot": None,
        "cookies_count": 0,
        "step": 0,
    }

    action = await agent._decide_next_action(
        "Test goal", page_state, 0
    )

    assert "action" in action
    mock_grok_client.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_execute_action_navigate(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test executing navigate action."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            result = await agent._execute_action(
                {"action": "navigate", "target": "https://example.com"}
            )

            assert result["success"] is True
            mock_browser_controller.navigate.assert_called_once_with(
                "https://example.com"
            )


@pytest.mark.asyncio
async def test_execute_action_click(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test executing click action."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            result = await agent._execute_action(
                {"action": "click", "target": "#button"}
            )

            assert result["success"] is True
            mock_browser_controller.click.assert_called_once_with("#button")


@pytest.mark.asyncio
async def test_execute_action_type(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test executing type action."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            result = await agent._execute_action(
                {
                    "action": "type",
                    "target": "#input",
                    "value": "test text",
                }
            )

            assert result["success"] is True
            mock_browser_controller.type.assert_called_once_with(
                "#input", "test text"
            )


@pytest.mark.asyncio
async def test_execute_action_extract(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test executing extract action."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller
            agent._extract_field = AsyncMock(return_value="Extracted value")

            result = await agent._execute_action(
                {"action": "extract", "target": "title"}
            )

            assert result["success"] is True
            assert result["data"] == "Extracted value"


@pytest.mark.asyncio
async def test_extract_prices(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test price extraction."""
    mock_element1 = AsyncMock()
    mock_element1.text_content = AsyncMock(return_value="$19.99")
    mock_element2 = AsyncMock()
    mock_element2.text_content = AsyncMock(return_value="$29.99")

    mock_browser_controller.current_page.query_selector_all = AsyncMock(
        return_value=[mock_element1, mock_element2]
    )

    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            prices = await agent._extract_prices()

            assert len(prices) >= 2
            assert "$19.99" in prices


@pytest.mark.asyncio
async def test_extract_emails(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test email extraction."""
    mock_browser_controller.get_page_text = AsyncMock(
        return_value=(
            "Contact us at test@example.com or info@test.com"
        )
    )

    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            emails = await agent._extract_emails()

            assert len(emails) == 2
            assert "test@example.com" in emails


@pytest.mark.asyncio
async def test_extract_links(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test link extraction."""
    mock_link1 = AsyncMock()
    mock_link1.get_attribute = AsyncMock(
        return_value="https://example.com/page1"
    )
    mock_link1.text_content = AsyncMock(return_value="Page 1")

    mock_link2 = AsyncMock()
    mock_link2.get_attribute = AsyncMock(
        return_value="https://example.com/page2"
    )
    mock_link2.text_content = AsyncMock(return_value="Page 2")

    mock_browser_controller.current_page.query_selector_all = AsyncMock(
        return_value=[mock_link1, mock_link2]
    )

    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller

            links = await agent._extract_links()

            assert len(links) == 2
            assert links[0]["url"] == "https://example.com/page1"
            assert links[0]["text"] == "Page 1"


@pytest.mark.asyncio
async def test_learn_from_step(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test learning from successful steps."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent.browser = mock_browser_controller
            mock_browser_controller.get_current_url = AsyncMock(
                return_value="https://example.com/page"
            )

            await agent._learn_from_step(
                goal="Find price",
                action={"action": "click", "target": "#button"},
                result={"success": True},
            )

            assert "example.com" in agent.domain_patterns
            assert (
                len(agent.domain_patterns["example.com"]["actions"])
                == 1
            )


@pytest.mark.asyncio
async def test_save_load_state(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    tmp_path: Path,
) -> None:
    """Test saving and loading agent state."""
    agent = GrokBrowserAgent(
        mock_grok_client, browser_config, system_info
    )
    agent.domain_patterns = {
        "example.com": {
            "actions": [{"action": "click", "target": "#button"}]
        }
    }

    state_path = await agent.save_state(tmp_path / "state.json")
    assert state_path.exists()

    new_agent = GrokBrowserAgent(
        mock_grok_client, browser_config, system_info
    )
    await new_agent.load_state(state_path)

    assert new_agent.domain_patterns == agent.domain_patterns


@pytest.mark.asyncio
async def test_context_manager(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test async context manager."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            assert agent.browser is not None

        mock_browser_controller.close.assert_called_once()


@pytest.mark.asyncio
async def test_max_steps_limit(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_grok_client: AsyncMock,
    mock_browser_controller: AsyncMock,
) -> None:
    """Test max steps limit is respected."""
    with patch(
        "grok_harness.browser.agent.BrowserController",
        return_value=mock_browser_controller,
    ):
        async with GrokBrowserAgent(
            mock_grok_client, browser_config, system_info
        ) as agent:
            agent._get_page_state = AsyncMock(
                return_value={"url": "https://example.com"}
            )
            agent._decide_next_action = AsyncMock(
                return_value={"action": "wait", "value": 1}
            )
            agent._execute_action = AsyncMock(
                return_value={"success": True}
            )
            agent._extract_results = AsyncMock(return_value={})

            result = await agent.run_task(
                "Test task", max_steps=3
            )

            assert result.steps_taken <= 3
            assert agent.step_count <= 3
