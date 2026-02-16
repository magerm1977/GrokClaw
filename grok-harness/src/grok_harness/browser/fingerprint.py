"""Browser fingerprint management for session persistence."""

import hashlib
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class BrowserFingerprint:
    """
    Manage browser fingerprints for session persistence.

    Creates consistent fingerprints that can be reused across sessions
    to appear as a returning user rather than a new bot.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or Path.home() / ".grok-harness" / "fingerprints"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.fingerprints: Dict[str, Dict[str, Any]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all saved fingerprints."""
        for fp_file in self.storage_path.glob("*.json"):
            try:
                with open(fp_file, "r") as f:
                    fp_data = json.load(f)
                    self.fingerprints[fp_data.get("id", fp_file.stem)] = fp_data
            except (json.JSONDecodeError, OSError):
                pass

    def generate_fingerprint(self, seed: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a consistent fingerprint based on seed.

        Args:
            seed: String to seed the RNG for consistent fingerprints.

        Returns:
            Fingerprint dictionary.
        """
        if seed:
            hash_obj = hashlib.md5(seed.encode())
            random.seed(int(hash_obj.hexdigest(), 16) % (2**32))

        fp_id = (
            hashlib.md5(seed.encode()).hexdigest()[:16]
            if seed
            else hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:16]
        )

        fingerprint: Dict[str, Any] = {
            "id": fp_id,
            "created_at": datetime.now().isoformat(),
            "user_agent": self._generate_user_agent(),
            "screen": self._generate_screen(),
            "fonts": self._generate_fonts(),
            "webgl_vendor": self._generate_webgl_vendor(),
            "audio": self._generate_audio_fingerprint(),
            "canvas": self._generate_canvas_fingerprint(),
            "timezone": self._generate_timezone(),
            "language": self._generate_language(),
            "platform": self._generate_platform(),
            "hardware": self._generate_hardware(),
            "plugins": self._generate_plugins(),
            "do_not_track": random.choice([0, 1, None]),
        }

        random.seed()
        return fingerprint

    def _generate_user_agent(self) -> str:
        """Generate realistic user agent."""
        browsers = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        return random.choice(browsers)

    def _generate_screen(self) -> Dict[str, int]:
        """Generate screen resolution."""
        resolutions = [
            {"width": 1920, "height": 1080, "color_depth": 24},
            {"width": 1366, "height": 768, "color_depth": 24},
            {"width": 2560, "height": 1440, "color_depth": 30},
            {"width": 3840, "height": 2160, "color_depth": 30},
        ]
        return random.choice(resolutions).copy()

    def _generate_fonts(self) -> List[str]:
        """Generate list of installed fonts."""
        font_lists = [
            ["Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana"],
            ["Arial", "Helvetica", "Georgia", "Times New Roman", "Courier New", "Impact"],
            ["Arial", "Helvetica", "Times New Roman", "Courier New", "Comic Sans MS"],
        ]
        return random.choice(font_lists).copy()

    def _generate_webgl_vendor(self) -> Dict[str, str]:
        """Generate WebGL vendor strings."""
        vendors = [
            {"vendor": "Intel Inc.", "renderer": "Intel Iris OpenGL Engine"},
            {"vendor": "NVIDIA Corporation", "renderer": "NVIDIA GeForce RTX 3070"},
            {"vendor": "AMD", "renderer": "AMD Radeon Pro 5500M"},
            {"vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics, OpenGL)"},
        ]
        return random.choice(vendors).copy()

    def _generate_audio_fingerprint(self) -> str:
        """Generate audio context fingerprint."""
        return hashlib.md5(str(random.random()).encode()).hexdigest()[:32]

    def _generate_canvas_fingerprint(self) -> str:
        """Generate canvas fingerprint."""
        return hashlib.md5(str(random.random()).encode()).hexdigest()[:32]

    def _generate_timezone(self) -> int:
        """Generate timezone offset in minutes."""
        offsets = [-300, -240, -180, 0, 60, 120, 480, 540, 600, 660]
        return random.choice(offsets)

    def _generate_language(self) -> str:
        """Generate language preference."""
        languages = ["en-US", "en-GB", "en-CA", "en-AU", "en"]
        return random.choice(languages)

    def _generate_platform(self) -> str:
        """Generate platform string."""
        platforms = ["Win32", "MacIntel", "Linux x86_64"]
        return random.choice(platforms)

    def _generate_hardware(self) -> Dict[str, int]:
        """Generate hardware capabilities."""
        return {
            "cores": random.choice([4, 6, 8, 12, 16]),
            "memory": random.choice([4, 8, 16, 32]),
            "touch_points": random.choice([0, 5, 10]),
        }

    def _generate_plugins(self) -> List[str]:
        """Generate list of installed plugins."""
        plugin_lists = [
            ["Chrome PDF Plugin", "Chrome PDF Viewer", "Native Client"],
            ["PDF Viewer", "QuickTime", "Java"],
            ["Chrome PDF Plugin", "Chrome PDF Viewer"],
        ]
        return random.choice(plugin_lists).copy()

    def save_fingerprint(self, fingerprint: Dict[str, Any]) -> str:
        """Save fingerprint to storage."""
        fp_id = fingerprint.get(
            "id",
            hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:16],
        )
        fp_file = self.storage_path / f"{fp_id}.json"

        with open(fp_file, "w") as f:
            json.dump(fingerprint, f, indent=2)

        self.fingerprints[fp_id] = fingerprint
        return fp_id

    def load_fingerprint(self, fp_id: str) -> Optional[Dict[str, Any]]:
        """Load fingerprint by ID."""
        if fp_id in self.fingerprints:
            return self.fingerprints[fp_id]

        fp_file = self.storage_path / f"{fp_id}.json"
        if fp_file.exists():
            with open(fp_file, "r") as f:
                fp_data = json.load(f)
                self.fingerprints[fp_id] = fp_data
                return fp_data

        return None

    def delete_fingerprint(self, fp_id: str) -> None:
        """Delete fingerprint."""
        if fp_id in self.fingerprints:
            del self.fingerprints[fp_id]

        fp_file = self.storage_path / f"{fp_id}.json"
        if fp_file.exists():
            fp_file.unlink()

    def list_fingerprints(self) -> List[Dict[str, Any]]:
        """List all saved fingerprints."""
        return list(self.fingerprints.values())

    def get_consistent_fingerprint(self, domain: str) -> Dict[str, Any]:
        """
        Get or create a consistent fingerprint for a domain.

        This ensures the same fingerprint is used for the same domain
        to appear as a returning visitor.
        """
        for fp in self.fingerprints.values():
            if fp.get("domain") == domain:
                return fp

        fingerprint = self.generate_fingerprint(seed=domain)
        fingerprint["domain"] = domain
        self.save_fingerprint(fingerprint)

        return fingerprint
