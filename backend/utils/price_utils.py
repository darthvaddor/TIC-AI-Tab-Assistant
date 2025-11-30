"""Price extraction and parsing utilities."""
import re
from typing import Optional, Tuple

PRICE_PATTERNS = [
    r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
    r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD',  # 1234.56 USD
    r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*\$',   # 1234.56 $
    r'price[:\s]+(\d+(?:,\d{3})*(?:\.\d{2})?)',  # price: 1234.56
    r'(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Just numbers
]

CURRENCY_SYMBOLS = {
    '$': 'USD',
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',
    '₹': 'INR',
}


def extract_price(text: str) -> Optional[Tuple[float, str]]:
    """Extract price and currency from text."""
    text_clean = text.replace('\n', ' ').replace('\t', ' ')
    
    for pattern in PRICE_PATTERNS:
        matches = re.findall(pattern, text_clean, re.IGNORECASE)
        if matches:
            price_str = matches[0].replace(',', '')
            try:
                price = float(price_str)
                currency = parse_currency(text_clean)
                return (price, currency)
            except ValueError:
                continue
    
    return None


def normalize_price(price_str: str) -> Optional[float]:
    """Normalize price string to float."""
    try:
        return float(price_str.replace(',', '').replace('$', '').strip())
    except (ValueError, AttributeError):
        return None


def parse_currency(text: str) -> str:
    """Parse currency from text."""
    text_upper = text.upper()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text or code in text_upper:
            return code
    return "USD"  # Default


