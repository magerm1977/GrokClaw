"""Data models for the memory system."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryItemType(Enum):
    """Types of memory items."""

    TASK_RESULT = "task_result"
    EXTRACTED_DATA = "extracted_data"
    SESSION = "session"
    PATTERN = "pattern"
    PREFERENCE = "preference"
    ERROR = "error"
    SYSTEM = "system"
    COMPRESSED = "compressed"
    REFERENCE = "reference"
    STEP_RESULT = "step_result"


@dataclass
class MemoryMetadata:
    """Metadata for memory items."""

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": (
                self.last_accessed.isoformat()
                if self.last_accessed
                else None
            ),
            "tags": self.tags,
            "source": self.source,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryMetadata":
        """Create from dictionary."""
        return cls(
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else datetime.now()
            ),
            access_count=data.get("access_count", 0),
            last_accessed=(
                datetime.fromisoformat(data["last_accessed"])
                if data.get("last_accessed")
                else None
            ),
            tags=data.get("tags", []),
            source=data.get("source"),
            version=data.get("version", "1.0"),
        )


@dataclass
class MemoryItem:
    """Base memory item."""

    id: str
    key: str
    content: Any
    type: MemoryItemType
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        content_val = self.content
        if not isinstance(content_val, str):
            content_val = json.dumps(content_val)

        return {
            "id": self.id,
            "key": self.key,
            "content": content_val,
            "type": self.type.value,
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Create from dictionary."""
        content = data["content"]
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass

        return cls(
            id=data["id"],
            key=data["key"],
            content=content,
            type=MemoryItemType(data["type"]),
            metadata=MemoryMetadata.from_dict(
                data.get("metadata", {})
            ),
        )


@dataclass
class TaskEpisode:
    """Record of a task execution episode."""

    task_id: str
    goal: str
    steps_taken: int
    success: bool
    duration_ms: float
    results: Dict[str, Any]
    action_history: List[Dict[str, Any]]
    error: Optional[str] = None
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def to_memory_item(self) -> MemoryItem:
        """Convert to memory item for storage."""
        return MemoryItem(
            id=self.task_id,
            key=f"task:{self.task_id}",
            content={
                "goal": self.goal,
                "steps_taken": self.steps_taken,
                "success": self.success,
                "duration_ms": self.duration_ms,
                "results": self.results,
                "action_history": self.action_history,
                "error": self.error,
            },
            type=MemoryItemType.TASK_RESULT,
            metadata=self.metadata,
        )

    @classmethod
    def from_memory_item(cls, item: MemoryItem) -> "TaskEpisode":
        """Create from memory item."""
        content = item.content
        if isinstance(content, str):
            content = json.loads(content) if content else {}
        return cls(
            task_id=item.id,
            goal=content.get("goal", ""),
            steps_taken=content.get("steps_taken", 0),
            success=content.get("success", False),
            duration_ms=content.get("duration_ms", 0),
            results=content.get("results", {}),
            action_history=content.get("action_history", []),
            error=content.get("error"),
            metadata=item.metadata,
        )


@dataclass
class ExtractionResult:
    """Result of a data extraction operation."""

    source_url: str
    extracted_at: datetime
    data_type: str
    data: Any
    confidence: float = 1.0
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def to_memory_item(self) -> MemoryItem:
        """Convert to memory item for storage."""
        content_hash = hashlib.md5(
            f"{self.source_url}:{self.data_type}:{str(self.data)}".encode()
        ).hexdigest()[:16]

        return MemoryItem(
            id=content_hash,
            key=f"extract:{self.source_url}:{self.data_type}",
            content={
                "source_url": self.source_url,
                "extracted_at": self.extracted_at.isoformat(),
                "data_type": self.data_type,
                "data": self.data,
                "confidence": self.confidence,
            },
            type=MemoryItemType.EXTRACTED_DATA,
            metadata=self.metadata,
        )

    @classmethod
    def from_memory_item(cls, item: MemoryItem) -> "ExtractionResult":
        """Create from memory item."""
        content = item.content
        if isinstance(content, str):
            content = json.loads(content) if content else {}

        return cls(
            source_url=content.get("source_url", ""),
            extracted_at=datetime.fromisoformat(
                content.get(
                    "extracted_at",
                    datetime.now().isoformat(),
                )
            ),
            data_type=content.get("data_type", ""),
            data=content.get("data", {}),
            confidence=content.get("confidence", 1.0),
            metadata=item.metadata,
        )


@dataclass
class SessionData:
    """Browser session data for persistence."""

    session_id: str
    url: Optional[str]
    cookies: List[Dict[str, Any]]
    local_storage: Dict[str, str]
    created_at: datetime
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def to_memory_item(self) -> MemoryItem:
        """Convert to memory item for storage."""
        return MemoryItem(
            id=self.session_id,
            key=f"session:{self.session_id}",
            content={
                "url": self.url,
                "cookies": self.cookies,
                "local_storage": self.local_storage,
                "created_at": self.created_at.isoformat(),
            },
            type=MemoryItemType.SESSION,
            metadata=self.metadata,
        )

    @classmethod
    def from_memory_item(cls, item: MemoryItem) -> "SessionData":
        """Create from memory item."""
        content = item.content
        if isinstance(content, str):
            content = json.loads(content) if content else {}

        return cls(
            session_id=item.id,
            url=content.get("url"),
            cookies=content.get("cookies", []),
            local_storage=content.get("local_storage", {}),
            created_at=datetime.fromisoformat(
                content.get(
                    "created_at",
                    datetime.now().isoformat(),
                )
            ),
            metadata=item.metadata,
        )
