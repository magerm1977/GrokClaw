"""Unit tests for SQLite memory backend."""

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from grok_harness.memory.models import (
    ExtractionResult,
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
    SessionData,
    TaskEpisode,
)
from grok_harness.memory.sqlite_backend import SQLiteMemory


@pytest.fixture
def memory_db(tmp_path: Path) -> SQLiteMemory:
    """Create a temporary memory database."""
    db_path = tmp_path / "test_memory.db"
    return SQLiteMemory(
        db_path=db_path,
        auto_cleanup_days=0,
        max_items=100,
    )


@pytest.fixture
def sample_memory_item() -> MemoryItem:
    """Create a sample memory item."""
    return MemoryItem(
        id=hashlib.md5(b"test-key").hexdigest(),
        key="test-key",
        content={"data": "test content"},
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(
            tags=["test", "sample"],
            source="pytest",
        ),
    )


@pytest.mark.asyncio
async def test_store_retrieve(
    memory_db: SQLiteMemory,
    sample_memory_item: MemoryItem,
) -> None:
    """Test storing and retrieving a memory item."""
    item_id = await memory_db.store(sample_memory_item)
    assert item_id == sample_memory_item.id

    retrieved = await memory_db.retrieve("test-key")
    assert retrieved is not None
    assert retrieved.key == "test-key"
    assert retrieved.content["data"] == "test content"
    assert retrieved.type == MemoryItemType.SYSTEM
    assert "test" in retrieved.metadata.tags

    retrieved = await memory_db.retrieve_by_id(item_id)
    assert retrieved is not None
    assert retrieved.id == item_id


@pytest.mark.asyncio
async def test_retrieve_nonexistent(memory_db: SQLiteMemory) -> None:
    """Test retrieving non-existent item."""
    assert await memory_db.retrieve("nonexistent") is None
    assert await memory_db.retrieve_by_id("nonexistent") is None


@pytest.mark.asyncio
async def test_delete(
    memory_db: SQLiteMemory,
    sample_memory_item: MemoryItem,
) -> None:
    """Test deleting items."""
    await memory_db.store(sample_memory_item)

    assert await memory_db.delete("test-key") is True
    assert await memory_db.retrieve("test-key") is None

    assert await memory_db.delete("nonexistent") is False


@pytest.mark.asyncio
async def test_search(memory_db: SQLiteMemory) -> None:
    """Test searching memory items."""
    items = [
        MemoryItem(
            id=f"id{i}",
            key=f"key{i}",
            content=f"content about {'prices' if i % 2 == 0 else 'emails'}",
            type=(
                MemoryItemType.EXTRACTED_DATA
                if i % 2 == 0
                else MemoryItemType.TASK_RESULT
            ),
            metadata=MemoryMetadata(tags=["test"]),
        )
        for i in range(5)
    ]

    for item in items:
        await memory_db.store(item)

    results = await memory_db.search("prices", limit=10)
    assert len(results) >= 2

    results = await memory_db.search(
        "content",
        type_filter=MemoryItemType.TASK_RESULT,
        limit=10,
    )
    assert all(r.type == MemoryItemType.TASK_RESULT for r in results)


@pytest.mark.asyncio
async def test_search_by_type(memory_db: SQLiteMemory) -> None:
    """Test searching by memory type."""
    for i in range(3):
        await memory_db.store(
            MemoryItem(
                id=f"task{i}",
                key=f"task-key{i}",
                content=f"task {i}",
                type=MemoryItemType.TASK_RESULT,
                metadata=MemoryMetadata(),
            )
        )

    for i in range(2):
        await memory_db.store(
            MemoryItem(
                id=f"extract{i}",
                key=f"extract-key{i}",
                content=f"extract {i}",
                type=MemoryItemType.EXTRACTED_DATA,
                metadata=MemoryMetadata(),
            )
        )

    tasks = await memory_db.search_by_type(
        MemoryItemType.TASK_RESULT,
        limit=10,
    )
    assert len(tasks) == 3

    extracts = await memory_db.search_by_type(
        MemoryItemType.EXTRACTED_DATA,
        limit=10,
    )
    assert len(extracts) == 2


@pytest.mark.asyncio
async def test_clear(
    memory_db: SQLiteMemory,
    sample_memory_item: MemoryItem,
) -> None:
    """Test clearing memory."""
    await memory_db.store(sample_memory_item)

    await memory_db.clear()
    assert await memory_db.retrieve("test-key") is None

    await memory_db.store(sample_memory_item)
    await memory_db.clear(MemoryItemType.SYSTEM)
    assert await memory_db.retrieve("test-key") is None


@pytest.mark.asyncio
async def test_access_count_updates(
    memory_db: SQLiteMemory,
    sample_memory_item: MemoryItem,
) -> None:
    """Test access count increments."""
    await memory_db.store(sample_memory_item)

    item = await memory_db.retrieve("test-key")
    assert item is not None
    assert item.metadata.access_count == 1

    item = await memory_db.retrieve("test-key")
    assert item is not None
    assert item.metadata.access_count == 2


@pytest.mark.asyncio
async def test_stats(memory_db: SQLiteMemory) -> None:
    """Test getting memory statistics."""
    for i in range(5):
        await memory_db.store(
            MemoryItem(
                id=f"id{i}",
                key=f"key{i}",
                content=f"content{i}",
                type=(
                    MemoryItemType.SYSTEM
                    if i % 2 == 0
                    else MemoryItemType.TASK_RESULT
                ),
                metadata=MemoryMetadata(),
            )
        )

    stats = await memory_db.get_stats()

    assert stats["total_items"] == 5
    assert "system" in stats["items_by_type"]
    assert "task_result" in stats["items_by_type"]
    assert stats["total_accesses"] >= 0
    assert stats["db_size_bytes"] > 0


