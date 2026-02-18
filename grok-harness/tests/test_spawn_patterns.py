#!/usr/bin/env python
"""
Test spawn pattern detection.
"""

import asyncio
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Ensure src is on path for standalone run
if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.orchestrator import Orchestrator
from grok_harness.core.session_manager import SessionManager
from grok_harness.memory.unified import UnifiedMemory
from grok_harness.scheduler.smart import SmartScheduler


# Patterns used in orchestrator (keep in sync)
SPAWN_PATTERNS = [
    r"spawn (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"create (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"start (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"launch (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"need (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"could you spawn (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    r"can you spawn (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
]


def test_spawn_pattern_regex() -> None:
    """Test that spawn patterns match expected phrases."""
    test_cases = [
        ("spawn a researcher to find AI news", "researcher", "find AI news"),
        ("spawn researcher to find AI news", "researcher", "find AI news"),
        ("create a writer to write a summary", "writer", "write a summary"),
        ("start an analyst to analyze data", "analyst", "analyze data"),
        ("launch a critic to review my code", "critic", "review my code"),
        ("need a coder to write a script", "coder", "write a script"),
        (
            "can you spawn a translator to convert this",
            "translator",
            "convert this",
        ),
        (
            "could you spawn a summarizer to summarize the report",
            "summarizer",
            "summarize the report",
        ),
    ]
    for phrase, expected_type, expected_task in test_cases:
        matched = False
        for pattern in SPAWN_PATTERNS:
            m = re.search(pattern, phrase, re.IGNORECASE | re.DOTALL)
            if m:
                assert m.group(1).lower() == expected_type, (
                    f"'{phrase}': expected type {expected_type}, got {m.group(1)}"
                )
                assert expected_task in m.group(2) or m.group(2) in expected_task, (
                    f"'{phrase}': expected task containing '{expected_task}', "
                    f"got '{m.group(2)}'"
                )
                matched = True
                break
        assert matched, f"'{phrase}' did not match any spawn pattern"


def test_spawn_patterns_no_false_positives() -> None:
    """Ensure non-spawn phrases don't match."""
    non_spawn = [
        "what's the weather in London",
        "navigate to example.com",
        "tell me a joke",
        "hello",
    ]
    for phrase in non_spawn:
        for pattern in SPAWN_PATTERNS:
            m = re.search(pattern, phrase, re.IGNORECASE)
            assert m is None, f"'{phrase}' should not match spawn pattern"


@pytest.mark.asyncio
async def test_try_builtin_tool_spawn(tmp_path: Path) -> None:
    """Test _try_builtin_tool spawn matching with mocked session manager."""
    from grok_harness.core.types import MemoryConfig

    config = ConfigManager.create_default_config()
    memory = UnifiedMemory(
        MemoryConfig(
            path=tmp_path / "mem.db",
            enable_embeddings=False,
            low_spec_mode=True,
        )
    )
    await memory.start()

    scheduler = SmartScheduler(
        grok_client=None,
        storage_path=tmp_path,
        enable_learning=False,
        enable_predictive=False,
        enable_monitoring=False,
    )
    await scheduler.start()

    mock_session_manager = AsyncMock(spec=SessionManager)
    mock_session_manager.create_session = AsyncMock(return_value="test-session-1")
    mock_session_manager.send_message = AsyncMock(
        return_value={"success": True, "result": "Test result"}
    )
    mock_session_manager.terminate_session = AsyncMock(return_value=True)
    mock_session_manager.sessions = {}

    mock_grok = AsyncMock()

    orchestrator = Orchestrator(
        config=config,
        grok=mock_grok,
        memory=memory,
        scheduler=scheduler,
        session_manager=mock_session_manager,
    )

    try:
        result = await orchestrator._try_builtin_tool(
            "spawn a researcher to find AI news"
        )
        assert result is not None
        assert result.get("tool") == "spawn_agent"
        assert result.get("result", {}).get("success") is True
        assert result.get("result", {}).get("agent_name") == "researcher"
    finally:
        await scheduler.stop()
        await memory.stop()
