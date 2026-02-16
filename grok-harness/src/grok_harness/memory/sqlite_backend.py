"""SQLite-based persistent memory backend."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import (
    ExtractionResult,
    MemoryItem,
    MemoryItemType,
    MemoryMetadata,
    SessionData,
    TaskEpisode,
)


class SQLiteMemory:
    """
    SQLite-based persistent memory backend.

    Stores task results, extracted data, sessions, and learned patterns
    with automatic cleanup and indexing for fast retrieval.
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        db_path: Optional[Path] = None,
        auto_cleanup_days: int = 30,
        max_items: int = 10000,
    ) -> None:
        """
        Initialize SQLite memory backend.

        Args:
            db_path: Path to SQLite database file
            auto_cleanup_days: Delete items older than this (0 to disable)
            max_items: Maximum number of items to keep (oldest deleted first)
        """
        self.db_path = (
            db_path
            or Path.home() / ".grok-harness" / "memory" / "grok_memory.db"
        )
        self.db_path = Path(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.auto_cleanup_days = auto_cleanup_days
        self.max_items = max_items

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    key TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP,
                    tags TEXT,
                    source TEXT,
                    version TEXT
                )
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_key "
                "ON memory_items(key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_type "
                "ON memory_items(type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_created "
                "ON memory_items(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_accessed "
                "ON memory_items(last_accessed)"
            )

            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        content,
                        content='memory_items',
                        content_rowid='rowid'
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS memory_items_ai
                    AFTER INSERT ON memory_items BEGIN
                        INSERT INTO memory_fts(rowid, content)
                        VALUES (new.rowid, new.content);
                    END
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS memory_items_ad
                    AFTER DELETE ON memory_items BEGIN
                        INSERT INTO memory_fts(memory_fts, rowid, content)
                        VALUES('delete', old.rowid, old.content);
                    END
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS memory_items_au
                    AFTER UPDATE ON memory_items BEGIN
                        INSERT INTO memory_fts(memory_fts, rowid, content)
                        VALUES('delete', old.rowid, old.content);
                        INSERT INTO memory_fts(rowid, content)
                        VALUES (new.rowid, new.content);
                    END
                    """
                )
            except sqlite3.OperationalError:
                pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

            conn.execute(
                "INSERT OR REPLACE INTO memory_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )

            conn.commit()

    @contextmanager
    def _get_connection(self) -> Any:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _maybe_cleanup(self, conn: sqlite3.Connection) -> None:
        """Clean up old items if needed."""
        count_row = conn.execute(
            "SELECT COUNT(*) FROM memory_items"
        ).fetchone()
        count = count_row[0] if count_row else 0

        if count > self.max_items:
            to_delete = count - self.max_items
            conn.execute(
                """
                DELETE FROM memory_items
                WHERE rowid IN (
                    SELECT rowid FROM memory_items
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (to_delete,),
            )

        if self.auto_cleanup_days > 0:
            cutoff = (
                datetime.now()
                - timedelta(days=self.auto_cleanup_days)
            ).isoformat()
            conn.execute(
                "DELETE FROM memory_items WHERE created_at < ?",
                (cutoff,),
            )

    def _row_to_memory_item(self, row: sqlite3.Row) -> MemoryItem:
        """Convert database row to MemoryItem."""
        content = row["content"]
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

        tags: List[str] = []
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except (json.JSONDecodeError, TypeError):
                tags = (
                    [t.strip() for t in row["tags"].split(",")]
                    if row["tags"]
                    else []
                )

        metadata = MemoryMetadata(
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            access_count=row["access_count"] or 0,
            last_accessed=(
                datetime.fromisoformat(row["last_accessed"])
                if row["last_accessed"]
                else None
            ),
            tags=tags,
            source=row["source"],
            version=row["version"] or "1.0",
        )

        return MemoryItem(
            id=row["id"],
            key=row["key"],
            content=content,
            type=MemoryItemType(row["type"]),
            metadata=metadata,
        )

    async def store(self, item: MemoryItem) -> str:
        """
        Store a memory item.

        Args:
            item: MemoryItem to store

        Returns:
            ID of stored item
        """
        with self._get_connection() as conn:
            self._maybe_cleanup(conn)

            item.metadata.updated_at = datetime.now()

            content_str = (
                json.dumps(item.content)
                if not isinstance(item.content, str)
                else item.content
            )
            tags_json = json.dumps(item.metadata.tags)
            last_acc = (
                item.metadata.last_accessed.isoformat()
                if item.metadata.last_accessed
                else None
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO memory_items
                (id, key, content, type, created_at, updated_at,
                 access_count, last_accessed, tags, source, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.key,
                    content_str,
                    item.type.value,
                    item.metadata.created_at.isoformat(),
                    item.metadata.updated_at.isoformat(),
                    item.metadata.access_count,
                    last_acc,
                    tags_json,
                    item.metadata.source,
                    item.metadata.version,
                ),
            )

            conn.commit()
            return item.id

    async def retrieve(self, key: str) -> Optional[MemoryItem]:
        """
        Retrieve a memory item by key.

        Args:
            key: Unique key of the item

        Returns:
            MemoryItem if found, None otherwise
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE key = ?",
                (key,),
            ).fetchone()

            if not row:
                return None

            now = datetime.now().isoformat()
            conn.execute(
                """
                UPDATE memory_items
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE key = ?
                """,
                (now, key),
            )
            conn.commit()

            item = self._row_to_memory_item(row)
            item.metadata.access_count = (row["access_count"] or 0) + 1
            item.metadata.last_accessed = datetime.fromisoformat(now)
            return item

    async def retrieve_by_id(self, item_id: str) -> Optional[MemoryItem]:
        """Retrieve a memory item by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE id = ?",
                (item_id,),
            ).fetchone()

            if not row:
                return None

            now = datetime.now().isoformat()
            conn.execute(
                """
                UPDATE memory_items
                SET access_count = access_count + 1,
                    last_accessed = ?
                WHERE id = ?
                """,
                (now, item_id),
            )
            conn.commit()

            item = self._row_to_memory_item(row)
            item.metadata.access_count = (row["access_count"] or 0) + 1
            item.metadata.last_accessed = datetime.fromisoformat(now)
            return item

    async def search(
        self,
        query: str,
        type_filter: Optional[MemoryItemType] = None,
        limit: int = 10,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryItem]:
        """
        Search memory items by content.

        Args:
            query: Search query string
            type_filter: Filter by memory type
            limit: Maximum number of results
            tags: Filter by tags

        Returns:
            List of matching memory items
        """
        with self._get_connection() as conn:
            try:
                fts_query = f'"{query}"' if " " in query else query
                sql = """
                    SELECT mi.* FROM memory_items mi
                    JOIN memory_fts fts ON mi.rowid = fts.rowid
                    WHERE memory_fts MATCH ?
                """
                params: List[Any] = [fts_query]

                if type_filter:
                    sql += " AND mi.type = ?"
                    params.append(type_filter.value)

                if tags:
                    for tag in tags:
                        sql += " AND mi.tags LIKE ?"
                        params.append(f"%{tag}%")

                sql += " ORDER BY mi.created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                rows = []

            for row in rows:
                conn.execute(
                    """
                    UPDATE memory_items
                    SET access_count = access_count + 1,
                        last_accessed = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), row["id"]),
                )
            conn.commit()

            return [self._row_to_memory_item(row) for row in rows]

    async def search_by_type(
        self,
        memory_type: MemoryItemType,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MemoryItem]:
        """Retrieve items by type with pagination."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE type = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (memory_type.value, limit, offset),
            ).fetchall()

            return [self._row_to_memory_item(row) for row in rows]

    async def delete(self, key: str) -> bool:
        """Delete a memory item by key."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM memory_items WHERE key = ?",
                (key,),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def delete_by_id(self, item_id: str) -> bool:
        """Delete a memory item by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM memory_items WHERE id = ?",
                (item_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def clear(
        self,
        memory_type: Optional[MemoryItemType] = None,
    ) -> None:
        """Clear all memory items, optionally filtered by type."""
        with self._get_connection() as conn:
            if memory_type:
                conn.execute(
                    "DELETE FROM memory_items WHERE type = ?",
                    (memory_type.value,),
                )
            else:
                conn.execute("DELETE FROM memory_items")
            conn.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        with self._get_connection() as conn:
            total_row = conn.execute(
                "SELECT COUNT(*) FROM memory_items"
            ).fetchone()
            total = total_row[0] if total_row else 0

            by_type: Dict[str, int] = {}
            for type_enum in MemoryItemType:
                count_row = conn.execute(
                    "SELECT COUNT(*) FROM memory_items WHERE type = ?",
                    (type_enum.value,),
                ).fetchone()
                count = count_row[0] if count_row else 0
                if count > 0:
                    by_type[type_enum.value] = count

            oldest_row = conn.execute(
                "SELECT MIN(created_at) FROM memory_items"
            ).fetchone()
            newest_row = conn.execute(
                "SELECT MAX(created_at) FROM memory_items"
            ).fetchone()
            accesses_row = conn.execute(
                "SELECT SUM(access_count) FROM memory_items"
            ).fetchone()

            return {
                "total_items": total,
                "items_by_type": by_type,
                "oldest_item": oldest_row[0] if oldest_row else None,
                "newest_item": newest_row[0] if newest_row else None,
                "total_accesses": accesses_row[0] or 0,
                "db_size_bytes": (
                    self.db_path.stat().st_size
                    if self.db_path.exists()
                    else 0
                ),
                "auto_cleanup_days": self.auto_cleanup_days,
                "max_items": self.max_items,
            }

    async def vacuum(self) -> None:
        """Optimize database (VACUUM)."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
            conn.commit()

    async def store_task_episode(self, episode: TaskEpisode) -> str:
        """Store a task episode."""
        return await self.store(episode.to_memory_item())

    async def get_task_episodes(
        self,
        limit: int = 10,
        successful_only: bool = False,
    ) -> List[TaskEpisode]:
        """Get recent task episodes."""
        with self._get_connection() as conn:
            query = "SELECT * FROM memory_items WHERE type = ?"
            params: List[Any] = [MemoryItemType.TASK_RESULT.value]

            if successful_only:
                query += " AND json_extract(content, '$.success') = 1"

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            episodes = []
            for row in rows:
                item = self._row_to_memory_item(row)
                episodes.append(TaskEpisode.from_memory_item(item))

            return episodes

    async def store_extraction(self, extraction: ExtractionResult) -> str:
        """Store an extraction result."""
        return await self.store(extraction.to_memory_item())

    async def get_extractions(
        self,
        source_url: Optional[str] = None,
        data_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[ExtractionResult]:
        """Get extraction results."""
        with self._get_connection() as conn:
            query = "SELECT * FROM memory_items WHERE type = ?"
            params: List[Any] = [MemoryItemType.EXTRACTED_DATA.value]

            if source_url:
                query += " AND json_extract(content, '$.source_url') = ?"
                params.append(source_url)

            if data_type:
                query += " AND json_extract(content, '$.data_type') = ?"
                params.append(data_type)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            extractions = []
            for row in rows:
                item = self._row_to_memory_item(row)
                extractions.append(ExtractionResult.from_memory_item(item))

            return extractions

    async def store_session(self, session: SessionData) -> str:
        """Store session data."""
        return await self.store(session.to_memory_item())

    async def get_session(
        self, session_id: str
    ) -> Optional[SessionData]:
        """Get session data by ID."""
        item = await self.retrieve_by_id(session_id)
        if item and item.type == MemoryItemType.SESSION:
            return SessionData.from_memory_item(item)
        return None

    async def find_similar_tasks(
        self,
        goal: str,
        limit: int = 5,
    ) -> List[TaskEpisode]:
        """Find similar tasks by goal text (keyword-based)."""
        keywords = [w for w in goal.lower().split() if len(w) > 3][:5]

        if not keywords:
            return []

        with self._get_connection() as conn:
            conditions = [
                "content LIKE ?" for _ in keywords
            ]
            params: List[Any] = [
                MemoryItemType.TASK_RESULT.value,
                *[f"%{kw}%" for kw in keywords],
                limit,
            ]

            query = f"""
                SELECT * FROM memory_items
                WHERE type = ? AND ({" OR ".join(conditions)})
                ORDER BY created_at DESC
                LIMIT ?
            """

            rows = conn.execute(query, params).fetchall()

            episodes = []
            for row in rows:
                item = self._row_to_memory_item(row)
                episodes.append(TaskEpisode.from_memory_item(item))

            return episodes
