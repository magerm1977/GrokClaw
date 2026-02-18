"""Grok-powered autonomous browser agent."""

import asyncio
import base64
import hashlib
import uuid
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from ..core.grok_client import GrokClient
from ..core.types import (
    ActionResult,
    BrowserConfig,
    SystemInfo,
    TaskPlan,
    TaskResult,
    TaskStep,
)
from ..utils.errors import BrowserError, GrokAPIError
from .controller import BrowserController
from .fingerprint import BrowserFingerprint
from .stealth import StealthEngine


class GrokBrowserAgent:
    """
    Grok-powered autonomous browser agent.

    Uses Grok's reasoning to understand web pages and decide next actions
    in real-time, with safety checks and learning from past experiences.
    """

    DEFAULT_MAX_STEPS = 30
    AUTO_CONFIDENCE_THRESHOLD = 0.8

    def __init__(
        self,
        grok_client: GrokClient,
        config: BrowserConfig,
        system_info: SystemInfo,
        workspace_dir: Optional[Path] = None,
    ) -> None:
        self.grok = grok_client
        self.config = config
        self.system_info = system_info
        self.workspace_dir = (
            workspace_dir or Path.home() / ".grok-harness" / "workspace"
        )
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.browser: Optional[BrowserController] = None
        self.stealth: Optional[StealthEngine] = None
        self.fingerprint_manager = BrowserFingerprint()

        self.current_task: Optional[str] = None
        self.task_history: List[TaskResult] = []
        self.session_id = hashlib.md5(
            str(datetime.now().timestamp()).encode()
        ).hexdigest()[:8]
        self.step_count = 0
        self._is_running = False

        self.domain_patterns: Dict[str, Dict[str, Any]] = {}
        self._scheduler: Optional[Any] = None
        self._memory: Optional[Any] = None

    def set_orchestrator_deps(
        self,
        scheduler: Optional[Any] = None,
        memory: Optional[Any] = None,
    ) -> None:
        """Set scheduler/memory for orchestrator integration."""
        self._scheduler = scheduler
        self._memory = memory

    async def run_step(
        self,
        step: Union[Dict[str, Any], TaskStep],
    ) -> Dict[str, Any]:
        """
        Execute a single step. Uses scheduler resource lock when available.

        Args:
            step: TaskStep or dict with action, target, value

        Returns:
            Dict with success, data, error, duration_ms
        """
        from ..scheduler.models import Job

        if isinstance(step, TaskStep):
            action = {
                "action": step.action,
                "target": step.target,
                "value": step.value,
                "description": step.description,
            }
        else:
            action = step

        job_id = f"browser-step-{uuid.uuid4().hex[:8]}"
        job = Job(
            id=job_id,
            name="browser-step",
            resources=["browser"],
        )

        if self._scheduler and hasattr(
            self._scheduler,
            "conflict_scheduler",
        ):
            detector = self._scheduler.conflict_scheduler.conflict_detector
            acquired = await detector.acquire_resources(job)
            if not acquired:
                return {
                    "success": False,
                    "data": None,
                    "error": "Could not acquire browser resource",
                    "duration_ms": 0,
                }

        try:
            result = await self._execute_action(action)

            if self._memory and result.get("success") and result.get("data"):
                try:
                    screenshot = None
                    if isinstance(result.get("data"), dict):
                        screenshot = result["data"].get("screenshot")
                    if screenshot or result.get("data"):
                        from ..memory.models import (
                            MemoryItem,
                            MemoryMetadata,
                        )

                        from ..memory.models import MemoryItemType

                        sid = hashlib.md5(
                            str(datetime.now().timestamp()).encode()
                        ).hexdigest()[:8]
                        item = MemoryItem(
                            id=sid,
                            key=f"session:{self.session_id}:step",
                            content={
                                "action": action.get("action"),
                                "screenshot_preview": (
                                    screenshot[:100] if screenshot else None
                                ),
                                "timestamp": datetime.now().isoformat(),
                            },
                            type=MemoryItemType.SESSION,
                            metadata=MemoryMetadata(),
                        )
                        await self._memory.store(item)
                except Exception:
                    pass

            return {
                "success": result.get("success", False),
                "data": result.get("data"),
                "error": result.get("error"),
                "duration_ms": result.get("duration_ms", 0),
            }
        finally:
            if self._scheduler and hasattr(
                self._scheduler,
                "conflict_scheduler",
            ):
                detector = self._scheduler.conflict_scheduler.conflict_detector
                detector.release_all_resources(job_id)

    async def initialize(self) -> None:
        """Initialize browser and stealth."""
        if self.config.stealth_mode:
            self.stealth = StealthEngine(
                os_type=self.system_info.os.value,
                browser_type="chrome",
            )

        self.browser = BrowserController(
            config=self.config,
            system_info=self.system_info,
        )

        if self.stealth:
            self.browser.stealth = self.stealth
            self.browser.fingerprint_manager = self.fingerprint_manager

        await self.browser.initialize()

    async def run_task(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        interactive: bool = False,
    ) -> TaskResult:
        """
        Run an autonomous browsing task.

        Args:
            goal: What the user wants to accomplish
            context: Additional context (previous results, user preferences)
            max_steps: Maximum number of actions to take
            interactive: If True, ask for approval before each action

        Returns:
            TaskResult with results and action history
        """
        try:
            if not self.browser:
                await self.initialize()
        except BrowserError as e:
            if "Playwright" in str(e):
                return TaskResult(
                    task_id=self.session_id,
                    success=False,
                    steps_taken=0,
                    results={
                        "error": (
                            "Browser automation requires Playwright. "
                            "Run: playwright install chromium"
                        ),
                        "fix": "playwright install chromium",
                    },
                    action_history=[],
                    duration_ms=0,
                )
            raise

        self.current_task = goal
        self.step_count = 0
        self._is_running = True

        start_time = datetime.now()
        action_history: List[ActionResult] = []
        final_results: Dict[str, Any] = {}

        try:
            plan = await self.grok.plan_task(goal, context)

            while self.step_count < max_steps and self._is_running:
                page_state = await self._get_page_state()

                action = await self._decide_next_action(
                    goal=goal,
                    page_state=page_state,
                    step=self.step_count,
                    plan=plan if self.step_count == 0 else None,
                )

                if action.get("action") == "done":
                    final_results = await self._extract_results(goal)
                    break

                if action.get("action") == "fail":
                    raise BrowserError(
                        f"Task failed: {action.get('reason', 'Unknown reason')}"
                    )

                if interactive and not await self._get_approval(action):
                    action = {"action": "fail", "reason": "User rejected action"}
                    continue

                result = await self._execute_action(action)

                result_data = result.get("data")
                screenshot = None
                if isinstance(result_data, dict):
                    screenshot = result_data.get("screenshot")
                action_history.append(
                    ActionResult(
                        success=result.get("success", False),
                        action=action.get("action", "unknown"),
                        data=result.get("data"),
                        error=result.get("error"),
                        duration_ms=result.get("duration_ms", 0),
                        screenshot=screenshot,
                    )
                )

                self.step_count += 1

                await self._learn_from_step(goal, action, result)

            if self.step_count >= max_steps:
                final_results = await self._extract_results(goal)

        except Exception as e:
            if self.browser and self.browser.current_page:
                try:
                    screenshot = await self.browser.screenshot_base64()
                except Exception:
                    screenshot = None
                action_history.append(
                    ActionResult(
                        success=False,
                        action="error",
                        error=str(e),
                        screenshot=screenshot,
                    )
                )
            raise

        finally:
            self._is_running = False

        duration_ms = (
            datetime.now() - start_time
        ).total_seconds() * 1000

        task_result = TaskResult(
            task_id=self.session_id,
            success=True,
            steps_taken=self.step_count,
            results=final_results,
            action_history=action_history,
            duration_ms=duration_ms,
        )

        self.task_history.append(task_result)

        return task_result

    async def _get_page_state(self) -> Dict[str, Any]:
        """Get current page state for Grok."""
        if not self.browser or not self.browser.current_page:
            raise BrowserError("Browser not initialized")

        page_text = await self.browser.get_page_text()
        page_text_preview = page_text[:3000] + (
            "..." if len(page_text) > 3000 else ""
        )

        page_html = await self.browser.get_page_html()

        screenshot = None
        if self.config.screenshot_on_error or self.step_count % 5 == 0:
            screenshot = await self.browser.screenshot_base64(full_page=False)

        url = await self.browser.get_current_url()
        title = await self.browser.get_page_title()
        cookies = await self.browser.get_cookies()

        return {
            "url": url,
            "title": title,
            "text_preview": page_text_preview,
            "text_length": len(page_text),
            "html_length": len(page_html),
            "screenshot": screenshot,
            "cookies_count": len(cookies),
            "step": self.step_count,
            "timestamp": datetime.now().isoformat(),
        }

    async def _decide_next_action(
        self,
        goal: str,
        page_state: Dict[str, Any],
        step: int,
        plan: Optional[TaskPlan] = None,
    ) -> Dict[str, Any]:
        """Use Grok to decide the next action."""
        recent_actions = (
            self.browser.get_action_history()[-5:]
            if self.browser
            else []
        )

        domain = urlparse(page_state["url"]).netloc
        domain_pattern = self.domain_patterns.get(domain, {})

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": """You are Grok controlling a browser. Analyze the current page state and goal,
then decide the next action. Be concise and precise.

