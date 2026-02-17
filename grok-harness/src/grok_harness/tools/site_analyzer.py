"""
Website content analyzer using BeautifulSoup.
Extracts actual content instead of inferring from domain names.
"""

import re
from typing import Any, Dict, List, Optional

import aiohttp


class SiteAnalyzer:
    """Analyze website content for accurate understanding."""

    @staticmethod
    async def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
        """Fetch HTML from URL with browser-like headers."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
        except Exception:
            return None

    @staticmethod
    def _get_soup(html: str):
        """Parse HTML with lxml or html.parser fallback."""
        try:
            from bs4 import BeautifulSoup

            return BeautifulSoup(html, "lxml")
        except Exception:
            from bs4 import BeautifulSoup

            return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_meta_tags(soup: Any) -> Dict[str, str]:
        """Extract meta tags (name and property)."""
        meta: Dict[str, str] = {}
        for tag in soup.find_all("meta"):
            if tag.get("name"):
                meta[tag["name"]] = tag.get("content", "")
            elif tag.get("property"):
                meta[tag["property"]] = tag.get("content", "")
        return meta

    @staticmethod
    def extract_headlines(soup: Any) -> Dict[str, List[str]]:
        """Extract headlines h1-h3."""
        headlines: Dict[str, List[str]] = {
            "h1": [],
            "h2": [],
            "h3": [],
        }
        for level in ("h1", "h2", "h3"):
            for h in soup.find_all(level):
                t = h.get_text(strip=True)
                if t:
                    headlines[level].append(t)
        return headlines

    @staticmethod
    def extract_pricing(soup: Any, text: str) -> List[str]:
        """Extract pricing info from page (prices, plans)."""
        found: List[str] = []
        # Price patterns: $29, $29/mo, $99 one-time, Free, etc.
        price_re = re.compile(
            r"(?:\$|€|£)\s*\d+(?:\.\d{2})?(?:\s*/\s*(?:mo|month|yr|year))?|"
            r"\d+(?:\.\d{2})?\s*(?:\$|€|£)|"
            r"(?:free|trial)\b",
            re.I,
        )
        for m in price_re.finditer(text):
            s = m.group(0).strip()
            if s not in found:
                found.append(s)
        # Also check pricing/plan sections
        for el in soup.find_all(["div", "section"], class_=re.compile(r"price|pricing|plan", re.I)):
            t = el.get_text(separator=" ", strip=True)
            for m in price_re.finditer(t):
                s = m.group(0).strip()
                if s not in found:
                    found.append(s)
        return found[:5]

    @staticmethod
    def extract_ctas(soup: Any) -> List[str]:
        """Extract call-to-action buttons and links."""
        ctas: List[str] = []
        btn_class = re.compile(r"btn|button|cta", re.I)
        for el in soup.find_all(["button", "a"]):
            classes = el.get("class") or []
            if any(btn_class.search(c) for c in classes if isinstance(c, str)):
                text = el.get_text(strip=True)
                if text and len(text) < 50:
                    ctas.append(text)
        return ctas[:5]

    @staticmethod
    def extract_key_phrases(text: str, keywords: List[str]) -> List[str]:
        """Extract sentences containing key phrases."""
        sentences = re.split(r"[.!?]+", text)
        matches: List[str] = []
        for sentence in sentences:
            s = sentence.strip()
            if len(s) < 20:
                continue
            if any(kw.lower() in s.lower() for kw in keywords):
                matches.append(s[:150])
        return matches[:5]

    @staticmethod
    def detect_site_purpose(text: str, headlines: Dict[str, List[str]]) -> Dict[str, float]:
        """Detect site purpose from content."""
        text_lower = text.lower()
        categories = {
            "ai_interview_coach": [
                "interview",
                "ai coach",
                "practice",
                "callback",
                "job offer",
                "hiring",
                "recruiter",
            ],
            "executive_coach": [
                "executive",
                "leadership",
                "ceo",
                "management",
                "career growth",
            ],
            "saas_platform": ["platform", "dashboard", "sign up", "pricing", "subscription"],
            "content_site": ["blog", "article", "read more", "subscribe"],
            "ecommerce": ["shop", "buy", "cart", "checkout", "purchase"],
        }
        scores: Dict[str, float] = {}
        for category, kws in categories.items():
            count = sum(1 for kw in kws if kw in text_lower)
            scores[category] = count / len(kws) if kws else 0
        return scores

    @classmethod
    async def analyze(cls, url: str) -> Dict[str, Any]:
        """
        Run site analysis.

        Returns:
            Dict with title, description, headlines, ctas, key_messages,
            purpose_detection, raw_text_preview; or error key on failure.
        """
        html = await cls.fetch_html(url)
        if not html:
            return {"error": f"Could not fetch {url}", "url": url}

        soup = cls._get_soup(html)
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        title = soup.title.string if soup.title else ""
        meta = cls.extract_meta_tags(soup)
        headlines = cls.extract_headlines(soup)
        pricing = cls.extract_pricing(soup, text)
        ctas = cls.extract_ctas(soup)

        key_messages = cls.extract_key_phrases(
            text,
            [
                "interview",
                "practice",
                "coach",
                "callback",
                "job",
                "improve",
                "drill",
                "diagnose",
                "test",
                "hire",
            ],
        )

        purpose_scores = cls.detect_site_purpose(text, headlines)
        primary = max(purpose_scores, key=purpose_scores.get)
        confidence = purpose_scores[primary]

        return {
            "url": url,
            "title": title or "",
            "description": meta.get("description", ""),
            "headlines": headlines,
            "pricing": pricing,
            "ctas": ctas,
            "key_messages": key_messages,
            "purpose_detection": {
                "primary": primary,
                "confidence": round(confidence, 2),
                "all_scores": purpose_scores,
            },
            "raw_text_preview": (
                text[:1000] + "..." if len(text) > 1000 else text
            ),
        }
