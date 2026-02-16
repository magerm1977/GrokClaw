"""Test fixtures for Grok API responses."""

import json

VALID_PLAN_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "steps": [
                            {
                                "action": "navigate",
                                "target": "https://example.com",
                                "description": "Navigate to example.com",
                            },
                            {
                                "action": "extract",
                                "target": "title",
                                "description": "Extract page title",
                            },
                            {
                                "action": "done",
                                "description": "Task complete",
                            },
                        ],
                        "reasoning": "Simple two-step process",
                        "estimated_steps": 3,
                        "requires_browser": True,
                        "requires_memory": False,
                    }
                )
            }
        }
    ],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 30,
        "total_tokens": 55,
    },
}

COMPRESSION_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "• Key point 1\n• Key point 2\n• Key point 3"
            }
        }
    ],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    },
}

SIMPLE_CHAT_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "This is a test response."
            }
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    },
}

CONNECTION_TEST_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": "OK"
            }
        }
    ],
    "usage": {
        "prompt_tokens": 5,
        "completion_tokens": 1,
        "total_tokens": 6,
    },
}
