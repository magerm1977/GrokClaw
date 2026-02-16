"""Unit tests for browser controller."""

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.browser.controller import BrowserController
from grok_harness.core.types import BrowserConfig, OS_TYPE, SystemInfo
from grok_harness.utils.errors import (
    BrowserError,
    NavigationError,
    ResourceError,
    SecurityError,
)


@pytest.fixture
def browser_config() -> BrowserConfig:
    """Browser configuration fixture."""
    return BrowserConfig(
        headless=True,
        timeout_ms=30000,
        viewport_width=1280,
        viewport_height=720,
        max_instances=2,
        stealth_mode=True,
        require_approval=True,
        high_risk_domains=["bank", "login", "payment"],
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
def mock_page() -> AsyncMock:
    """Mock Playwright Page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Test</body></html>")
    page.title = AsyncMock(return_value="Test Page")
    page.evaluate = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake_image_data")
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()
    page.select_option = AsyncMock(return_value=["option1"])
    page.wait_for_selector = AsyncMock()
    page.query_selector = AsyncMock()
    page.set_default_timeout = MagicMock()
    page.close = AsyncMock()
    page.url = "https://example.com"
    return page


@pytest.fixture
def mock_context(mock_page: AsyncMock) -> AsyncMock:
    """Mock BrowserContext."""
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=mock_page)
    context.add_init_script = AsyncMock()
    context.cookies = AsyncMock(return_value=[])
    context.clear_cookies = AsyncMock()
    context.add_cookies = AsyncMock()
    context.close = AsyncMock()
    return context


@pytest.fixture
def mock_browser(mock_context: AsyncMock) -> AsyncMock:
    """Mock Browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=mock_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser: AsyncMock) -> MagicMock:
    """Mock Playwright - async_playwright().start() returns playwright instance."""
    pw = MagicMock()
    pw.chromium = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    pw.stop = AsyncMock()

    mock_ap = MagicMock()
    mock_ap.start = AsyncMock(return_value=pw)
    return mock_ap


@pytest.fixture
def mock_playwright_setup() -> AsyncMock:
    """Mock PlaywrightSetup."""
    setup = MagicMock()
    setup.ensure_playwright = AsyncMock(return_value=True)
    return setup


@pytest.mark.asyncio
async def test_initialize_success(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
) -> None:
    """Test successful initialization."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        controller = BrowserController(
            browser_config, system_info, mock_playwright_setup
        )

        result = await controller.initialize()

        assert result is True
        assert controller._is_initialized is True
        assert controller.browser is not None
        assert controller.context is not None
        assert controller.current_page is not None
        mock_playwright_setup.ensure_playwright.assert_called_once()
        pw = mock_playwright.start.return_value
        pw.chromium.launch.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_failure_setup(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
) -> None:
    """Test initialization fails if Playwright setup fails."""
    mock_playwright_setup.ensure_playwright = AsyncMock(return_value=False)

    controller = BrowserController(
        browser_config, system_info, mock_playwright_setup
    )

    with pytest.raises(BrowserError) as exc_info:
        await controller.initialize()
    assert "Failed to setup Playwright" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resource_check_ram(browser_config: BrowserConfig) -> None:
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

    controller = BrowserController(browser_config, low_ram_system)

    with pytest.raises(ResourceError) as exc_info:
        controller._check_resources()
    assert "RAM" in str(exc_info.value)


@pytest.mark.asyncio
async def test_navigate_success(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test successful navigation."""
    mock_response = MagicMock()
    mock_response.ok = True
    mock_page.goto = AsyncMock(return_value=mock_response)

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            result = await controller.navigate("https://example.com")

            assert result is True
            mock_page.goto.assert_called_once_with(
                "https://example.com",
                timeout=30000,
                wait_until="domcontentloaded",
            )


