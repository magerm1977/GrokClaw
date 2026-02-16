"""Unit tests for Grok client."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_session_post(mock_response: AsyncMock) -> MagicMock:
    """Create a mock session.post that returns an async context manager."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_cm)
    mock_session.close = AsyncMock(return_value=None)
    return mock_session

from grok_harness.core.grok_client import GrokClient
from grok_harness.core.types import GrokConfig, TaskPlan
from grok_harness.utils.errors import (
    AuthenticationError,
    BudgetExceededError,
    GrokAPIError,
    OperationTimeoutError,
    RateLimitError,
    ValidationError,
)


@pytest.fixture
def mock_config() -> GrokConfig:
    """Create a test configuration."""
    return GrokConfig(
        api_key="test-key",
        model="grok-4-1-fast-reasoning",
        temperature=0.3,
        max_tokens=100,
        timeout_seconds=5,
        max_retries=1,
        budget_limit_usd=1.0,
    )


@pytest.fixture
async def client(mock_config: GrokConfig):
    """Create a test client instance."""
    async with GrokClient(mock_config) as c:
        yield c


@pytest.mark.asyncio
async def test_successful_chat_completion(mock_config: GrokConfig) -> None:
    """Test successful API call."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            result = await c.chat_completion(
                [{"role": "user", "content": "Hello"}]
            )

            assert result["choices"][0]["message"]["content"] == "Test response"
            assert c._call_count == 1
            assert c._total_cost > 0


@pytest.mark.asyncio
async def test_authentication_error(mock_config: GrokConfig) -> None:
    """Test authentication failure."""
    mock_response = AsyncMock()
    mock_response.status = 401
    mock_response.text = AsyncMock(return_value="Invalid API key")

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            with pytest.raises(AuthenticationError) as exc_info:
                await c.chat_completion(
                    [{"role": "user", "content": "Hello"}]
                )
            assert "Invalid API key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rate_limit_error(mock_config: GrokConfig) -> None:
    """Test rate limit exceeded."""
    mock_response = AsyncMock()
    mock_response.status = 429
    mock_response.headers = {"Retry-After": "30"}
    mock_response.text = AsyncMock(return_value="Rate limit exceeded")

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            with pytest.raises(RateLimitError) as exc_info:
                await c.chat_completion(
                    [{"role": "user", "content": "Hello"}]
                )
            assert exc_info.value.retry_after == 30


@pytest.mark.asyncio
async def test_budget_exceeded(mock_config: GrokConfig) -> None:
    """Test budget limit reached."""
    mock_config.budget_limit_usd = 0.00001

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "OK"}}],
            "usage": {
                "prompt_tokens": 10000,
                "completion_tokens": 5000,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            await c.chat_completion([{"role": "user", "content": "Hello"}])

            with pytest.raises(BudgetExceededError) as exc_info:
                await c.chat_completion(
                    [{"role": "user", "content": "Hello"}]
                )
            assert "Budget limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_retry_logic(mock_config: GrokConfig) -> None:
    """Test retry on temporary failures."""
    mock_config.max_retries = 3
    mock_config.retry_delay = 0.01

    mock_response_fail = AsyncMock()
    mock_response_fail.status = 500
    mock_response_fail.text = AsyncMock(return_value="Server error")

    mock_response_success = AsyncMock()
    mock_response_success.status = 200
    mock_response_success.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "Success"}}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 5,
            },
        }
    )

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(
        side_effect=[
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]
    )
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_cm)
    mock_session.close = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        async with GrokClient(mock_config) as c:
            result = await c.chat_completion(
                [{"role": "user", "content": "Hello"}]
            )
            assert result["choices"][0]["message"]["content"] == "Success"


@pytest.mark.asyncio
async def test_timeout_error(mock_config: GrokConfig) -> None:
    """Test request timeout."""
    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=asyncio.TimeoutError())
    mock_session.close = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        async with GrokClient(mock_config) as c:
            with pytest.raises(OperationTimeoutError) as exc_info:
                await c.chat_completion(
                    [{"role": "user", "content": "Hello"}]
                )
            assert "timeout" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_plan_task(mock_config: GrokConfig) -> None:
    """Test task planning."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "steps": [
                                    {
                                        "action": "navigate",
                                        "target": "https://example.com",
                                        "description": "Go to site",
                                    },
                                    {
                                        "action": "extract",
                                        "target": "title",
                                        "description": "Get page title",
                                    },
                                ],
                                "reasoning": "First navigate then extract",
                                "estimated_steps": 2,
                                "requires_browser": True,
                                "requires_memory": False,
                            }
                        )
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 15,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            plan = await c.plan_task("Get title from example.com")

            assert isinstance(plan, TaskPlan)
            assert len(plan.steps) == 2
            assert plan.steps[0].action == "navigate"
            assert plan.steps[0].target == "https://example.com"
            assert plan.requires_browser is True
            assert plan.estimated_steps == 2


@pytest.mark.asyncio
async def test_plan_task_malformed_json(mock_config: GrokConfig) -> None:
    """Test handling of malformed JSON in response."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [
                {"message": {"content": "This is not JSON"}}
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 5,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            with pytest.raises(GrokAPIError) as exc_info:
                await c.plan_task("Test task")
            assert "parse plan JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_compress_text(mock_config: GrokConfig) -> None:
    """Test text compression."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": "• Point 1\n• Point 2\n• Point 3"
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 10,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            result = await c.compress_text("Long text here...", max_points=3)
            assert "Point 1" in result
            assert "Point 2" in result


@pytest.mark.asyncio
async def test_test_connection_success(mock_config: GrokConfig) -> None:
    """Test connection test - success case."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "OK"}}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 1,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            result = await c.test_connection()
            assert result is True


@pytest.mark.asyncio
async def test_test_connection_failure(mock_config: GrokConfig) -> None:
    """Test connection test - failure case."""
    mock_response = AsyncMock()
    mock_response.status = 401

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            result = await c.test_connection()
            assert result is False


@pytest.mark.asyncio
async def test_rate_limiting(mock_config: GrokConfig) -> None:
    """Test rate limiting between requests."""
    mock_config.rate_limit_calls_per_minute = 600

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "OK"}}],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 1,
            },
        }
    )

    with patch(
        "aiohttp.ClientSession",
        return_value=_make_mock_session_post(mock_response),
    ):
        async with GrokClient(mock_config) as c:
            start = asyncio.get_event_loop().time()
            await c.chat_completion([{"role": "user", "content": "1"}])
            await c.chat_completion([{"role": "user", "content": "2"}])
            duration = asyncio.get_event_loop().time() - start
            assert duration >= 0.09


def test_validation_error() -> None:
    """Test config validation on init."""
    with pytest.raises(ValidationError):
        GrokClient(GrokConfig(api_key="x", temperature=2.0))


def test_usage_stats(mock_config: GrokConfig) -> None:
    """Test usage statistics."""
    c = GrokClient(mock_config)
    c._call_count = 10
    c._total_cost = 0.15

    stats = c.get_usage_stats()
    assert stats["total_calls"] == 10
    assert stats["total_cost"] == 0.15
    assert stats["budget_limit"] == 1.0
    assert stats["budget_remaining"] == 0.85
