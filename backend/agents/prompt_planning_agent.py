"""PromptPlanningAgent: Analyzes user queries and creates action plans."""
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_llm  # Centralized LLM factory - uses MODEL_PROVIDER from .env
import logging
import json

logger = logging.getLogger(__name__)


class PromptPlanningAgent:
    """Analyzes user queries and creates execution plans."""
    
    def __init__(self):
        self.llm = get_llm()  # Uses MODEL_PROVIDER from .env
    
    def create_plan(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze query and create execution plan."""
        query_lower = query.lower().strip()
        tab_count = len(tabs)
        
        # Fast heuristic planning for common queries (skip LLM call)
        if "analyze" in query_lower and ("my tabs" in query_lower or "all tabs" in query_lower):
            logger.info(f"[PLAN] Using fast heuristic plan for 'analyze my tabs'")
            return {
                "mode": "analysis",
                "needs_classification": True,
                "needs_summarization": True,
                "needs_price_extraction": False,
                "needs_youtube_transcript": False,
                "should_ask_cleanup": False,
                "follow_up_needed": False,
                "reasoning": "Fast heuristic: general tab analysis query"
            }
        
        tab_types = self._analyze_tab_types(tabs)
        
        system_prompt = """You are a query planning agent for TabSensei. Analyze the user's query and create an execution plan.

Return ONLY a JSON object with:
- "mode": "single" | "multi" | "analysis" | "cleanup"
- "needs_classification": boolean (whether to classify tabs)
- "needs_summaries": boolean (whether to generate summaries)
- "needs_price_extraction": boolean (whether to extract prices)
- "needs_youtube_transcript": boolean (whether to get YouTube video transcript)
- "should_ask_cleanup": boolean (whether to prompt user to close irrelevant tabs - only true for specific single-tab queries, NOT for "analyze all tabs" type queries)
- "needs_followup": boolean (whether the answer might need follow-up questions)
- "priority_tabs": array of tab indices to prioritize (empty if all tabs)
- "reasoning": brief explanation of the plan

Modes:
- "single": Answer a specific question about one tab (e.g., "what is johnny depp's first movie")
- "multi": Compare multiple tabs (e.g., "compare these laptops")
- "analysis": General analysis of all tabs (e.g., "analyze my tabs", "what tabs do I have open")
- "cleanup": Close irrelevant tabs

Rules for should_ask_cleanup:
- TRUE only for specific single-tab queries where a relevant tab is found (e.g., "what is X", "when did Y happen")
- FALSE for general queries like "analyze my tabs", "what tabs do I have", "compare all tabs", "summarize everything"
- FALSE for multi-tab comparison queries

Return valid JSON only, no markdown."""
        
        tab_preview = "\n".join([f"{i+1}. {t.get('title', 'N/A')[:60]} ({t.get('url', 'N/A')[:50]})" for i, t in enumerate(tabs[:10])])
        
        user_prompt = f"""User Query: "{query}"

Number of tabs: {tab_count}
Tab types detected: {', '.join(tab_types)}

Tabs:
{tab_preview}

Create an execution plan for this query."""
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            content = response.content if hasattr(response, "content") else str(response)
            
            # Parse JSON
            json_str = content.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            plan = json.loads(json_str)
            
            # Validate and set defaults
            plan.setdefault("mode", "analysis")
            plan.setdefault("needs_classification", True)
            plan.setdefault("needs_summaries", True)
            plan.setdefault("needs_price_extraction", False)
            plan.setdefault("needs_youtube_transcript", False)
            plan.setdefault("should_ask_cleanup", False)
            plan.setdefault("needs_followup", False)
            plan.setdefault("priority_tabs", [])
            plan.setdefault("reasoning", "")
            
            logger.info(f"Created plan: mode={plan['mode']}, should_ask_cleanup={plan['should_ask_cleanup']}, reasoning={plan['reasoning'][:100]}")
            return plan
            
        except Exception as e:
            logger.error(f"Planning failed: {e}, using default plan")
            # Default plan based on heuristics
            query_lower = query.lower()
            is_general = any(phrase in query_lower for phrase in [
                "analyze", "analysis", "all tabs", "what tabs", "summarize", "overview",
                "compare all", "show me all", "list all", "what do i have"
            ])
            
            return {
                "mode": "analysis" if is_general else "single",
                "needs_classification": True,
                "needs_summaries": True,
                "needs_price_extraction": "shop" in query_lower or "price" in query_lower,
                "needs_youtube_transcript": "youtube" in query_lower or any("youtube.com" in t.get("url", "") for t in tabs),
                "should_ask_cleanup": not is_general,  # Only for specific queries
                "needs_followup": False,
                "priority_tabs": [],
                "reasoning": f"Default plan (heuristic): is_general={is_general}"
            }
    
    def _analyze_tab_types(self, tabs: List[Dict[str, Any]]) -> List[str]:
        """Quick analysis of tab types."""
        types = set()
        for tab in tabs:
            url = (tab.get("url", "") or "").lower()
            title = (tab.get("title", "") or "").lower()
            
            if "youtube.com" in url or "youtu.be" in url:
                types.add("youtube")
            elif "google.com" in url and "/search" in url:
                types.add("google_search")
            elif "wikipedia.org" in url:
                types.add("wikipedia")
            elif any(x in url for x in ["amazon", "ebay", "walmart", "shop"]):
                types.add("shopping")
            elif "mail" in url or "gmail" in url:
                types.add("email")
            else:
                types.add("other")
        
        return list(types)

