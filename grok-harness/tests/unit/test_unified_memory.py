"""Unit tests for unified memory interface."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from grok_harness.core.grok_client import GrokClient
from grok_harness.core.types import MemoryConfig, MemoryType
from grok_harness.memory.models import (
    ExtractionResult,
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
    SessionData,
    TaskEpisode,
)
from grok_harness.memory.unified import UnifiedMemory


@pytest.fixture
def memory_config(tmp_path: Path) -> MemoryConfig:
    """Memory configuration fixture."""
    return MemoryConfig(
        type=MemoryType.SQLITE,
        path=tmp_path / "test_unified.db",
        ttl_days=30,
        max_items=100,
        enable_embeddings=True,
        low_spec_mode=False,
        enable_compression=True,
        compression_threshold=3,
    )


@pytest.fixture
def mock_grok_client() -> AsyncMock:
    """Mock Grok client for compression."""
    client = AsyncMock(spec=GrokClient)
    client.compress_memory = AsyncMock(
        return_value="• Point 1\n• Point 2\n• Point 3"
    )
    return client


@pytest.fixture
async def unified_memory(memory_config: MemoryConfig, mock_grok_client: AsyncMock):
    """Create unified memory instance."""
    with patch(
        "grok_harness.memory.embeddings.SentenceTransformer",
    ) as mock_transformer:
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        vec = np.full(384, 0.1, dtype=np.float32)

        def _encode(x, batch_size=32):
            return (
                vec.copy()
                if isinstance(x, str)
                else np.array([vec.copy() for _ in range(len(x))])
            )

        mock_model.encode.side_effect = _encode
        mock_transformer.return_value = mock_model

        with patch(
            "grok_harness.memory.embeddings.SENTENCE_TRANSFORMERS_AVAILABLE",
            True,
        ):
            memory = UnifiedMemory(
                memory_config,
                grok_client=mock_grok_client,
            )
            await memory.start()
            yield memory
            await memory.stop()


@pytest.mark.asyncio
async def test_store_retrieve(unified_memory: UnifiedMemory) -> None:
    """Test basic store and retrieve."""
    item = MemoryItem(
        id="test1",
        key="test-key",
        content={"data": "test content"},
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(tags=["test"]),
    )

    item_id = await unified_memory.store(item)
    assert item_id == "test1"

    retrieved = await unified_memory.retrieve("test-key")
    assert retrieved is not None
    assert retrieved.content["data"] == "test content"

    retrieved = await unified_memory.retrieve_by_id("test1")
    assert retrieved is not None


@pytest.mark.asyncio
async def test_search(unified_memory: UnifiedMemory) -> None:
    """Test search functionality."""
    for i in range(5):
        item = MemoryItem(
            id=f"item{i}",
            key=f"key{i}",
            content=f"content about {'prices' if i % 2 == 0 else 'emails'}",
            type=(
                MemoryItemType.EXTRACTED_DATA
                if i % 2 == 0
                else MemoryItemType.TASK_RESULT
            ),
            metadata=MemoryMetadata(tags=["test"]),
        )
        await unified_memory.store(item)

    results = await unified_memory.search("prices", limit=10)
    assert len(results) >= 2

    results = await unified_memory.search(
        "content",
        type_filter=MemoryItemType.TASK_RESULT,
        limit=10,
    )
    assert all(r.type == MemoryItemType.TASK_RESULT for r in results)


@pytest.mark.asyncio
async def test_task_operations(unified_memory: UnifiedMemory) -> None:
    """Test task episode operations."""
    episode = TaskEpisode(
        task_id="task1",
        goal="Get prices from example.com",
        steps_taken=3,
        success=True,
        duration_ms=1500,
        results={"prices": ["$19.99", "$29.99"]},
        action_history=[
            {"action": "navigate", "target": "https://example.com"},
            {"action": "extract", "target": "prices"},
        ],
    )

    item_id = await unified_memory.store_task(episode)
    assert item_id == "task1"

    recent = await unified_memory.get_recent_tasks(limit=5)
    assert len(recent) == 1
    assert recent[0].goal == "Get prices from example.com"

    # Use "prices" to match keyword fallback (words >3 chars) or semantic search
    similar = await unified_memory.find_similar_tasks(
        "get product prices",
        limit=5,
        threshold=0.0,
    )
    assert isinstance(similar, list)
    assert len(similar) > 0  # "prices" matches stored goal "Get prices from..."


@pytest.mark.asyncio
async def test_extraction_operations(unified_memory: UnifiedMemory) -> None:
    """Test extraction operations."""
    extraction = ExtractionResult(
        source_url="https://example.com",
        extracted_at=datetime.now(),
        data_type="prices",
        data=[{"product": "Widget", "price": "$9.99"}],
        confidence=0.95,
    )

    await unified_memory.store_extraction(extraction)

    extractions = await unified_memory.get_extractions(
        source_url="https://example.com",
        limit=5,
    )
    assert len(extractions) == 1
    assert extractions[0].data_type == "prices"

    similar = await unified_memory.find_similar_extractions(
        data_type="prices",
        value="$9.99",
        limit=5,
        threshold=0.0,
    )
    assert isinstance(similar, list)


@pytest.mark.asyncio
async def test_session_operations(unified_memory: UnifiedMemory) -> None:
    """Test session operations."""
    session = SessionData(
        session_id="sess1",
        url="https://example.com",
        cookies=[{"name": "session", "value": "123"}],
        local_storage={"pref": "dark"},
        created_at=datetime.now(),
    )

    await unified_memory.store_session(session)

    retrieved = await unified_memory.get_session("sess1")
    assert retrieved is not None
    assert retrieved.url == "https://example.com"
    assert len(retrieved.cookies) == 1


@pytest.mark.asyncio
async def test_compression(unified_memory: UnifiedMemory) -> None:
    """Test memory compression."""
    items = []
    for i in range(5):
        item = MemoryItem(
            id=f"compress{i}",
            key=f"compress-key{i}",
            content=f"Item {i} with some content to compress",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(tags=["compress"]),
        )
        await unified_memory.store(item)
        items.append(item)

    compressed = await unified_memory.compress(items)

    assert len(compressed) >= 1
    assert compressed[0].type == MemoryItemType.COMPRESSED
    assert "summary" in compressed[0].content

    for item in items:
        retrieved = await unified_memory.retrieve(item.key)
        assert retrieved is None


@pytest.mark.asyncio
async def test_decompress(unified_memory: UnifiedMemory) -> None:
    """Test decompression."""
    items = [
        MemoryItem(
            id=f"decompress{i}",
            key=f"decompress-key{i}",
            content=f"Original {i}",
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(),
        )
        for i in range(3)
    ]

    compressed = await unified_memory.compress(items)

    decompressed = await unified_memory.decompress(compressed[0])

    assert len(decompressed) == 3
    assert all(
        item.type == MemoryItemType.REFERENCE for item in decompressed
    )
    assert all(
        "compressed_in" in item.content for item in decompressed
    )


@pytest.mark.asyncio
async def test_search_by_type(unified_memory: UnifiedMemory) -> None:
    """Test searching by type."""
    for i in range(3):
        await unified_memory.store(
            MemoryItem(
                id=f"task{i}",
                key=f"task-key{i}",
                content=f"task {i}",
                type=MemoryItemType.TASK_RESULT,
                metadata=MemoryMetadata(),
            )
        )

    for i in range(2):
        await unified_memory.store(
            MemoryItem(
                id=f"extract{i}",
                key=f"extract-key{i}",
                content=f"extract {i}",
                type=MemoryItemType.EXTRACTED_DATA,
                metadata=MemoryMetadata(),
            )
        )

    tasks = await unified_memory.search_by_type(
        MemoryItemType.TASK_RESULT,
        limit=10,
    )
    assert len(tasks) == 3

    extracts = await unified_memory.search_by_type(
        MemoryItemType.EXTRACTED_DATA,
        limit=10,
    )
    assert len(extracts) == 2


@pytest.mark.asyncio
async def test_delete(unified_memory: UnifiedMemory) -> None:
    """Test delete operations."""
    item = MemoryItem(
        id="delete-test",
        key="delete-key",
        content="to be deleted",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )

    await unified_memory.store(item)

    assert await unified_memory.delete("delete-key") is True
    assert await unified_memory.retrieve("delete-key") is None

    assert await unified_memory.delete("nonexistent") is False


@pytest.mark.asyncio
async def test_clear(unified_memory: UnifiedMemory) -> None:
    """Test clearing memory."""
    for i in range(3):
        await unified_memory.store(
            MemoryItem(
                id=f"clear{i}",
                key=f"clear-key{i}",
                content=f"item {i}",
                type=(
                    MemoryItemType.SYSTEM
                    if i % 2 == 0
                    else MemoryItemType.TASK_RESULT
                ),
                metadata=MemoryMetadata(),
            )
        )

    await unified_memory.clear(MemoryItemType.SYSTEM)

    items = await unified_memory.search_by_type(
        MemoryItemType.SYSTEM,
        limit=10,
    )
    assert len(items) == 0

    items = await unified_memory.search_by_type(
        MemoryItemType.TASK_RESULT,
        limit=10,
    )
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_stats(unified_memory: UnifiedMemory) -> None:
    """Test getting statistics."""
    item = MemoryItem(
        id="stats-test",
        key="stats-key",
        content="stats test",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    await unified_memory.store(item)
    await unified_memory.retrieve("stats-key")
    await unified_memory.search("test", limit=5)

    stats = await unified_memory.get_stats()

    assert "total_items" in stats
    assert "operations" in stats
    assert stats["operations"]["stores"] >= 1
    assert stats["operations"]["retrievals"] >= 1
    assert stats["operations"]["searches"] >= 1


@pytest.mark.asyncio
async def test_context_manager(
    memory_config: MemoryConfig,
    mock_grok_client: AsyncMock,
) -> None:
    """Test async context manager."""
    with patch(
        "grok_harness.memory.embeddings.SentenceTransformer",
    ) as mock_transformer:
        mock_model = Mock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        vec = np.full(384, 0.1, dtype=np.float32)
        mock_model.encode.side_effect = lambda x, batch_size=32: (
            vec.copy()
            if isinstance(x, str)
            else np.array([vec.copy() for _ in range(len(x))])
        )
        mock_transformer.return_value = mock_model

        with patch(
            "grok_harness.memory.embeddings.SENTENCE_TRANSFORMERS_AVAILABLE",
            True,
        ):
            async with UnifiedMemory(
                memory_config,
                grok_client=mock_grok_client,
            ) as memory:
                item = MemoryItem(
                    id="ctx-test",
                    key="ctx-key",
                    content="context test",
                    type=MemoryItemType.SYSTEM,
                    metadata=MemoryMetadata(),
                )
                await memory.store(item)

                retrieved = await memory.retrieve("ctx-key")
                assert retrieved is not None


@pytest.mark.asyncio
async def test_vacuum(unified_memory: UnifiedMemory) -> None:
    """Test vacuum operation."""
    await unified_memory.vacuum()

    item = MemoryItem(
        id="vacuum-test",
        key="vacuum-key",
        content="after vacuum",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    await unified_memory.store(item)
    assert await unified_memory.retrieve("vacuum-key") is not None
