"""Memory system test fixtures."""

from datetime import datetime, timedelta

SAMPLE_MEMORY_ITEMS = [
    {
        "id": "task-001",
        "key": "task:example-title",
        "content": {
            "goal": "Get page title from example.com",
            "steps_taken": 2,
            "success": True,
            "duration_ms": 1234,
            "results": {"title": "Example Domain"},
            "action_history": [
                {"action": "navigate", "target": "https://example.com"},
                {"action": "extract", "target": "title"},
            ],
        },
        "type": "task_result",
        "metadata": {
            "created_at": (
                datetime.now() - timedelta(days=1)
            ).isoformat(),
            "tags": ["web", "title", "success"],
            "source": "test",
        },
    },
    {
        "id": "extract-001",
        "key": "extract:https://example.com:prices",
        "content": {
            "source_url": "https://example.com",
            "extracted_at": datetime.now().isoformat(),
            "data_type": "prices",
            "data": [
                {"product": "Item 1", "price": "$19.99"},
                {"product": "Item 2", "price": "$29.99"},
            ],
            "confidence": 0.95,
        },
        "type": "extracted_data",
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "tags": ["prices", "ecommerce"],
            "source": "agent",
        },
    },
    {
        "id": "session-001",
        "key": "session:test-session",
        "content": {
            "url": "https://example.com",
            "cookies": [{"name": "session", "value": "abc123"}],
            "local_storage": {"pref": "dark-mode"},
            "created_at": datetime.now().isoformat(),
        },
        "type": "session",
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "tags": ["chrome", "persistent"],
            "source": "browser",
        },
    },
]

SAMPLE_TASK_EPISODES = [
    {
        "task_id": "task-001",
        "goal": "Get page title",
        "steps_taken": 2,
        "success": True,
        "duration_ms": 1500,
        "results": {"title": "Example Domain"},
        "action_history": [
            {"action": "navigate", "target": "https://example.com"},
            {"action": "extract", "target": "title"},
        ],
    },
    {
        "task_id": "task-002",
        "goal": "Find email addresses",
        "steps_taken": 3,
        "success": False,
        "duration_ms": 2500,
        "results": {},
        "action_history": [
            {"action": "navigate", "target": "https://example.com"},
            {"action": "extract", "target": "emails"},
            {"action": "wait", "value": 2},
        ],
        "error": "No emails found",
    },
]

SAMPLE_EXTRACTIONS = [
    {
        "source_url": "https://example.com",
        "data_type": "prices",
        "data": [{"product": "Widget", "price": "$9.99"}],
        "confidence": 0.98,
    },
    {
        "source_url": "https://example.com/contact",
        "data_type": "emails",
        "data": ["info@example.com", "support@example.com"],
        "confidence": 0.95,
    },
]

SAMPLE_SESSIONS = [
    {
        "session_id": "sess-001",
        "url": "https://example.com",
        "cookies": [{"name": "auth", "value": "token123"}],
        "local_storage": {"theme": "dark"},
    },
]
