"""Text processing utilities."""
import re
import math
from typing import List

WORD_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Tokenize text into words."""
    return [t.lower() for t in WORD_RE.findall(text or "")]


def overlap_score(query_tokens: List[str], content_tokens: List[str]) -> float:
    """Calculate cosine-like overlap score between query and content."""
    if not query_tokens or not content_tokens:
        return 0.0
    q_set, c_set = set(query_tokens), set(content_tokens)
    intersection = len(q_set & c_set)
    if intersection == 0:
        return 0.0
    return intersection / math.sqrt(len(q_set) * len(c_set))


def make_tab_tokens(tab_title: str, tab_url: str, tab_text: str, max_chars: int = 2000) -> List[str]:
    """Create tokens from tab metadata."""
    base = f"{tab_title} {tab_url} {(tab_text or '')[:max_chars]}"
    return tokenize(base)


