"""TabReaderAgent: Extracts content from browser tabs."""
from typing import List, Dict, Any, Optional
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_llm  # Centralized LLM factory - uses MODEL_PROVIDER from .env
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


class TabReaderAgent:
    """Extracts and normalizes content from browser tabs."""
    
    def __init__(self, max_text_length: int = 4000):
        self.max_text_length = max_text_length
        self.llm = get_llm()  # Uses MODEL_PROVIDER from .env
    
    def clean_content_with_llm(self, title: str, url: str, raw_text: str) -> str:
        """Use LLM to extract main content and remove UI/navigation text."""
        if not raw_text or len(raw_text.strip()) < 50:
            return raw_text
        
        # Limit input to avoid token limits
        text_sample = raw_text[:6000] if len(raw_text) > 6000 else raw_text
        
        system_prompt = """You are a content extraction assistant. Your task is to extract ONLY the main content from web page text, removing all navigation, UI elements, and irrelevant text.

Rules:
- Extract the actual article/content text
- Remove navigation menus, headers, footers, sidebars
- Remove UI elements like "Skip to", "Jump to", "Main menu", "Search", etc.
- Remove Wikipedia navigation like "23 languages", "Article Talk", "View source", etc.
- Remove Google Search UI like "Filters", "Tools", "All Images Videos", etc.
- Remove email UI like "Print all", "In new window", "Remove label", etc.
- Keep only the meaningful content that a user would read
- Preserve the structure and flow of the actual content
- If it's a search results page, extract the search results (titles and snippets)
- If it's an article, extract the article body
- If it's an email, extract the email content

Return ONLY the cleaned content, nothing else."""
        
        user_prompt = f"""Page Title: {title}
Page URL: {url}

Raw Page Text:
{text_sample}

Extract and return ONLY the main content, removing all navigation and UI elements."""
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            cleaned = response.content if hasattr(response, "content") else str(response)
            # Fallback if LLM returns something weird
            if len(cleaned) < 20 or cleaned.lower().startswith("i cannot") or cleaned.lower().startswith("i'm unable"):
                logger.warning("LLM content cleaning returned suspicious result, using original text")
                return raw_text[:self.max_text_length]
            return cleaned[:self.max_text_length]
        except Exception as e:
            logger.error(f"LLM content cleaning failed: {e}, using original text")
            return raw_text[:self.max_text_length]
    
    def extract_tab_content(self, tab_data: Dict[str, Any], use_llm_cleaning: bool = False) -> Dict[str, Any]:
        """Extract and normalize content from a single tab."""
        title = (tab_data.get("title") or "").strip()
        url = (tab_data.get("url") or "").strip()
        text = (tab_data.get("text") or "").strip()
        
        # Use LLM to clean content if enabled
        if use_llm_cleaning and text and len(text) > 100:
            try:
                text = self.clean_content_with_llm(title, url, text)
            except Exception as e:
                logger.warning(f"LLM cleaning failed for tab {tab_data.get('id')}: {e}, using original text")
        
        # Normalize whitespace
        text = " ".join(text.split())[:self.max_text_length]
        
        return {
            "id": tab_data.get("id"),
            "title": title,
            "url": url,
            "text": text,
            "text_length": len(text),
        }
    
    def extract_multiple_tabs(self, tabs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract content from multiple tabs."""
        extracted = []
        for tab in tabs:
            try:
                content = self.extract_tab_content(tab)
                if content.get("text") or content.get("title"):
                    extracted.append(content)
            except Exception as e:
                logger.warning(f"Failed to extract tab {tab.get('id')}: {e}")
        return extracted
    
    def is_valid_tab(self, tab_data: Dict[str, Any]) -> bool:
        """Check if tab is valid for processing."""
        url = tab_data.get("url", "")
        if not url or url.startswith(("chrome://", "edge://", "about:", "moz-extension://")):
            return False
        return True


