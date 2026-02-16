"""Unit tests for stealth module."""

import pytest
from pathlib import Path

from grok_harness.browser.stealth import StealthEngine, StealthProfile


@pytest.fixture
def stealth_engine() -> StealthEngine:
    """Stealth engine fixture."""
    return StealthEngine(os_type="windows", browser_type="chrome")


def test_generate_fingerprint(stealth_engine: StealthEngine) -> None:
    """Test fingerprint generation."""
    fp = stealth_engine.fingerprint

    assert "user_agent" in fp
    assert "viewport" in fp
    assert "timezone" in fp
    assert "languages" in fp
    assert "hardware_concurrency" in fp
    assert fp["hardware_concurrency"] in [2, 4, 6, 8, 12, 16]


def test_user_agent_selection(stealth_engine: StealthEngine) -> None:
    """Test user agent selection."""
    ua = stealth_engine._get_random_user_agent()
    assert "Chrome" in ua or "Firefox" in ua or "Edge" in ua


def test_platform_string(stealth_engine: StealthEngine) -> None:
    """Test platform string generation."""
    platform = stealth_engine._get_platform_string()
    assert platform in ["Win32", "MacIntel", "Linux x86_64"]


def test_accept_language(stealth_engine: StealthEngine) -> None:
    """Test Accept-Language header."""
    lang = stealth_engine._get_accept_language()
    assert "en" in lang


@pytest.mark.asyncio
async def test_apply_to_context(stealth_engine: StealthEngine) -> None:
    """Test applying stealth to context."""
    from unittest.mock import AsyncMock

    mock_context = AsyncMock()
    mock_context.set_extra_http_headers = AsyncMock()
    mock_context.add_init_script = AsyncMock()
    mock_context.grant_permissions = AsyncMock()

    await stealth_engine.apply_to_context(mock_context)

    mock_context.set_extra_http_headers.assert_called_once()
    mock_context.add_init_script.assert_called_once()
    mock_context.grant_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_apply_to_page(stealth_engine: StealthEngine) -> None:
    """Test applying stealth to page."""
    from unittest.mock import AsyncMock

    mock_page = AsyncMock()
    mock_page.mouse = AsyncMock()
    mock_page.mouse.move = AsyncMock()
    mock_page.evaluate = AsyncMock()

    await stealth_engine.apply_to_page(mock_page)

    # Mouse movements are always simulated
    assert mock_page.mouse.move.call_count >= 1


def test_stealth_profile_init(tmp_path: Path) -> None:
    """Test stealth profile initialization."""
    profile = StealthProfile(tmp_path)
    assert profile.profile_path == tmp_path
    assert profile.current_profile is None


@pytest.mark.asyncio
async def test_stealth_profile_save_load(tmp_path: Path) -> None:
    """Test saving and loading stealth profiles."""
    profile = StealthProfile(tmp_path)

    fingerprint = {"test": "data", "id": "123"}
    await profile.save_profile("test_profile", fingerprint)

    loaded = await profile.load_profile("test_profile")
    assert loaded == fingerprint


@pytest.mark.asyncio
async def test_stealth_profile_list(tmp_path: Path) -> None:
    """Test listing stealth profiles."""
    profile = StealthProfile(tmp_path)

    await profile.save_profile("profile1", {"id": "1"})
    await profile.save_profile("profile2", {"id": "2"})

    profiles = await profile.list_profiles()
    assert "profile1" in profiles
    assert "profile2" in profiles


@pytest.mark.asyncio
async def test_stealth_profile_delete(tmp_path: Path) -> None:
    """Test deleting stealth profiles."""
    profile = StealthProfile(tmp_path)

    await profile.save_profile("test", {"id": "test"})
    assert (tmp_path / "test.json").exists()

    await profile.delete_profile("test")
    assert not (tmp_path / "test.json").exists()


def test_get_fingerprint_returns_copy(stealth_engine: StealthEngine) -> None:
    """Test get_fingerprint returns a copy."""
    fp1 = stealth_engine.get_fingerprint()
    fp2 = stealth_engine.get_fingerprint()
    assert fp1 is not fp2
    assert fp1 == fp2
