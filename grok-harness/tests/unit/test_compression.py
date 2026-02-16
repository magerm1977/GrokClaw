"""Unit tests for memory compression module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from grok_harness.memory.compression import AutoCompressor, MemoryCompressor
from grok_harness.memory.models import (
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
)
from grok_harness.memory.sqlite_backend import SQLiteMemory


@pytest.fixture
def mock_grok_client() -> AsyncMock:
    """Mock Grok client for compression."""
    client = AsyncMock()
    client.compress_memory = AsyncMock(
        return_value="• Point 1\n• Point 2\n• Point 3"
    )
    return client


@pytest.fixture
def memory_db(tmp_path: Path) -> SQLiteMemory:
    """Create test memory database."""
    db_path = tmp_path / "test_compression.db"
    return SQLiteMemory(db_path=db_path)


@pytest.fixture
def compressor(mock_grok_client: AsyncMock) -> MemoryCompressor:
    """Create compressor with mock Grok."""
    return MemoryCompressor(
        grok_client=mock_grok_client,
        threshold=3,
        auto_compress=True,
    )


@pytest.mark.asyncio
async def test_should_compress_force(compressor: MemoryCompressor) -> None:
    """Test force compression."""
    items = [
        MemoryItem(
            id="1",
            key="k1",
            content="x",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
    ]
    assert await compressor.should_compress(items, force=True) is True


@pytest.mark.asyncio
async def test_should_compress_threshold(compressor: MemoryCompressor) -> None:
    """Test compression threshold."""
    items = [
        MemoryItem(
            id=str(i),
            key=f"k{i}",
            content="x",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
        for i in range(3)
    ]
    assert await compressor.should_compress(items) is True
    assert await compressor.should_compress(items[:2]) is False


@pytest.mark.asyncio
async def test_compress_items_grouped(
    compressor: MemoryCompressor,
    mock_grok_client: AsyncMock,
) -> None:
    """Test compressing items grouped by type."""
    items = [
        MemoryItem(
            id=f"task{i}",
            key=f"task-key{i}",
            content={"goal": f"Goal {i}", "results": {}},
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(tags=["test"]),
        )
        for i in range(4)
    ]

    compressed = await compressor.compress_items(
        items,
        max_points=5,
        group_by_type=True,
    )

    assert len(compressed) == 1
    assert compressed[0].type == MemoryItemType.COMPRESSED
    assert "summary" in compressed[0].content
    assert compressed[0].content["source_count"] == 4
    assert len(compressed[0].content["source_ids"]) == 4
    mock_grok_client.compress_memory.assert_called_once()


@pytest.mark.asyncio
async def test_compress_items_single(compressor: MemoryCompressor) -> None:
    """Test single item returns unchanged."""
    item = MemoryItem(
        id="1",
        key="k1",
        content="single",
        type=MemoryItemType.TASK_RESULT,
        metadata=MemoryMetadata(),
    )
    compressed = await compressor.compress_items([item])
    assert compressed == [item]


@pytest.mark.asyncio
async def test_decompress(
    compressor: MemoryCompressor,
    mock_grok_client: AsyncMock,
) -> None:
    """Test decompression returns reference items."""
    items = [
        MemoryItem(
            id=f"d{i}",
            key=f"dk{i}",
            content={"goal": f"G{i}"},
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
        for i in range(3)
    ]
    compressed = await compressor.compress_items(items)

    decompressed = await compressor.decompress(compressed[0])

    assert len(decompressed) == 3
    assert all(
        item.type == MemoryItemType.REFERENCE for item in decompressed
    )
    assert all(
        "compressed_in" in item.content for item in decompressed
    )


@pytest.mark.asyncio
async def test_decompress_non_compressed(compressor: MemoryCompressor) -> None:
    """Test decompress on non-compressed item returns as-is."""
    item = MemoryItem(
        id="1",
        key="k1",
        content="plain",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    result = await compressor.decompress(item)
    assert result == [item]


@pytest.mark.asyncio
async def test_compress_stats(
    compressor: MemoryCompressor,
    mock_grok_client: AsyncMock,
) -> None:
    """Test compression statistics."""
    items = [
        MemoryItem(
            id=str(i),
            key=f"k{i}",
            content=f"Content {i}",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
        for i in range(5)
    ]
    await compressor.compress_items(items)

    stats = compressor.get_stats()
    assert stats["total_compressions"] == 1
    assert stats["total_items_compressed"] == 5
    assert "last_compression" in stats


@pytest.mark.asyncio
async def test_item_to_string_task(compressor: MemoryCompressor) -> None:
    """Test task result serialization for compression."""
    item = MemoryItem(
        id="1",
        key="k1",
        content={
            "goal": "Get prices",
            "results": {"price": "$10"},
        },
        type=MemoryItemType.TASK_RESULT,
        metadata=MemoryMetadata(tags=["test"]),
    )
    s = compressor._item_to_string(item)
    assert "Get prices" in s
    assert "$10" in s


@pytest.mark.asyncio
async def test_auto_compressor_start_stop(
    compressor: MemoryCompressor,
    memory_db: SQLiteMemory,
) -> None:
    """Test auto compressor start and stop."""
    auto = AutoCompressor(
        compressor=compressor,
        memory_backend=memory_db,
        check_interval_minutes=1,
        min_age_days=7,
        min_access_count=3,
    )
    await auto.start()
    assert auto._running is True
    await auto.stop()
    assert auto._running is False


@pytest.mark.asyncio
async def test_compress_failure_returns_originals(
    mock_grok_client: AsyncMock,
) -> None:
    """Test that failed compression returns original items."""
    mock_grok_client.compress_memory = AsyncMock(side_effect=Exception("API"))
    compressor = MemoryCompressor(
        grok_client=mock_grok_client,
        threshold=2,
    )

    items = [
        MemoryItem(
            id=f"f{i}",
            key=f"fk{i}",
            content="fail",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
        for i in range(2)
    ]

    result = await compressor.compress_items(items)
    assert result == items
