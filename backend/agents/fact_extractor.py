"""Fact Extractor: specialized agent for extracting facts from search results."""
import logging
from typing import Dict, Any, List, Optional
from config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

class FactExtractor:
    """Extracts precise facts from browser tabs, prioritizing search results."""
    
    def __init__(self):
        self.llm = get_llm()
        
    def extract(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Finds the best tab for the query and extracts the answer.
        """
        logger.info(f"[FACT] Extracting fact for: '{query}'")
        
        # 1. Find the most relevant tab (simple heuristic for now: Google Search)
        target_tab = self._find_best_tab(query, tabs)
        
        if not target_tab:
            return {
                "found": False,
                "answer": "I couldn't find a relevant open tab to answer this. Try opening a Google Search for it first.",
                "source_tab": None
            }
            
        # 2. Extract answer from that tab's content
        answer = self._extract_from_content(query, target_tab)
        
        return {
            "found": True,
            "answer": answer,
            "source_tab": target_tab['title'],
            "source_tab_id": target_tab.get('id'),
            "source_tab_url": target_tab.get('url')
        }
        
    def _find_best_tab(self, query: str, tabs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Finds the best tab by scoring relevance to the query."""
        query_lower = query.lower()
        query_terms = [w for w in query_lower.split() if len(w) > 3 and w not in ["what", "when", "where", "who", "how", "why"]]
        
        best_tab = None
        best_score = 0
        
        for tab in tabs:
            score = 0
            title = tab.get('title', '').lower()
            url = tab.get('url', '').lower()
            
            # 1. Keyword matching in Title (High weight)
            for term in query_terms:
                if term in title:
                    score += 10
            
            # 2. Keyword matching in URL (Medium weight)
            for term in query_terms:
                if term in url:
                    score += 5
                    
            # 3. Boost for Google Search/Wikipedia if relevant terms found
            if score > 0:
                if "google.com/search" in url:
                    score += 3 # Slight boost for search results
                if "wikipedia.org" in url:
                    score += 3 # Slight boost for wiki
            
            # 4. Exact phrase match bonus
            if query_lower in title:
                score += 20
                
            if score > best_score:
                best_score = score
                best_tab = tab
                
        # Only return if we have a decent match, otherwise return None (or fallback to Google Search if no specific match)
        if best_score > 0:
            return best_tab
            
        # Fallback: If no keywords matched, but we have a Google Search tab, it might be relevant context
        # But only if the query looks like a general fact question
        for tab in tabs:
            if "google.com/search" in tab.get('url', ''):
                return tab
                
        return None
        
    def _extract_from_content(self, query: str, tab: Dict[str, Any]) -> str:
        """Uses LLM to extract the answer from the tab's content."""
        content = tab.get('content', '')
        # Truncate content to avoid context limit (approx 10k chars)
        content = content[:10000]
        
        system_prompt = f"""You are a Fact Extractor. 
        Your goal is to answer the user's question based ONLY on the provided page content.
        
        User Question: "{query}"
        
        Page Title: {tab.get('title')}
        Page Content:
        {content}
        
        Instructions:
        1. Extract the direct answer (e.g., a date, a name, a number).
        2. If the page contains a "Knowledge Panel" or "Featured Snippet", prioritize that information.
        3. Be concise. Do not say "According to the page...". Just give the answer.
        4. If the answer is NOT in the content, say "I couldn't find the answer in this tab."
        """
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="What is the answer?")
            ]
            response = self.llm.invoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"[FACT] Extraction failed: {e}")
            return "Error extracting answer."
