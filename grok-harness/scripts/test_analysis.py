"""
Website content analyzer using BeautifulSoup
Extracts actual content, not assumptions
"""

import aiohttp
from typing import Dict, List, Optional, Tuple
import re
from urllib.parse import urlparse
import logging

# Try importing BeautifulSoup with helpful error
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

logger = logging.getLogger(__name__)

class SiteAnalyzer:
    """Properly analyze website content"""
    
    @classmethod
    def _check_dependencies(cls):
        """Check if required dependencies are installed"""
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 is required for site analysis. "
                "Install it with: pip install beautifulsoup4 lxml"
            )
    
    @classmethod
    async def fetch_html(cls, url: str, timeout: int = 10) -> Optional[str]:
        """Fetch HTML from URL with proper headers"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None
    
    @classmethod
    def _get_soup(cls, html: str):
        """Get BeautifulSoup object with dependency check"""
        cls._check_dependencies()
        return BeautifulSoup(html, 'lxml')
    
    @classmethod
    def extract_meta_tags(cls, soup) -> Dict[str, str]:
        """Extract all meta tags"""
        meta = {}
        for tag in soup.find_all('meta'):
            if tag.get('name'):
                meta[tag['name']] = tag.get('content', '')
            elif tag.get('property'):
                meta[tag['property']] = tag.get('content', '')
        return meta
    
    @classmethod
    def extract_headlines(cls, soup) -> Dict[str, List[str]]:
        """Extract all headlines (h1-h3)"""
        headlines = {
            'h1': [h.get_text(strip=True) for h in soup.find_all('h1') if h.get_text(strip=True)],
            'h2': [h.get_text(strip=True) for h in soup.find_all('h2') if h.get_text(strip=True)],
            'h3': [h.get_text(strip=True) for h in soup.find_all('h3') if h.get_text(strip=True)]
        }
        return headlines
    
    @classmethod
    def extract_pricing(cls, soup) -> List[Dict]:
        """Extract pricing information"""
        pricing = []
        
        # Look for common pricing patterns
        price_elements = soup.find_all(['div', 'section'], class_=re.compile(r'price|pricing|plan|card', re.I))
        
        for elem in price_elements:
            text = elem.get_text(strip=True)
            if '$' in text or '€' in text or '£' in text:
                # Extract price
                price_match = re.search(r'[\$\€\£]\s*(\d+)', text)
                if price_match:
                    pricing.append({
                        'text': text[:100],
                        'price': price_match.group(0)
                    })
        
        return pricing[:3]  # Top 3 pricing elements
    
    @classmethod
    def extract_ctas(cls, soup) -> List[str]:
        """Extract call-to-action buttons and links"""
        ctas = []
        
        # Buttons
        for btn in soup.find_all(['button', 'a'], class_=re.compile(r'btn|button|cta|start|try', re.I)):
            text = btn.get_text(strip=True)
            if text and len(text) < 50 and text not in ctas:
                ctas.append(text)
        
        return ctas[:5]
    
    @classmethod
    def extract_key_messages(cls, soup) -> List[str]:
        """Extract key value propositions"""
        messages = []
        
        # Look for hero section
        hero = soup.find(['section', 'div'], class_=re.compile(r'hero|header|banner', re.I))
        if hero:
            hero_text = hero.get_text(strip=True)
            if hero_text:
                sentences = re.split(r'[.!?]+', hero_text)
                messages.extend([s.strip() for s in sentences if len(s.strip()) > 20][:2])
        
        # Look for feature sections
        features = soup.find_all(['div', 'section'], class_=re.compile(r'feature|card', re.I))
        for feat in features[:3]:
            text = feat.get_text(strip=True)
            if text and len(text) < 200:
                messages.append(text[:150])
        
        return messages[:5]
    
    @classmethod
    def detect_purpose(cls, text: str, headlines: Dict) -> Dict[str, float]:
        """Detect what the site is about based on content"""
        text_lower = text.lower()
        
        # Keyword categories with weighted scoring
        categories = {
            'ai_interview_coach': {
                'keywords': ['interview', 'ai coach', 'practice', 'callback', 'job offer', 'scoring', 'diagnostic', 'drill', 'mock interview'],
                'weight': 1.0
            },
            'executive_coach': {
                'keywords': ['executive', 'leadership', 'ceo', 'management', 'career growth', 'professional coach'],
                'weight': 0.8
            },
            'saas_platform': {
                'keywords': ['platform', 'dashboard', 'sign up', 'pricing', 'subscription', 'features'],
                'weight': 0.6
            },
            'content_site': {
                'keywords': ['blog', 'article', 'read more', 'subscribe', 'newsletter'],
                'weight': 0.5
            },
            'ecommerce': {
                'keywords': ['shop', 'buy', 'cart', 'checkout', 'purchase', 'order'],
                'weight': 0.7
            }
        }
        
        scores = {}
        for category, data in categories.items():
            score = sum(1 for keyword in data['keywords'] if keyword in text_lower)
            scores[category] = (score / len(data['keywords'])) * data['weight']
        
        return scores
    
    @classmethod
    async def analyze(cls, url: str) -> Dict:
        """
        Comprehensive site analysis
        
        Returns:
            Dict with:
            - title: Page title
            - description: Meta description
            - headlines: h1-h3 tags
            - pricing: Extracted pricing info
            - ctas: Call-to-action buttons
            - key_messages: Main value propositions
            - purpose_detection: What the site appears to be
            - raw_text_preview: First 1000 chars of text
            - error: Error message if analysis failed
        """
        try:
            # Check dependencies first
            cls._check_dependencies()
            
            # Fetch HTML
            html = await cls.fetch_html(url)
            if not html:
                return {
                    "error": f"Could not fetch {url}",
                    "url": url
                }
            
            # Parse
            soup = cls._get_soup(html)
            
            # Remove script/style tags
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()
            
            # Get clean text
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            
            # Extract components
            title = soup.title.string if soup.title else ""
            meta = cls.extract_meta_tags(soup)
            headlines = cls.extract_headlines(soup)
            pricing = cls.extract_pricing(soup)
            ctas = cls.extract_ctas(soup)
            key_messages = cls.extract_key_messages(soup)
            
            # Detect purpose
            purpose_scores = cls.detect_purpose(text, headlines)
            primary_purpose = max(purpose_scores, key=purpose_scores.get) if purpose_scores else "unknown"
            confidence = purpose_scores.get(primary_purpose, 0) if purpose_scores else 0
            
            return {
                "url": url,
                "title": title.strip() if title else "",
                "description": meta.get('description', '').strip(),
                "headlines": headlines,
                "pricing": pricing,
                "ctas": ctas,
                "key_messages": key_messages,
                "purpose_detection": {
                    "primary": primary_purpose,
                    "confidence": round(confidence, 2),
                    "all_scores": purpose_scores
                },
                "raw_text_preview": text[:1000] + "..." if len(text) > 1000 else text
            }
            
        except ImportError as e:
            return {
                "error": str(e),
                "url": url,
                "fix": "pip install beautifulsoup4 lxml"
            }
        except Exception as e:
            logger.exception("Site analysis failed")
            return {
                "error": f"Analysis failed: {str(e)}",
                "url": url
            }