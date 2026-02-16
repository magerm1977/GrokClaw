"""Unified memory interface combining SQLite, embeddings, and compression."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.grok_client import GrokClient
from ..core.types import MemoryConfig
from ..utils.errors import MemorySystemError
from .compression import AutoCompressor, MemoryCompressor
from .embeddings import EmbeddingEngine, HybridSearch
from .models import (
    ExtractionResult,
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
    SessionData,
    TaskEpisode,
)
from .sqlite_backend import SQLiteMemory


class UnifiedMemory:
    """
    Unified memory interface combining SQLite, embeddings, and compression.

    Provides a single API for all memory operations with automatic
    embedding generation, semantic search, and background compression.
    """

    def __init__(
        self,
        config: MemoryConfig,
        grok_client: Optional[GrokClient] = None,
        db_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize unified memory interface.

        Args:
            config: Memory configuration
            grok_client: Optional Grok client for compression
            db_path: Optional custom database path
        """
        self.config = config
        self.grok = grok_client

        self.db_path = (
            db_path
            or config.path
            or Path.home() / ".grok-harness" / "memory" / "unified.db"
        )
        self.db_path = Path(self.db_path)

        self.sqlite = SQLiteMemory(
            db_path=self.db_path,
            auto_cleanup_days=config.ttl_days,
            max_items=config.max_items,
        )

        self.embeddings: Optional[EmbeddingEngine] = None
        self.hybrid_search: Optional[HybridSearch] = None
        if not config.low_spec_mode and config.enable_embeddings:
            try:
                self.embeddings = EmbeddingEngine(
                    memory=self.sqlite,
                    grok_client=grok_client,
                    model=config.embedding_model,
                    use_cache=True,
                )
                self.hybrid_search = HybridSearch(self.sqlite, self.embeddings)
            except Exception:
                pass

        self.compressor: Optional[MemoryCompressor] = None
        self.auto_compressor: Optional[AutoCompressor] = None
        if grok_client and config.enable_compression:
            self.compressor = MemoryCompressor(
                grok_client=grok_client,
                threshold=config.compression_threshold,
                auto_compress=config.auto_compress,
            )

            if config.auto_compress:
                self.auto_compressor = AutoCompressor(
                    compressor=self.compressor,
                    memory_backend=self.sqlite,
                    check_interval_minutes=config.compression_interval_minutes,
                    min_age_days=config.compression_min_age_days,
                    min_access_count=config.compression_min_access,
                )

        self._stats: Dict[str, int] = {
            "stores": 0,
            "retrievals": 0,
            "searches": 0,
            "compressions": 0,
        }

    async def start(self) -> None:
        """Start background services."""
        if self.auto_compressor:
            await self.auto_compressor.start()

    async def stop(self) -> None:
        """Stop background services."""
        if self.auto_compressor:
            await self.auto_compressor.stop()

    async def store(self, item: MemoryItem) -> str:
        """Store a memory item."""
        item_id = await self.sqlite.store(item)
        self._stats["stores"] += 1
        return item_id

    async def retrieve(self, key: str) -> Optional[MemoryItem]:
        """Retrieve by key."""
        self._stats["retrievals"] += 1
        return await self.sqlite.retrieve(key)

    async def retrieve_by_id(self, item_id: str) -> Optional[MemoryItem]:
        """Retrieve by ID."""
        self._stats["retrievals"] += 1
        return await self.sqlite.retrieve_by_id(item_id)

    async def delete(self, key: str) -> bool:
        """Delete by key."""
        return await self.sqlite.delete(key)

    async def delete_by_id(self, item_id: str) -> bool:
        """Delete by ID."""
        return await self.sqlite.delete_by_id(item_id)

    async def clear(
        self,
        memory_type: Optional[MemoryItemType] = None,
    ) -> None:
        """Clear all items of a type."""
        await self.sqlite.clear(memory_type)

    async def search(
        self,
        query: str,
        limit: int = 10,
        use_semantic: bool = True,
        type_filter: Optional[MemoryItemType] = None,
    ) -> List[MemoryItem]:
        """
        Search memory with optional semantic enhancement.

        Args:
            query: Search query
            limit: Maximum results
            use_semantic: Use semantic search if available
            type_filter: Filter by memory type

        Returns:
            List of matching memory items
        """
        self._stats["searches"] += 1

        if use_semantic and self.hybrid_search:
            results = await self.hybrid_search.search(
                query=query,
                limit=limit,
                semantic_weight=0.5,
                type_filter=type_filter,
            )
            return [item for item, _ in results]
        else:
            return await self.sqlite.search(
                query=query,
                type_filter=type_filter,
                limit=limit,
            )

    async def search_similar(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        type_filter: Optional[MemoryItemType] = None,
    ) -> List[MemoryItem]:
        """Semantic search only."""
        if not self.embeddings:
            raise MemorySystemError("Semantic search not available")

        results = await self.embeddings.search_similar(
            query=query,
            limit=limit,
            threshold=threshold,
            type_filter=type_filter,
        )
        return [item for item, _ in results]

    async def search_by_type(
        self,
        memory_type: MemoryItemType,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MemoryItem]:
        """Get items by type."""
        return await self.sqlite.search_by_type(
            memory_type,
            limit,
            offset,
        )

    async def store_task(self, episode: TaskEpisode) -> str:
        """Store a task episode."""
        item_id = await self.sqlite.store_task_episode(episode)

        if self.embeddings:
            asyncio.create_task(self._embed_task(episode))

        return item_id

    async def _embed_task(self, episode: TaskEpisode) -> None:
        """Background task embedding."""
        try:
            text = f"{episode.goal} {json.dumps(episode.results)}"
            await self.embeddings.embed(text)
        except Exception:
            pass

    async def get_recent_tasks(
        self,
        limit: int = 10,
        successful_only: bool = False,
    ) -> List[TaskEpisode]:
        """Get recent task episodes."""
        return await self.sqlite.get_task_episodes(limit, successful_only)

    async def find_similar_tasks(
        self,
        goal: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> List[TaskEpisode]:
        """Find similar tasks by goal."""
        if self.embeddings:
            results = await self.embeddings.find_similar_tasks(
                goal=goal,
                limit=limit,
                threshold=threshold,
            )
            episodes = []
            for item, score in results:
                episode = TaskEpisode.from_memory_item(item)
                episode.metadata.tags = list(episode.metadata.tags) + [
                    f"similarity:{score:.2f}"
                ]
                episodes.append(episode)
            return episodes
        else:
            return await self.sqlite.find_similar_tasks(goal, limit)

    async def store_extraction(self, extraction: ExtractionResult) -> str:
        """Store extraction result."""
        return await self.sqlite.store_extraction(extraction)

    async def get_extractions(
        self,
        source_url: Optional[str] = None,
        data_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[ExtractionResult]:
        """Get extraction results."""
        return await self.sqlite.get_extractions(
            source_url,
            data_type,
            limit,
        )

    async def find_similar_extractions(
        self,
        data_type: str,
        value: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> List[ExtractionResult]:
        """Find similar extractions by content."""
        if not self.embeddings:
            return []

        results = await self.embeddings.find_similar_extractions(
            data_type=data_type,
            value=value,
            limit=limit,
            threshold=threshold,
        )

        extractions = []
        for item, score in results:
            extraction = ExtractionResult.from_memory_item(item)
            extraction.metadata.tags = list(extraction.metadata.tags) + [
                f"similarity:{score:.2f}"
            ]
            extractions.append(extraction)
        return extractions

    async def store_session(self, session: SessionData) -> str:
        """Store session data."""
        return await self.sqlite.store_session(session)

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID."""
        return await self.sqlite.get_session(session_id)

    async def compress(
        self,
        items: List[MemoryItem],
        group_by_type: bool = True,
    ) -> List[MemoryItem]:
        """Manually compress items."""
        if not self.compressor:
            raise MemorySystemError("Compression not available")

        compressed = await self.compressor.compress_items(
            items,
            group_by_type=group_by_type,
        )

        self._stats["compressions"] += 1

        for item in compressed:
            await self.store(item)

        for item in items:
            await self.delete(item.key)

        return compressed

    async def decompress(
        self,
        compressed_item: MemoryItem,
    ) -> List[MemoryItem]:
        """Decompress a compressed item."""
        if not self.compressor:
            raise MemorySystemError("Compression not available")

        return await self.compressor.decompress(compressed_item)

    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        if not self.compressor:
            return {}
        return self.compressor.get_stats()

    async def get_stats(self) -> Dict[str, Any]:
        """Get unified memory statistics."""
        sqlite_stats = await self.sqlite.get_stats()
        embedding_stats = (
            self.embeddings.get_stats() if self.embeddings else {}
        )
        compression_stats = self.get_compression_stats()

        return {
            **sqlite_stats,
            "embeddings": embedding_stats,
            "compression": compression_stats,
            "operations": self._stats.copy(),
            "timestamp": datetime.now().isoformat(),
        }

    async def vacuum(self) -> None:
        """Optimize database."""
        await self.sqlite.vacuum()

    async def close(self) -> None:
        """Clean up resources."""
        await self.stop()

    async def __aenter__(self) -> "UnifiedMemory":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type,
        exc_val: BaseException,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()