@pytest.mark.asyncio
async def test_navigate_http_error(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test navigation with HTTP error."""
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status = 404
    mock_response.status_text = "Not Found"
    mock_page.goto = AsyncMock(return_value=mock_response)

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            with pytest.raises(NavigationError) as exc_info:
                await controller.navigate("https://example.com/404")
            assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_navigate_blocked_url(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test navigation to blocked URL raises SecurityError."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        controller = BrowserController(
            browser_config, system_info, mock_playwright_setup
        )
        controller.current_page = mock_page

        with pytest.raises(SecurityError) as exc_info:
            await controller.navigate("https://bank.com/login")
        assert "blocked" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_page_text(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test getting page text."""
    mock_page.evaluate = AsyncMock(return_value="Page text content")

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page
            mock_page.evaluate.reset_mock()

            text = await controller.get_page_text()
            assert text == "Page text content"
            mock_page.evaluate.assert_called_once_with(
                "document.body.innerText"
            )


@pytest.mark.asyncio
async def test_get_page_html(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test getting page HTML."""
    mock_page.content = AsyncMock(
        return_value="<html><body>Test</body></html>"
    )

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            html = await controller.get_page_html()
            assert "<html>" in html
            mock_page.content.assert_called_once()


@pytest.mark.asyncio
async def test_screenshot(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test taking screenshot."""
    mock_page.screenshot = AsyncMock(return_value=b"fake_image_data")

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            screenshot = await controller.screenshot()
            assert screenshot == b"fake_image_data"
            mock_page.screenshot.assert_called_once_with(full_page=True)


@pytest.mark.asyncio
async def test_screenshot_base64(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test base64 screenshot."""
    mock_page.screenshot = AsyncMock(return_value=b"fake_image_data")

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            b64 = await controller.screenshot_base64()
            decoded = base64.b64decode(b64)
            assert decoded == b"fake_image_data"


@pytest.mark.asyncio
async def test_click(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test clicking element."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            result = await controller.click("#button")

            assert result is True
            mock_page.wait_for_selector.assert_called_once_with(
                "#button",
                state="visible",
                timeout=30000,
            )
            mock_page.click.assert_called_once_with("#button", timeout=30000)


@pytest.mark.asyncio
async def test_type(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test typing text."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            result = await controller.type("#input", "test text", delay_ms=0)

            assert result is True
            mock_page.wait_for_selector.assert_called_once_with(
                "#input",
                state="visible",
                timeout=30000,
            )
            mock_page.fill.assert_any_call("#input", "")
            mock_page.fill.assert_any_call("#input", "test text")


@pytest.mark.asyncio
async def test_select_option(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test selecting dropdown option."""
    mock_page.select_option = AsyncMock(return_value=["option1"])

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            selected = await controller.select_option("#select", "option1")

            assert selected == ["option1"]
            mock_page.select_option.assert_called_once_with(
                "#select", "option1"
            )


@pytest.mark.asyncio
async def test_scroll(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test scrolling."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page
            mock_page.evaluate.reset_mock()

            await controller.scroll("down")

            mock_page.evaluate.assert_called_once()
            assert "scrollBy" in str(mock_page.evaluate.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_script(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test executing JavaScript."""
    mock_page.evaluate = AsyncMock(return_value="script result")

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page
            mock_page.evaluate.reset_mock()

            result = await controller.execute_script("return document.title")

            assert result == "script result"
            mock_page.evaluate.assert_called_once_with("return document.title")


@pytest.mark.asyncio
async def test_element_exists_true(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test element exists (true)."""
    mock_element = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=mock_element)

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            exists = await controller.element_exists("#button")

            assert exists is True
            mock_page.query_selector.assert_called_once_with("#button")


@pytest.mark.asyncio
async def test_element_exists_false(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test element exists (false)."""
    mock_page.query_selector = AsyncMock(return_value=None)

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.current_page = mock_page

            exists = await controller.element_exists("#missing")

            assert exists is False


@pytest.mark.asyncio
async def test_new_page(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_context: AsyncMock,
    mock_page: AsyncMock,
) -> None:
    """Test creating new page."""
    mock_context.new_page = AsyncMock(return_value=mock_page)

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        controller = BrowserController(
            browser_config, system_info, mock_playwright_setup
        )
        controller.context = mock_context
        controller.pages = [mock_page]
        controller.current_page = mock_page

        new_page = await controller.new_page()

        assert new_page == mock_page
        assert len(controller.pages) == 2
        mock_context.new_page.assert_called_once()


@pytest.mark.asyncio
async def test_close_page(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
) -> None:
    """Test closing page."""
    mock_page.close = AsyncMock()

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.pages = [mock_page]
            controller.current_page = mock_page

            await controller.close_page(mock_page)

            assert len(controller.pages) == 0
            assert controller.current_page is None
            mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_save_session(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_page: AsyncMock,
    mock_context: AsyncMock,
    tmp_path: Path,
) -> None:
    """Test saving session."""
    mock_context.cookies = AsyncMock(
        return_value=[{"name": "session", "value": "123"}]
    )
    mock_page.evaluate = AsyncMock(return_value='{"key": "value"}')
    mock_page.url = "https://example.com"

    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller.context = mock_context
            controller.current_page = mock_page

            session_path = await controller.save_session(
                tmp_path / "session.json"
            )

            assert session_path.exists()
            with open(session_path, "r") as f:
                data = json.load(f)
                assert data["url"] == "https://example.com"
                assert len(data["cookies"]) == 1


@pytest.mark.asyncio
async def test_action_history(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
) -> None:
    """Test action history recording."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            controller._record_action("test", {"foo": "bar"})

            history = controller.get_action_history()
            assert len(history) == 1
            assert history[0]["action"] == "test"
            assert history[0]["details"]["foo"] == "bar"


@pytest.mark.asyncio
async def test_close_cleanup(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
    mock_browser: AsyncMock,
    mock_context: AsyncMock,
    mock_page: AsyncMock,
) -> None:
    """Test close cleans up resources."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        controller = BrowserController(
            browser_config, system_info, mock_playwright_setup
        )
        controller.browser = mock_browser
        controller.context = mock_context
        controller.pages = [mock_page]
        controller.current_page = mock_page
        controller.playwright = mock_playwright

        await controller.close()

        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

        assert controller.pages == []
        assert controller.current_page is None
        assert controller.context is None
        assert controller.browser is None
        assert controller.playwright is None


@pytest.mark.asyncio
async def test_context_manager(
    browser_config: BrowserConfig,
    system_info: SystemInfo,
    mock_playwright_setup: AsyncMock,
    mock_playwright: MagicMock,
) -> None:
    """Test async context manager."""
    with patch(
        "grok_harness.browser.controller.async_playwright",
        return_value=mock_playwright,
    ):
        async with BrowserController(
            browser_config, system_info, mock_playwright_setup
        ) as controller:
            assert controller._is_initialized is True

        assert controller._is_initialized is False
