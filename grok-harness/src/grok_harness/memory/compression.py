"""Grok-powered memory compression."""

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..core.grok_client import GrokClient
from .models import MemoryItem, MemoryItemType, MemoryMetadata, TaskEpisode


class MemoryCompressor:
    """
    Grok-powered memory compression.

    Uses Grok to summarize and compress multiple memory items
    into concise insights, reducing storage while preserving
    important information.
    """

    DEFAULT_COMPRESSION_THRESHOLD = 50
    DEFAULT_MAX_POINTS = 10

    def __init__(
        self,
        grok_client: GrokClient,
        threshold: int = DEFAULT_COMPRESSION_THRESHOLD,
        auto_compress: bool = True,
    ) -> None:
        """
        Initialize memory compressor.

        Args:
            grok_client: Grok client for compression
            threshold: Number of items before triggering compression
            auto_compress: Automatically compress when threshold reached
        """
        self.grok = grok_client
        self.threshold = threshold
        self.auto_compress = auto_compress
        self.compression_stats: Dict[str, Any] = {
            "total_compressions": 0,
            "total_items_compressed": 0,
            "total_tokens_saved": 0,
            "last_compression": None,
        }

    async def should_compress(
        self,
        items: List[MemoryItem],
        force: bool = False,
    ) -> bool:
        """Determine if compression should run."""
        if force:
            return True

        if not self.auto_compress:
            return False

        return len(items) >= self.threshold

    async def compress_items(
        self,
        items: List[MemoryItem],
        max_points: int = DEFAULT_MAX_POINTS,
        group_by_type: bool = True,
    ) -> List[MemoryItem]:
        """
        Compress multiple memory items into summaries.

        Args:
            items: List of memory items to compress
            max_points: Maximum bullet points per summary
            group_by_type: Group items by type before compression

        Returns:
            List of compressed memory items
        """
        if not items:
            return []

        if group_by_type:
            grouped: Dict[MemoryItemType, List[MemoryItem]] = defaultdict(list)
            for item in items:
                grouped[item.type].append(item)

            compressed: List[MemoryItem] = []
            for item_type, group in grouped.items():
                group_compressed = await self._compress_group(
                    group,
                    item_type,
                    max_points,
                )
                compressed.extend(group_compressed)
            return compressed
        else:
            first_type = items[0].type if items else MemoryItemType.SYSTEM
            return await self._compress_group(items, first_type, max_points)

    async def _compress_group(
        self,
        items: List[MemoryItem],
        item_type: MemoryItemType,
        max_points: int,
    ) -> List[MemoryItem]:
        """Compress a group of same-type items."""
        if len(items) == 1:
            return items

        contents = []
        original_tokens = 0

        for item in items:
            content_str = self._item_to_string(item)
            contents.append(content_str)
            original_tokens += len(content_str) // 4

        try:
            summary = await self.grok.compress_memory(
                contents,
                max_points=max_points,
            )

            compressed_tokens = len(summary) // 4
            tokens_saved = original_tokens - compressed_tokens

            compressed_item = MemoryItem(
                id=self._generate_compression_id(items),
                key=f"compressed:{item_type.value}:{datetime.now().isoformat()}",
                content={
                    "summary": summary,
                    "source_count": len(items),
                    "source_ids": [item.id for item in items],
                    "source_types": [item.type.value for item in items],
                    "compressed_at": datetime.now().isoformat(),
                },
                type=MemoryItemType.COMPRESSED,
                metadata=MemoryMetadata(
                    tags=["compressed", item_type.value],
                    source="compressor",
                ),
            )

            self.compression_stats["total_compressions"] += 1
            self.compression_stats["total_items_compressed"] += len(items)
            self.compression_stats["total_tokens_saved"] += tokens_saved
            self.compression_stats["last_compression"] = datetime.now()

            return [compressed_item]

        except Exception:
            return items

    def _item_to_string(self, item: MemoryItem) -> str:
        """Convert memory item to string for compression."""
        parts = []

        if item.metadata.tags:
            parts.append(f"Tags: {', '.join(item.metadata.tags)}")

        if item.type == MemoryItemType.TASK_RESULT:
            if isinstance(item.content, dict):
                if "goal" in item.content:
                    parts.append(f"Goal: {item.content['goal']}")
                if "results" in item.content:
                    results = item.content["results"]
                    if isinstance(results, dict):
                        for k, v in results.items():
                            parts.append(f"{k}: {v}")
                    else:
                        parts.append(f"Results: {results}")

        elif item.type == MemoryItemType.EXTRACTED_DATA:
            if isinstance(item.content, dict):
                if "data_type" in item.content:
                    parts.append(f"Type: {item.content['data_type']}")
                if "data" in item.content:
                    data = item.content["data"]
                    if isinstance(data, list):
                        parts.extend(str(d) for d in data[:3])
                    else:
                        parts.append(f"Data: {data}")

        elif item.type == MemoryItemType.PATTERN:
            if isinstance(item.content, dict):
                for k, v in item.content.items():
                    parts.append(f"{k}: {v}")

        else:
            if isinstance(item.content, dict):
                parts.append(json.dumps(item.content))
            else:
                parts.append(str(item.content))

        return " | ".join(parts)

    def _generate_compression_id(self, items: List[MemoryItem]) -> str:
        """Generate a consistent ID for compressed items."""
        combined = "".join(sorted(item.id for item in items))
        return f"compressed_{hashlib.md5(combined.encode()).hexdigest()[:16]}"

    async def decompress(self, compressed_item: MemoryItem) -> List[MemoryItem]:
        """
        Decompress a compressed item to reference items.

        Note: Does not restore original content, only returns
        metadata about what was compressed.
        """
        if compressed_item.type != MemoryItemType.COMPRESSED:
            return [compressed_item]

        content = compressed_item.content
        if not isinstance(content, dict):
            return []

        source_ids = content.get("source_ids", [])
        source_types = content.get("source_types", [])

        return [
            MemoryItem(
                id=source_id,
                key=f"reference:{source_id}",
                content={
                    "note": "This item was compressed",
                    "compressed_in": compressed_item.id,
                    "original_type": source_type,
                },
                type=MemoryItemType.REFERENCE,
                metadata=MemoryMetadata(
                    tags=["compressed", "reference"],
                    source="decompressor",
                ),
            )
            for source_id, source_type in zip(source_ids, source_types)
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        return self.compression_stats.copy()


class AutoCompressor:
    """
    Automatic memory compression service.

    Runs in background to periodically compress old/unused memories.
    """

    def __init__(
        self,
        compressor: MemoryCompressor,
        memory_backend: Any,
        check_interval_minutes: int = 60,
        min_age_days: int = 7,
        min_access_count: int = 3,
    ) -> None:
        self.compressor = compressor
        self.memory = memory_backend
        self.check_interval = check_interval_minutes * 60
        self.min_age_days = min_age_days
        self.min_access_count = min_access_count
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start background compression task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop background compression."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main compression loop."""
        while self._running:
            try:
                await self._check_and_compress()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(60)

    async def _check_and_compress(self) -> None:
        """Check for items to compress and compress them."""
        from .models import MemoryItemType

        cutoff_date = datetime.now() - timedelta(days=self.min_age_days)

        all_items = await self.memory.search_by_type(
            MemoryItemType.TASK_RESULT,
            limit=1000,
        )

        old_items = [
            item
            for item in all_items
            if item.metadata.created_at < cutoff_date
            and item.metadata.access_count < self.min_access_count
        ]

        if old_items and await self.compressor.should_compress(old_items):
            compressed = await self.compressor.compress_items(old_items)

            for comp_item in compressed:
                await self.memory.store(comp_item)

            for item in old_items:
                await self.memory.delete(item.key)
