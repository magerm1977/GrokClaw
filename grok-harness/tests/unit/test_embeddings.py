"""Unit tests for embedding module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("numpy")

import numpy as np

from grok_harness.memory.embeddings import (
    EmbeddingEngine,
    EmbeddingVector,
    HybridSearch,
)
from grok_harness.memory.models import (
    ExtractionResult,
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
    TaskEpisode,
)
from grok_harness.memory.sqlite_backend import SQLiteMemory
from grok_harness.utils.errors import EmbeddingError


@pytest.fixture
def memory_db(tmp_path: Path) -> SQLiteMemory:
    """Create test memory database."""
    db_path = tmp_path / "test_memory.db"
    return SQLiteMemory(db_path=db_path)


@pytest.fixture
def mock_sentence_transformer() -> Mock:
    """Mock SentenceTransformer."""
    mock = Mock()
    mock.get_sentence_embedding_dimension.return_value = 384
    def _encode(x, batch_size=32):
        return (
            np.random.randn(384).astype(np.float32)
            if isinstance(x, str)
            else np.random.randn(len(x), 384).astype(np.float32)
        )

    mock.encode.side_effect = _encode
    return mock


@pytest.fixture
def embedding_engine(
    memory_db: SQLiteMemory,
    mock_sentence_transformer: Mock,
) -> EmbeddingEngine:
    """Create embedding engine with mocked model."""
    with patch(
        "grok_harness.memory.embeddings.SentenceTransformer",
        return_value=mock_sentence_transformer,
    ):
        with patch(
            "grok_harness.memory.embeddings.SENTENCE_TRANSFORMERS_AVAILABLE",
            True,
        ):
            return EmbeddingEngine(
                memory=memory_db,
                model="local",
                use_cache=True,
            )


@pytest.mark.asyncio
async def test_embed_local(
    embedding_engine: EmbeddingEngine,
) -> None:
    """Test local embedding generation."""
    text = "This is a test sentence"
    vector = await embedding_engine.embed(text)

    assert isinstance(vector, np.ndarray)
    assert vector.shape[0] == 384


@pytest.mark.asyncio
async def test_embed_cache(embedding_engine: EmbeddingEngine) -> None:
    """Test embedding caching."""
    text = "Test caching"

    vec1 = await embedding_engine.embed(text)
    vec2 = await embedding_engine.embed(text)

    assert np.array_equal(vec1, vec2)
    assert len(embedding_engine.cache) == 1


@pytest.mark.asyncio
async def test_similarity(embedding_engine: EmbeddingEngine) -> None:
    """Test similarity computation."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([1.0, 0.0, 0.0])
    vec3 = np.array([0.0, 1.0, 0.0])

    sim = await embedding_engine.similarity(vec1, vec2)
    assert abs(sim - 1.0) < 0.001

    sim = await embedding_engine.similarity(vec1, vec3)
    assert abs(sim - 0.0) < 0.001


@pytest.mark.asyncio
async def test_search_similar(
    embedding_engine: EmbeddingEngine,
    memory_db: SQLiteMemory,
) -> None:
    """Test semantic search."""
    for i, text in enumerate([
        "Get product prices from website",
        "Find email addresses on contact page",
        "Extract phone numbers from listings",
    ]):
        item = MemoryItem(
            id=f"task{i}",
            key=f"task-key{i}",
            content={"goal": text, "results": {"data": f"result{i}"}},
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(tags=["test"]),
        )
        await memory_db.store(item)

    results = await embedding_engine.search_similar(
        query="find prices online",
        limit=3,
        threshold=0.0,
    )

    assert isinstance(results, list)
    assert all(
        isinstance(r, tuple) and len(r) == 2 for r in results
    )


@pytest.mark.asyncio
async def test_find_similar_tasks(
    embedding_engine: EmbeddingEngine,
    memory_db: SQLiteMemory,
) -> None:
    """Test finding similar tasks by goal."""
    for i, goal in enumerate([
        "Get product prices from Amazon",
        "Find email on contact page",
        "Extract phone numbers",
    ]):
        task = TaskEpisode(
            task_id=f"task{i}",
            goal=goal,
            steps_taken=3,
            success=True,
            duration_ms=1000,
            results={},
            action_history=[],
        )
        await memory_db.store_task_episode(task)

    similar = await embedding_engine.find_similar_tasks(
        goal="find prices on website",
        limit=2,
        threshold=0.0,
    )

    assert isinstance(similar, list)


@pytest.mark.asyncio
async def test_batch_embed(embedding_engine: EmbeddingEngine) -> None:
    """Test batch embedding."""
    texts = ["First sentence", "Second sentence", "Third sentence"]

    vectors = await embedding_engine.batch_embed(texts)

    assert len(vectors) == 3
    assert all(isinstance(v, np.ndarray) for v in vectors)


