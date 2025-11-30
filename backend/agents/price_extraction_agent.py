"""PriceExtractionAgent: Extracts product name and price from shopping pages."""
from typing import Dict, Any, Optional, Tuple
from utils.price_utils import extract_price, parse_currency
import re
import logging

logger = logging.getLogger(__name__)


class PriceExtractionAgent:
    """Extracts product information from shopping pages."""
    
    def extract_product_info(self, tab: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract product name and price from a shopping tab."""
        title = tab.get("title", "")
        url = tab.get("url", "")
        text = tab.get("text", "") or ""
        
        # Try to extract price
        price_result = extract_price(text)
        if not price_result:
            # Try from title
            price_result = extract_price(title)
        
        if not price_result:
            return None
        
        price, currency = price_result
        
        # Extract product name (heuristic)
        product_name = self._extract_product_name(title, text)
        
        return {
            "product_name": product_name,
            "price": price,
            "currency": currency,
            "url": url,
            "source": "extracted",
        }
    
    def _extract_product_name(self, title: str, text: str) -> str:
        """Extract product name from title and text."""
        # Common patterns
        title_clean = title.strip()
        
        # Remove common suffixes
        suffixes = [" - Amazon", " | eBay", " - Walmart", " | Best Buy", " - Target"]
        for suffix in suffixes:
            if title_clean.endswith(suffix):
                title_clean = title_clean[:-len(suffix)]
        
        # Try to find product name in text (look for "Product:", "Item:", etc.)
        patterns = [
            r'product[:\s]+([^\n]{10,100})',
            r'item[:\s]+([^\n]{10,100})',
            r'name[:\s]+([^\n]{10,100})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fallback to title
        return title_clean[:200]  # Limit length
    
    def is_shopping_page(self, tab: Dict[str, Any]) -> bool:
        """Check if tab is likely a shopping page."""
        url = (tab.get("url", "") or "").lower()
        title = (tab.get("title", "") or "").lower()
        text = (tab.get("text", "") or "").lower()
        
        shopping_indicators = [
            "amazon", "ebay", "walmart", "target", "best buy", "shopify",
            "add to cart", "buy now", "price", "$", "€", "£",
            "product", "shopping", "checkout", "cart"
        ]
        
        combined = f"{url} {title} {text[:500]}"
        return any(indicator in combined for indicator in shopping_indicators)


