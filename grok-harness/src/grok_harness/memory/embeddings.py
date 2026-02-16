"""Embedding generation and similarity search."""

import asyncio
import hashlib
import json
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.errors import EmbeddingError
from .models import MemoryItem, MemoryItemType
from .sqlite_backend import SQLiteMemory

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore[misc, assignment]
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@dataclass
class EmbeddingVector:
    """Embedding vector with metadata."""

    vector: "np.ndarray"
    model: str
    dimension: int
    created_at: datetime

    def to_bytes(self) -> bytes:
        """Convert to bytes for storage."""
        return pickle.dumps(
            {
                "vector": self.vector,
                "model": self.model,
                "dimension": self.dimension,
                "created_at": self.created_at.isoformat(),
            }
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "EmbeddingVector":
        """Create from stored bytes."""
        obj = pickle.loads(data)
        return cls(
            vector=obj["vector"],
            model=obj["model"],
            dimension=obj["dimension"],
            created_at=datetime.fromisoformat(obj["created_at"]),
        )


class EmbeddingEngine:
    """
    Embedding generation and similarity search.

    Supports multiple backends:
    - sentence-transformers (local, default)
    - Grok API (cloud, fallback)
    """

    DEFAULT_MODELS = {
        "local": "all-MiniLM-L6-v2",
        "grok": "grok-4-embedding",
    }

    CACHE_DIR = Path.home() / ".grok-harness" / "cache" / "embeddings"

    def __init__(
        self,
        memory: SQLiteMemory,
        grok_client: Optional[Any] = None,
        model: str = "local",
        use_cache: bool = True,
        cache_size: int = 1000,
    ) -> None:
        """
        Initialize embedding engine.

        Args:
            memory: SQLiteMemory instance for storing embeddings
            grok_client: Optional Grok client for cloud embeddings
            model: Model to use ('local', 'grok', or custom path)
            use_cache: Cache embeddings in memory
            cache_size: Maximum cache entries
        """
        self.memory = memory
        self.grok = grok_client
        self.model_name = model
        self.use_cache = use_cache
        self.cache_size = cache_size

        self.model: Any = None
        self.model_dimension: Optional[int] = None
        self._init_model()

        self.cache: Dict[str, Tuple[Any, datetime]] = {}

        if use_cache:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _init_model(self) -> None:
        """Initialize the embedding model."""
        if self.model_name in ("local",) or self.model_name.startswith(
            "sentence-transformers/"
        ):
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise EmbeddingError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

            model_path = self.model_name.replace(
                "sentence-transformers/", ""
            )
            if model_path == "local":
                model_path = self.DEFAULT_MODELS["local"]

            try:
                if SentenceTransformer is None:
                    raise ImportError("sentence-transformers not installed")
                self.model = SentenceTransformer(model_path)
                self.model_dimension = (
                    self.model.get_sentence_embedding_dimension()
                )
            except Exception as e:
                raise EmbeddingError(
                    f"Failed to load model {model_path}: {e}"
                )

        elif self.model_name == "grok":
            if self.grok is None:
                raise EmbeddingError(
                    "Grok client required for cloud embeddings"
                )
            self.model_dimension = 1536

        else:
            raise EmbeddingError(f"Unknown model: {self.model_name}")

    async def embed(self, text: str) -> Any:
        """
        Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector as numpy array
        """
        if not NUMPY_AVAILABLE:
            raise EmbeddingError(
                "NumPy required for embedding operations"
            )

        cache_key = hashlib.md5(text.encode()).hexdigest()
        if self.use_cache and cache_key in self.cache:
            vector, _ = self.cache[cache_key]
            self.cache[cache_key] = (vector, datetime.now())
            return vector

        if self.model_name == "grok" and self.grok:
            vector = await self._embed_with_grok(text)
        else:
            vector = await self._embed_local(text)

        if self.use_cache:
            self.cache[cache_key] = (vector, datetime.now())
            if len(self.cache) > self.cache_size:
                self._cleanup_cache()

        return vector

    async def _embed_local(self, text: str) -> Any:
        """Generate embedding using local model."""
        if self.model is None:
            raise EmbeddingError("Local model not initialized")

        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None,
            self.model.encode,
            text,
        )
        return vector

    async def _embed_with_grok(self, text: str) -> Any:
        """Generate embedding using Grok API (mock)."""
        if self.grok is None:
            raise EmbeddingError("Grok client not available")

        await asyncio.sleep(0.01)
        return np.random.randn(self.model_dimension or 1536).astype(
            np.float32
        )

    def _cleanup_cache(self) -> None:
        """Remove oldest cache entries."""
        sorted_items = sorted(
            self.cache.items(),
            key=lambda x: x[1][1],
            reverse=True,
        )
        self.cache = dict(sorted_items[: self.cache_size])

    async def similarity(self, vec1: Any, vec2: Any) -> float:
        """Compute cosine similarity between two vectors."""
        if not NUMPY_AVAILABLE:
            raise EmbeddingError(
                "NumPy required for similarity computation"
            )

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    async def store_embedding(
        self,
        item_id: str,
        text: str,
        vector: Optional[Any] = None,
    ) -> str:
        """Store embedding for a memory item (placeholder)."""
        if vector is None:
            vector = await self.embed(text)

        _ = EmbeddingVector(
            vector=vector,
            model=self.model_name,
            dimension=self.model_dimension or 0,
            created_at=datetime.now(),
        )
        return item_id

    async def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        type_filter: Optional[MemoryItemType] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Search for similar items by semantic similarity.

        Args:
            query: Search query
            limit: Maximum results
            threshold: Minimum similarity score
            type_filter: Filter by memory type

        Returns:
            List of (MemoryItem, similarity_score) tuples
        """
        mem_type = type_filter or MemoryItemType.TASK_RESULT
        query_vec = await self.embed(query)

        items = await self.memory.search_by_type(
            memory_type=mem_type,
            limit=1000,
        )

        results: List[Tuple[MemoryItem, float]] = []
        for item in items:
            item_text = self._get_item_text(item)
            if not item_text:
                continue

            item_vec = await self.embed(item_text)
            score = await self.similarity(query_vec, item_vec)

            if score >= threshold:
                results.append((item, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _get_item_text(self, item: MemoryItem) -> str:
        """Extract searchable text from memory item."""
        if isinstance(item.content, str):
            return item.content
        if isinstance(item.content, dict):
            if item.type == MemoryItemType.TASK_RESULT:
                parts = []
                if "goal" in item.content:
                    parts.append(str(item.content["goal"]))
                if "results" in item.content:
                    results = item.content["results"]
                    if isinstance(results, dict):
                        parts.extend(str(v) for v in results.values())
                return " ".join(parts)
            if item.type == MemoryItemType.EXTRACTED_DATA:
                if "data" in item.content:
                    data = item.content["data"]
                    if isinstance(data, (list, dict)):
                        return json.dumps(data)
                    return str(data)
            return json.dumps(item.content)
        return str(item.content)

    async def batch_embed(
        self,
        texts: List[str],
        batch_size: int = 32,
    ) -> List[Any]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if self.model_name == "grok":
            results: List[Any] = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                for text in batch:
                    vec = await self.embed(text)
                    results.append(vec)
            return results

        loop = asyncio.get_event_loop()

        def _encode() -> List[Any]:
            arr = self.model.encode(texts, batch_size=batch_size)
            return [arr[i] for i in range(len(texts))]

        return await loop.run_in_executor(None, _encode)

    async def find_similar_tasks(
        self,
        goal: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> List[Tuple[MemoryItem, float]]:
        """Find similar tasks by goal semantic similarity."""
        return await self.search_similar(
            query=goal,
            limit=limit,
            threshold=threshold,
            type_filter=MemoryItemType.TASK_RESULT,
        )

    async def find_similar_extractions(
        self,
        data_type: str,
        value: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> List[Tuple[MemoryItem, float]]:
        """Find similar extractions by content."""
        from .models import ExtractionResult

        extractions = await self.memory.get_extractions(
            data_type=data_type,
            limit=100,
        )

        items = [e.to_memory_item() for e in extractions]
        query_vec = await self.embed(value)

        results: List[Tuple[MemoryItem, float]] = []
        for item in items:
            item_text = self._get_item_text(item)
            if not item_text:
                continue

            item_vec = await self.embed(item_text)
            score = await self.similarity(query_vec, item_vec)

            if score >= threshold:
                results.append((item, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self.cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding engine statistics."""
        return {
            "model": self.model_name,
            "dimension": self.model_dimension,
            "cache_size": len(self.cache),
            "cache_enabled": self.use_cache,
            "backend": "local" if self.model else "grok",
        }


