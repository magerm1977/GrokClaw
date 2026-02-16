"""Embedding test fixtures."""

import numpy as np

SAMPLE_EMBEDDINGS = {
    "price_query": np.random.randn(384),
    "email_query": np.random.randn(384),
    "phone_query": np.random.randn(384),
}

SAMPLE_TEXTS = {
    "price_1": "Find product prices on Amazon",
    "price_2": "Check cost of items in store",
    "email_1": "Extract email addresses from contact page",
    "email_2": "Find contact email on website",
    "phone_1": "Get phone numbers from directory",
    "phone_2": "Look up business phone numbers",
    "weather": "Check weather forecast for London",
    "news": "Read latest news headlines",
}

MOCK_SIMILARITIES = {
    ("price_1", "price_2"): 0.85,
    ("price_1", "email_1"): 0.25,
    ("email_1", "email_2"): 0.90,
    ("phone_1", "phone_2"): 0.88,
    ("price_1", "weather"): 0.15,
}

SAMPLE_MEMORY_ITEMS_WITH_TEXT = [
    {
        "id": "mem_price_1",
        "key": "price_task_1",
        "content": {
            "goal": "Find product prices on Amazon",
            "results": {"prices": ["$19.99", "$29.99"]},
        },
        "type": "task_result",
    },
    {
        "id": "mem_price_2",
        "key": "price_task_2",
        "content": {
            "goal": "Check cost of items in store",
            "results": {"prices": ["$9.99", "$14.99"]},
        },
        "type": "task_result",
    },
    {
        "id": "mem_email_1",
        "key": "email_task_1",
        "content": {
            "goal": "Extract email addresses from contact page",
            "results": {"emails": ["info@example.com"]},
        },
        "type": "task_result",
    },
]