@pytest.mark.asyncio
async def test_embedding_vector_serialization() -> None:
    """Test EmbeddingVector serialization."""
    vector = EmbeddingVector(
        vector=np.array([1.0, 2.0, 3.0]),
        model="test",
        dimension=3,
        created_at=datetime.now(),
    )

    data = vector.to_bytes()
    assert isinstance(data, bytes)

    restored = EmbeddingVector.from_bytes(data)
    assert np.array_equal(restored.vector, vector.vector)
    assert restored.model == vector.model
    assert restored.dimension == vector.dimension


@pytest.mark.asyncio
async def test_hybrid_search(
    embedding_engine: EmbeddingEngine,
    memory_db: SQLiteMemory,
) -> None:
    """Test hybrid search combining keyword and semantic."""
    hybrid = HybridSearch(memory_db, embedding_engine)

    for i, text in enumerate([
        "Get product prices from store",
        "Find email addresses",
        "Extract phone numbers",
    ]):
        item = MemoryItem(
            id=f"item{i}",
            key=f"key{i}",
            content={"goal": text},
            type=MemoryItemType.TASK_RESULT,
            metadata=MemoryMetadata(tags=["test"]),
        )
        await memory_db.store(item)

    results1 = await hybrid.search(
        query="prices",
        limit=5,
        semantic_weight=0.3,
    )

    # Use "product" to match keyword FTS in "Get product prices from store"
    results2 = await hybrid.search(
        query="product",
        limit=5,
        semantic_weight=0.7,
    )

    assert len(results1) > 0
    assert len(results2) > 0


@pytest.mark.asyncio
async def test_embedding_error_handling(memory_db: SQLiteMemory) -> None:
    """Test error handling when sentence-transformers not available."""
    with patch(
        "grok_harness.memory.embeddings.SENTENCE_TRANSFORMERS_AVAILABLE",
        False,
    ):
        with pytest.raises(EmbeddingError) as exc_info:
            EmbeddingEngine(memory=memory_db, model="local")
        assert "sentence-transformers" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_grok_embedding(
    memory_db: SQLiteMemory,
) -> None:
    """Test Grok API embeddings."""
    mock_grok = AsyncMock()

    engine = EmbeddingEngine(
        memory=memory_db,
        grok_client=mock_grok,
        model="grok",
    )

    vector = await engine.embed("Test with Grok")
    assert isinstance(vector, np.ndarray)
    assert vector.shape[0] == 1536


@pytest.mark.asyncio
async def test_cache_cleanup(embedding_engine: EmbeddingEngine) -> None:
    """Test cache cleanup when size exceeded."""
    embedding_engine.cache_size = 2

    await embedding_engine.embed("First")
    await embedding_engine.embed("Second")
    await embedding_engine.embed("Third")

    assert len(embedding_engine.cache) <= 2


def test_get_item_text(
    embedding_engine: EmbeddingEngine,
) -> None:
    """Test text extraction from different item types."""
    task_item = MemoryItem(
        id="task1",
        key="task1",
        content={
            "goal": "Test goal",
            "results": {"price": "$10", "title": "Product"},
        },
        type=MemoryItemType.TASK_RESULT,
        metadata=MemoryMetadata(),
    )
    text = embedding_engine._get_item_text(task_item)
    assert "Test goal" in text
    assert "$10" in text

    extract_item = MemoryItem(
        id="extract1",
        key="extract1",
        content={
            "data_type": "prices",
            "data": [{"price": "$20"}, {"price": "$30"}],
        },
        type=MemoryItemType.EXTRACTED_DATA,
        metadata=MemoryMetadata(),
    )
    text = embedding_engine._get_item_text(extract_item)
    assert "$20" in text or "prices" in text or "$30" in text

    string_item = MemoryItem(
        id="string1",
        key="string1",
        content="Plain text content",
        type=MemoryItemType.SYSTEM,
        metadata=MemoryMetadata(),
    )
    text = embedding_engine._get_item_text(string_item)
    assert text == "Plain text content"


def test_stats(embedding_engine: EmbeddingEngine) -> None:
    """Test getting embedding engine stats."""
    stats = embedding_engine.get_stats()

    assert "model" in stats
    assert "dimension" in stats
    assert "cache_size" in stats
    assert "cache_enabled" in stats
    assert "backend" in stats


@pytest.mark.asyncio
async def test_clear_cache(embedding_engine: EmbeddingEngine) -> None:
    """Test clearing cache."""
    await embedding_engine.embed("Test 1")
    await embedding_engine.embed("Test 2")

    assert len(embedding_engine.cache) == 2

    await embedding_engine.clear_cache()
    assert len(embedding_engine.cache) == 0


@pytest.mark.asyncio
async def test_find_similar_extractions(
    embedding_engine: EmbeddingEngine,
    memory_db: SQLiteMemory,
) -> None:
    """Test finding similar extractions."""
    extraction = ExtractionResult(
        source_url="https://example.com",
        extracted_at=datetime.now(),
        data_type="prices",
        data={"product": "$19.99"},
        confidence=0.95,
    )
    await memory_db.store_extraction(extraction)

    similar = await embedding_engine.find_similar_extractions(
        data_type="prices",
        value="$19.99 product",
        limit=5,
        threshold=0.0,
    )

    assert isinstance(similar, list)
