"""Unit tests for the site analyzer tool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grok_harness.tools.site_analyzer import SiteAnalyzer


@pytest.fixture
def sample_html() -> str:
    """Sample HTML for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Interview Coach - Practice & Land Your Dream Job</title>
        <meta name="description" content="Practice interviews with AI coach. Get callbacks.">
    </head>
    <body>
        <h1>AI Interview Coach for Job Seekers</h1>
        <h2>Practice Makes Perfect</h2>
        <p>Our AI coach helps you practice interviews and improve your chances of getting callbacks from recruiters.</p>
        <button class="btn cta">Start Free Trial</button>
    </body>
    </html>
    """


@pytest.mark.asyncio
async def test_fetch_html_success() -> None:
    """Test successful HTML fetch."""
    mock_html = "<html><body>Test</body></html>"
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=MagicMock(return_value=mock_context))
        )
        mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await SiteAnalyzer.fetch_html("https://example.com")
        assert result == mock_html


@pytest.mark.asyncio
async def test_extract_headlines() -> None:
    """Test headline extraction."""
    from bs4 import BeautifulSoup

    html = "<h1>Title</h1><h2>Sub1</h2><h2>Sub2</h2><h3>Minor</h3>"
    soup = BeautifulSoup(html, "lxml")
    headlines = SiteAnalyzer.extract_headlines(soup)
    assert headlines["h1"] == ["Title"]
    assert headlines["h2"] == ["Sub1", "Sub2"]
    assert headlines["h3"] == ["Minor"]


@pytest.mark.asyncio
async def test_detect_site_purpose_interview() -> None:
    """Test purpose detection identifies interview-related content."""
    text = "Practice interviews with our AI coach. Get callbacks from recruiters. Land your dream job."
    headlines = {"h1": ["AI Interview Coach"], "h2": [], "h3": []}
    scores = SiteAnalyzer.detect_site_purpose(text, headlines)
    assert "ai_interview_coach" in scores
    assert scores["ai_interview_coach"] > 0


@pytest.mark.asyncio
async def test_analyze_with_mock_fetch(sample_html: str) -> None:
    """Test full analysis with mocked HTTP fetch."""
    with patch.object(SiteAnalyzer, "fetch_html", AsyncMock(return_value=sample_html)):
        result = await SiteAnalyzer.analyze("https://coachframe.io")

    assert "error" not in result
    assert result["url"] == "https://coachframe.io"
    assert "interview" in result["title"].lower() or "interview" in str(
        result.get("purpose_detection", {})
    ).lower()
    assert "headlines" in result
    assert "purpose_detection" in result
    assert "primary" in result["purpose_detection"]
    assert "confidence" in result["purpose_detection"]