@pytest.mark.asyncio
async def test_task_episode_storage(memory_db: SQLiteMemory) -> None:
    """Test storing and retrieving task episodes."""
    episode = TaskEpisode(
        task_id="test-task-1",
        goal="Get page title from example.com",
        steps_taken=3,
        success=True,
        duration_ms=1500,
        results={"title": "Example Domain"},
        action_history=[
            {"action": "navigate", "target": "https://example.com"},
            {"action": "extract", "target": "title"},
        ],
    )

    item_id = await memory_db.store_task_episode(episode)
    assert item_id == "test-task-1"

    episodes = await memory_db.get_task_episodes(limit=10)
    assert len(episodes) == 1
    assert episodes[0].goal == "Get page title from example.com"
    assert episodes[0].results["title"] == "Example Domain"

    episodes = await memory_db.get_task_episodes(
        limit=10,
        successful_only=True,
    )
    assert len(episodes) == 1

    failed = TaskEpisode(
        task_id="test-task-2",
        goal="Failed task",
        steps_taken=2,
        success=False,
        duration_ms=500,
        results={},
        action_history=[],
        error="Navigation failed",
    )
    await memory_db.store_task_episode(failed)

    episodes = await memory_db.get_task_episodes(
        limit=10,
        successful_only=True,
    )
    assert len(episodes) == 1


@pytest.mark.asyncio
async def test_extraction_storage(memory_db: SQLiteMemory) -> None:
    """Test storing and retrieving extraction results."""
    extraction = ExtractionResult(
        source_url="https://example.com",
        extracted_at=datetime.now(),
        data_type="prices",
        data={"product": "$19.99"},
        confidence=0.95,
    )

    await memory_db.store_extraction(extraction)

    extractions = await memory_db.get_extractions(
        source_url="https://example.com",
        limit=10,
    )
    assert len(extractions) == 1
    assert extractions[0].data_type == "prices"
    assert extractions[0].data["product"] == "$19.99"

    extractions = await memory_db.get_extractions(
        data_type="prices",
        limit=10,
    )
    assert len(extractions) == 1


@pytest.mark.asyncio
async def test_session_storage(memory_db: SQLiteMemory) -> None:
    """Test storing and retrieving session data."""
    session = SessionData(
        session_id="test-session-1",
        url="https://example.com",
        cookies=[{"name": "session", "value": "123"}],
        local_storage={"key": "value"},
        created_at=datetime.now(),
    )

    await memory_db.store_session(session)

    retrieved = await memory_db.get_session("test-session-1")
    assert retrieved is not None
    assert retrieved.url == "https://example.com"
    assert len(retrieved.cookies) == 1
    assert retrieved.cookies[0]["name"] == "session"


@pytest.mark.asyncio
async def test_find_similar_tasks(memory_db: SQLiteMemory) -> None:
    """Test finding similar tasks by goal."""
    tasks = [
        TaskEpisode(
            task_id=f"task{i}",
            goal=f"Get {'prices' if i % 2 == 0 else 'emails'} from website",
            steps_taken=3,
            success=True,
            duration_ms=1000,
            results={},
            action_history=[],
        )
        for i in range(5)
    ]

    for task in tasks:
        await memory_db.store_task_episode(task)

    similar = await memory_db.find_similar_tasks(
        "find prices on site",
        limit=5,
    )
    assert len(similar) >= 2


@pytest.mark.asyncio
async def test_auto_cleanup(tmp_path: Path) -> None:
    """Test automatic cleanup of old items."""
    db_path = tmp_path / "test_cleanup.db"
    memory = SQLiteMemory(
        db_path=db_path,
        auto_cleanup_days=1,
        max_items=5,
    )

    for i in range(10):
        metadata = MemoryMetadata()
        if i < 5:
            metadata.created_at = datetime.now() - timedelta(days=2)

        await memory.store(
            MemoryItem(
                id=f"id{i}",
                key=f"key{i}",
                content=f"content{i}",
                type=MemoryItemType.SYSTEM,
                metadata=metadata,
            )
        )

    await memory.store(
        MemoryItem(
            id="trigger",
            key="trigger",
            content="trigger",
            type=MemoryItemType.SYSTEM,
            metadata=MemoryMetadata(),
        )
    )

    stats = await memory.get_stats()
    assert stats["total_items"] <= 6


@pytest.mark.asyncio
async def test_vacuum(
    memory_db: SQLiteMemory,
    sample_memory_item: MemoryItem,
) -> None:
    """Test vacuum operation."""
    await memory_db.store(sample_memory_item)

    await memory_db.vacuum()

    assert await memory_db.retrieve("test-key") is not None


@pytest.mark.asyncio
async def test_content_json_handling(memory_db: SQLiteMemory) -> None:
    """Test handling of JSON vs string content."""
    dict_item = MemoryItem(
        id="dict-id",
        key="dict-key",
        content={"nested": {"data": [1, 2, 3]}},
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    await memory_db.store(dict_item)

    retrieved = await memory_db.retrieve("dict-key")
    assert retrieved is not None
    assert isinstance(retrieved.content, dict)
    assert retrieved.content["nested"]["data"][0] == 1

    str_item = MemoryItem(
        id="str-id",
        key="str-key",
        content="plain text content",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    await memory_db.store(str_item)

    retrieved = await memory_db.retrieve("str-key")
    assert retrieved is not None
    assert isinstance(retrieved.content, str)
    assert retrieved.content == "plain text content"
