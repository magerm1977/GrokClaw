#!/usr/bin/env python
"""
Pre-release verification script.
Run this before pushing to GitHub.
"""

import re
import sys
from pathlib import Path
from typing import List


def check_api_keys() -> List[str]:
    """Check for exposed API keys."""
    patterns = [
        r"xai-[A-Za-z0-9]{50,}",
        r"sk-[A-Za-z0-9]{48,}",
        r'api_key\s*=\s*["\'][A-Za-z0-9]{20,}',
        r'token\s*=\s*["\'][A-Za-z0-9]{20,}',
    ]
    issues = []
    skip_dirs = {"site-packages", "venv", ".venv", "node_modules", "__pycache__"}
    for ext in [".py", ".md", ".json", ".yaml", ".yml"]:
        for file in Path(".").rglob(f"*{ext}"):
            if any(s in str(file) for s in skip_dirs):
                continue
            if file.name == ".env.example" or "example" in file.name:
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                for pattern in patterns:
                    if re.search(pattern, content):
                        issues.append(f"Possible API key in {file}")
                        break
            except Exception:
                pass
    return issues


def check_personal_data() -> List[str]:
    """Check for personal names (excluding examples)."""
    names = ["mmager", "fred"]  # mark excluded: pytest.mark, market cause false positives
    issues = []
    skip_dirs = {"site-packages", "venv", ".venv", "__pycache__"}
    for ext in [".py", ".md", ".json", ".yaml", ".yml"]:
        for file in Path(".").rglob(f"*{ext}"):
            if any(s in str(file) for s in skip_dirs):
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="ignore").lower()
                if "example" in file.name or "placeholder" in content:
                    continue
                for name in names:
                    if name in content:
                        issues.append(f"Possible personal name '{name}' in {file}")
                        break
            except Exception:
                pass
    return issues


def check_gitignore() -> List[str]:
    """Check .gitignore has necessary entries."""
    required = [".env", "config.yaml", ".grok-harness", "telegram.json", "*.db"]
    if not Path(".gitignore").exists():
        return ["No .gitignore found"]
    content = Path(".gitignore").read_text(encoding="utf-8")
    missing = [item for item in required if item not in content]
    return [f"Missing from .gitignore: {item}" for item in missing]


def main() -> int:
    """Run pre-release checks."""
    print("\nGrokClaw Pre-Release Check")
    print("=" * 50)

    issues = []
    issues.extend(check_api_keys())
    issues.extend(check_personal_data())
    issues.extend(check_gitignore())

    if issues:
        print(f"\nFound {len(issues)} issues to fix:\n")
        for issue in issues:
            print(f"  {issue}")
        return 1

    print("\nAll checks passed! Ready to ship.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