class HybridSearch:
    """
    Hybrid search combining keyword and semantic search.
    """

    def __init__(
        self,
        memory: SQLiteMemory,
        embeddings: EmbeddingEngine,
    ) -> None:
        self.memory = memory
        self.embeddings = embeddings

    async def search(
        self,
        query: str,
        limit: int = 10,
        semantic_weight: float = 0.5,
        type_filter: Optional[MemoryItemType] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Hybrid search combining keyword and semantic.

        Args:
            query: Search query
            limit: Maximum results
            semantic_weight: Weight for semantic search (0-1)
            type_filter: Filter by memory type

        Returns:
            List of (MemoryItem, combined_score)
        """
        keyword_results = await self.memory.search(
            query=query,
            type_filter=type_filter,
            limit=limit * 2,
        )

        try:
            semantic_results = await self.embeddings.search_similar(
                query=query,
                limit=limit * 2,
                threshold=0.5,
                type_filter=type_filter,
            )
        except EmbeddingError:
            semantic_results = []

        scores: Dict[str, Dict[str, Any]] = {}

        for i, item in enumerate(keyword_results):
            score = 1.0 - (i / (limit * 2)) * 0.5
            scores[item.id] = {
                "item": item,
                "keyword_score": score,
                "semantic_score": 0.0,
            }

        for item, semantic_score in semantic_results:
            if item.id in scores:
                scores[item.id]["semantic_score"] = semantic_score
            else:
                scores[item.id] = {
                    "item": item,
                    "keyword_score": 0.0,
                    "semantic_score": semantic_score,
                }

        combined: List[Tuple[MemoryItem, float]] = []
        for data in scores.values():
            combined_score = (
                (1 - semantic_weight) * data["keyword_score"]
                + semantic_weight * data["semantic_score"]
            )
            combined.append((data["item"], combined_score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:limit]
