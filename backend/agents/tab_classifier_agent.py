"""TabClassifierAgent: Categorizes tabs into types."""
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CLASSIFICATION_CATEGORIES, get_llm  # Centralized LLM factory - uses MODEL_PROVIDER from .env
import logging
import json

logger = logging.getLogger(__name__)


class TabClassifierAgent:
    """Classifies tabs into categories."""
    
    def __init__(self):
        self.llm = get_llm()  # Uses MODEL_PROVIDER from .env
        self.categories = CLASSIFICATION_CATEGORIES
    
    def classify_tab(self, tab: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a single tab."""
        title = tab.get("title", "")
        url = tab.get("url", "")
        text = (tab.get("text", "") or "")[:2000]  # Limit for classification
        
        system_prompt = f"""You are a tab classifier. Classify the given tab into one of these categories: {', '.join(self.categories)}.

Return ONLY a JSON object with:
- "category": one of the categories
- "confidence": float between 0 and 1
- "reason": brief explanation

Categories:
- research: educational, informational, learning content
- shopping: product pages, e-commerce, buying intent
- entertainment: videos, games, social media, fun content
- work: professional, productivity, business tools
- distraction: time-wasting, low-value content
- duplicate: same or very similar to another tab
- unknown: cannot determine

Return valid JSON only, no markdown."""
        
        user_prompt = f"""Title: {title}
URL: {url}
Content preview: {text[:1000]}

Classify this tab."""
        
        try:
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            
            # Parse JSON from response
            json_str = content.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            result = json.loads(json_str)
            return {
                "category": result.get("category", "unknown"),
                "confidence": float(result.get("confidence", 0.5)),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {"category": "unknown", "confidence": 0.0, "reason": f"Error: {e}"}
    
    def classify_multiple_tabs(self, tabs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify multiple tabs."""
        results = []
        for tab in tabs:
            classification = self.classify_tab(tab)
            results.append({
                **tab,
                "classification": classification,
            })
        return results
    
    def detect_duplicates(self, tabs: List[Dict[str, Any]]) -> List[List[int]]:
        """Detect duplicate tabs based on URL and title similarity."""
        duplicates = []
        processed = set()
        
        for i, tab1 in enumerate(tabs):
            if i in processed:
                continue
            group = [i]
            url1 = tab1.get("url", "").split("?")[0]  # Remove query params
            title1 = tab1.get("title", "").lower()
            
            for j, tab2 in enumerate(tabs[i+1:], start=i+1):
                if j in processed:
                    continue
                url2 = tab2.get("url", "").split("?")[0]
                title2 = tab2.get("title", "").lower()
                
                if url1 == url2 or (title1 == title2 and len(title1) > 10):
                    group.append(j)
                    processed.add(j)
            
            if len(group) > 1:
                duplicates.append(group)
                processed.update(group)
        
        return duplicates