Return JSON with:
- action: one of [click, type, select, scroll, wait, extract, navigate, done, fail]
- target: CSS selector or description of what to interact with
- value: text to type or option to select (if applicable)
- reasoning: brief explanation of why this action
- confidence: 0.0 to 1.0 how confident you are

Examples:
{"action": "click", "target": "#submit", "reasoning": "Submit the form", "confidence": 0.95}
{"action": "type", "target": "#search", "value": "weather", "reasoning": "Enter search query", "confidence": 0.9}
{"action": "extract", "target": ["price", "title"], "reasoning": "Extract product info", "confidence": 0.85}
""",
            }
        ]

        plan_steps = (
            [
                {
                    "action": s.action,
                    "target": s.target,
                    "value": s.value,
                    "description": s.description,
                }
                for s in plan.steps
            ]
            if plan
            else []
        )

        user_content = f"""
Goal: {goal}
Current URL: {page_state['url']}
Page title: {page_state['title']}

Page text preview:
{page_state['text_preview']}

Recent actions:
{json.dumps(recent_actions, indent=2)}
"""
        if plan and step == 0:
            user_content += f"\n\nInitial plan:\n{json.dumps(plan_steps, indent=2)}"
        if domain_pattern:
            user_content += (
                f"\n\nLearned patterns for {domain}: "
                f"{json.dumps(domain_pattern, indent=2)}"
            )

        if page_state.get("screenshot"):
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:image/png;base64,"
                                    f"{page_state['screenshot']}"
                                )
                            },
                        },
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": user_content})

        try:
            response = await self.grok.chat_completion(
                messages, temperature=0.2
            )
            content = response["choices"][0]["message"]["content"]

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            action = json.loads(content.strip())

            if "action" not in action:
                raise GrokAPIError("No action in response")

            return action

        except Exception as e:
            return {
                "action": "wait",
                "value": 2,
                "reasoning": f"Failed to parse Grok response: {str(e)}",
                "confidence": 0.1,
            }

    async def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action with timing."""
        if not self.browser:
            raise BrowserError("Browser not initialized")

        action_type = action.get("action")
        target = action.get("target")
        value = action.get("value")

        start_time = datetime.now()
        error = None
        result_data = None

        try:
            if action_type == "navigate":
                await self.browser.navigate(target)
            elif action_type == "click":
                await self.browser.click(target)
            elif action_type == "type":
                await self.browser.type(target, value or "")
            elif action_type == "select":
                selected = await self.browser.select_option(target, value)
                result_data = {"selected": selected}
            elif action_type == "scroll":
                await self.browser.scroll(target or "down")
            elif action_type == "wait":
                seconds = float(value or 2)
                await self.browser.wait(seconds)
            elif action_type == "extract":
                if isinstance(target, list):
                    result_data = {}
                    for field in target:
                        result_data[field] = await self._extract_field(
                            str(field)
                        )
                else:
                    result_data = await self._extract_field(
                        str(target) if target else "text"
                    )
            else:
                raise BrowserError(f"Unknown action: {action_type}")

            success = True

        except Exception as e:
            success = False
            error = str(e)
            if self.config.screenshot_on_error:
                try:
                    result_data = {
                        "screenshot": await self.browser.screenshot_base64()
                    }
                except Exception:
                    result_data = {}

        duration_ms = (
            datetime.now() - start_time
        ).total_seconds() * 1000

        return {
            "success": success,
            "data": result_data,
            "error": error,
            "duration_ms": duration_ms,
        }

    async def _extract_field(self, field: str) -> Any:
        """Extract a specific field from the current page."""
        if not self.browser or not self.browser.current_page:
            return None

        field_lower = field.lower()

        if field_lower in ("price", "prices"):
            return await self._extract_prices()
        elif field_lower in ("email", "emails"):
            return await self._extract_emails()
        elif field_lower in ("phone", "phones"):
            return await self._extract_phones()
        elif field_lower in ("link", "links"):
            return await self._extract_links()
        elif field_lower in ("image", "images"):
            return await self._extract_images()
        elif field_lower == "title":
            return await self.browser.get_page_title()
        elif field_lower == "url":
            return await self.browser.get_current_url()
        elif field_lower == "text":
            return await self.browser.get_page_text()
        else:
            return await self._extract_by_heuristic(field)

    async def _extract_prices(self) -> List[str]:
        """Extract prices from page."""
        if not self.browser or not self.browser.current_page:
            return []

        selectors = [
            ".price",
            "[class*='price']",
            "[itemprop='price']",
            ".product-price",
            "#price",
            "[data-testid='price']",
            ".sale-price",
            ".offer-price",
        ]

        prices: List[str] = []
        for selector in selectors:
            try:
                elements = await self.browser.current_page.query_selector_all(
                    selector
                )
                for elem in elements:
                    text = await elem.text_content()
                    if text and any(
                        c in text for c in ["$", "€", "£", "¥"]
                    ):
                        prices.append(text.strip())
            except Exception:
                pass

        return prices[:10]

    async def _extract_emails(self) -> List[str]:
        """Extract email addresses from page."""
        if not self.browser or not self.browser.current_page:
            return []

        text = await self.browser.get_page_text()
        emails = re.findall(
            r"[\w.-]+@[\w.-]+\.\w+",
            text,
        )
        return list(set(emails))[:10]

    async def _extract_phones(self) -> List[str]:
        """Extract phone numbers from page."""
        if not self.browser or not self.browser.current_page:
            return []

        text = await self.browser.get_page_text()
        phones = re.findall(
            r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
            text,
        )
        return list(set(phones))[:10]

    async def _extract_links(self) -> List[Dict[str, str]]:
        """Extract all links from page."""
        if not self.browser or not self.browser.current_page:
            return []

        links: List[Dict[str, str]] = []
        try:
            elements = await self.browser.current_page.query_selector_all(
                "a[href]"
            )
            for elem in elements:
                href = await elem.get_attribute("href")
                text = await elem.text_content()
                if (
                    href
                    and not href.startswith("#")
                    and not href.startswith("javascript:")
                ):
                    links.append(
                        {
                            "url": href,
                            "text": (text or "").strip(),
                        }
                    )
        except Exception:
            pass

        return links[:20]

    async def _extract_images(self) -> List[Dict[str, str]]:
        """Extract image information."""
        if not self.browser or not self.browser.current_page:
            return []

        images: List[Dict[str, str]] = []
        try:
            elements = await self.browser.current_page.query_selector_all(
                "img[src]"
            )
            for elem in elements:
                src = await elem.get_attribute("src")
                alt = await elem.get_attribute("alt")
                if src:
                    images.append(
                        {
                            "src": src,
                            "alt": alt or "",
                        }
                    )
        except Exception:
            pass

        return images[:10]

    async def _extract_by_heuristic(self, field: str) -> Optional[str]:
        """Extract field by heuristic (look for labels with matching text)."""
        if not self.browser or not self.browser.current_page:
            return None

        try:
            element = await self.browser.current_page.query_selector(
                f'text="{field}"'
            )
            if element:
                value = await element.evaluate(
                    """
                    el => {
                        const next = el.nextElementSibling;
                        if (next) return next.textContent;
                        const parent = el.parentElement;
                        if (parent && parent.nextElementSibling) {
                            return parent.nextElementSibling.textContent;
                        }
                        return null;
                    }
                """
                )
                return value
        except Exception:
            pass

        return None

    async def _extract_results(self, goal: str) -> Dict[str, Any]:
        """Extract final results based on goal."""
        if not self.browser:
            return {}

        results: Dict[str, Any] = {}
        goal_lower = goal.lower()

        if "price" in goal_lower or "cost" in goal_lower:
            results["prices"] = await self._extract_prices()
        if "email" in goal_lower:
            results["emails"] = await self._extract_emails()
        if "phone" in goal_lower:
            results["phones"] = await self._extract_phones()
        if "link" in goal_lower or "url" in goal_lower:
            results["links"] = await self._extract_links()
        if "image" in goal_lower or "picture" in goal_lower:
            results["images"] = await self._extract_images()
        if "title" in goal_lower:
            results["title"] = await self.browser.get_page_title()

        results["url"] = await self.browser.get_current_url()

        return results

    async def _get_approval(self, action: Dict[str, Any]) -> bool:
        """Get user approval for an action."""
        print("\n🔍 Proposed action:")
        print(f"   Action: {action.get('action')}")
        print(f"   Target: {action.get('target', 'N/A')}")
        print(f"   Value: {action.get('value', 'N/A')}")
        print(f"   Reasoning: {action.get('reasoning', 'N/A')}")
        print(f"   Confidence: {action.get('confidence', 0)}")

        response = input("Approve? (y/N): ").lower()
        return response == "y"

    async def _learn_from_step(
        self,
        goal: str,
        action: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Learn from each step to improve future decisions."""
        if not result.get("success"):
            return

        if self.browser and self.browser.current_page:
            url = await self.browser.get_current_url()
            domain = urlparse(url).netloc

            if domain not in self.domain_patterns:
                self.domain_patterns[domain] = {"actions": []}

            self.domain_patterns[domain]["actions"].append(
                {
                    "action": action.get("action"),
                    "target": action.get("target"),
                    "value": action.get("value"),
                    "goal_keywords": goal.lower().split(),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if len(self.domain_patterns[domain]["actions"]) > 50:
                self.domain_patterns[domain]["actions"] = (
                    self.domain_patterns[domain]["actions"][-50:]
                )

    async def resume_task(self, task_result: TaskResult) -> TaskResult:
        """Resume a previous task from where it left off."""
        if not task_result.action_history:
            raise BrowserError("No action history to resume from")

        last_successful = -1
        for i, action in enumerate(task_result.action_history):
            if action.success:
                last_successful = i

        if last_successful < 0:
            raise BrowserError("No successful actions to resume from")

        for i in range(last_successful + 1):
            ar = task_result.action_history[i]
            await self._execute_action({"action": ar.action})

        return await self.run_task(
            goal=self.current_task or "Resume task",
            context={"previous_result": task_result},
        )

    async def save_state(self, path: Optional[Path] = None) -> Path:
        """Save agent state (session, learned patterns)."""
        if path is None:
            path = self.workspace_dir / f"agent_state_{self.session_id}.json"

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "domain_patterns": self.domain_patterns,
            "task_history": [
                {
                    "task_id": t.task_id,
                    "success": t.success,
                    "steps_taken": t.steps_taken,
                    "duration_ms": t.duration_ms,
                }
                for t in self.task_history[-10:]
            ],
        }

        with open(path, "w") as f:
            json.dump(state, f, indent=2)

        return path

    async def load_state(self, path: Path) -> None:
        """Load agent state."""
        path = Path(path)
        if not path.exists():
            raise BrowserError(f"State file not found: {path}")

        with open(path, "r") as f:
            state = json.load(f)

        self.session_id = state.get("session_id", self.session_id)
        self.domain_patterns = state.get("domain_patterns", {})

    async def close(self) -> None:
        """Clean up resources."""
        self._is_running = False
        if self.browser:
            await self.browser.close()

    async def __aenter__(self) -> "GrokBrowserAgent":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type,
        exc_val: BaseException,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()
