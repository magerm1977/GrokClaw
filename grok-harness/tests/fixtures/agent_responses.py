"""Mock Grok responses for browser agent testing."""

# Mock task plan responses
SIMPLE_TASK_PLAN = {
    "steps": [
        {
            "action": "navigate",
            "target": "https://example.com",
            "description": "Navigate to example.com",
        },
        {
            "action": "extract",
            "target": "title",
            "description": "Extract the page title",
        },
        {
            "action": "done",
            "description": "Task complete",
        },
    ],
    "reasoning": "Simple two-step process to get page title",
    "estimated_steps": 3,
    "requires_browser": True,
    "requires_memory": False,
}

PRICE_CHECK_PLAN = {
    "steps": [
        {
            "action": "navigate",
            "target": "https://example.com/products",
            "description": "Go to products page",
        },
        {
            "action": "wait",
            "value": 2,
            "description": "Wait for page to load",
        },
        {
            "action": "extract",
            "target": ["price", "title"],
            "description": "Extract product prices and titles",
        },
        {
            "action": "done",
            "description": "Task complete",
        },
    ],
    "reasoning": "Navigate to products page and extract pricing information",
    "estimated_steps": 4,
    "requires_browser": True,
    "requires_memory": True,
}

# Mock action decision responses
CLICK_ACTION = {
    "action": "click",
    "target": "#submit-button",
    "reasoning": "Click the submit button to complete the form",
    "confidence": 0.95,
}

TYPE_ACTION = {
    "action": "type",
    "target": "#search-input",
    "value": "weather in London",
    "reasoning": "Enter search query for weather",
    "confidence": 0.9,
}

EXTRACT_ACTION = {
    "action": "extract",
    "target": ["price", "title"],
    "reasoning": "Extract product information",
    "confidence": 0.85,
}

NAVIGATE_ACTION = {
    "action": "navigate",
    "target": "https://example.com/next-page",
    "reasoning": "Navigate to next page for more results",
    "confidence": 0.8,
}

DONE_ACTION = {
    "action": "done",
    "reasoning": "Task completed successfully",
    "confidence": 1.0,
}

WAIT_ACTION = {
    "action": "wait",
    "value": 2,
    "reasoning": "Wait for dynamic content to load",
    "confidence": 0.7,
}

SCROLL_ACTION = {
    "action": "scroll",
    "target": "down",
    "reasoning": "Scroll down to load more products",
    "confidence": 0.75,
}

# Mock page states
EXAMPLE_PAGE_STATE = {
    "url": "https://example.com",
    "title": "Example Domain",
    "text_preview": "This domain is for use in illustrative examples...",
    "text_length": 1250,
    "html_length": 3500,
    "screenshot": None,
    "cookies_count": 0,
    "step": 1,
}

PRODUCT_PAGE_STATE = {
    "url": "https://example.com/products",
    "title": "Products - Example Store",
    "text_preview": (
        "Product 1: $19.99, Product 2: $29.99, Product 3: $39.99"
    ),
    "text_length": 850,
    "html_length": 12500,
    "screenshot": "base64_encoded_screenshot_data",
    "cookies_count": 3,
    "step": 2,
}
