"""PlannerAgent: Orchestrates all agents using LangGraph."""
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.tab_reader_agent import TabReaderAgent
from agents.tab_classifier_agent import TabClassifierAgent
from agents.tab_summary_agent import TabSummaryAgent
from agents.price_extraction_agent import PriceExtractionAgent
from agents.price_tracking_agent import PriceTrackingAgent
from agents.alert_agent import AlertAgent
from agents.memory_agent import MemoryAgent
from agents.prompt_planning_agent import PromptPlanningAgent
import logging
import uuid

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State passed between agent nodes."""
    query: str
    tabs: List[Dict[str, Any]]
    plan: Dict[str, Any]  # Execution plan from PromptPlanningAgent
    extracted_tabs: List[Dict[str, Any]]
    classified_tabs: List[Dict[str, Any]]
    summaries: Dict[int, str]
    shopping_tabs: List[Dict[str, Any]]
    price_info: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    workspace_summary: Dict[str, Any]
    reply: str
    mode: str
    chosen_tab_id: Optional[int]
    suggested_close_tab_ids: List[int]
    should_ask_cleanup: bool


class PlannerAgent:
    """Orchestrates all agents using LangGraph workflow."""
    
    def __init__(self):
        self.prompt_planner = PromptPlanningAgent()
        self.tab_reader = TabReaderAgent()
        self.tab_classifier = TabClassifierAgent()
        self.tab_summary = TabSummaryAgent()
        self.price_extractor = PriceExtractionAgent()
        self.price_tracker = PriceTrackingAgent()
        self.alert_agent = AlertAgent()
        self.memory_agent = MemoryAgent()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph workflow."""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("plan_query", self._plan_query_node)
        workflow.add_node("read_tabs", self._read_tabs_node)
        workflow.add_node("extract_youtube_transcripts", self._extract_youtube_transcripts_node)
        workflow.add_node("classify_tabs", self._classify_tabs_node)
        workflow.add_node("extract_prices", self._extract_prices_node)
        workflow.add_node("generate_summaries", self._generate_summaries_node)
        workflow.add_node("analyze_workspace", self._analyze_workspace_node)
        workflow.add_node("check_alerts", self._check_alerts_node)
        workflow.add_node("save_memory", self._save_memory_node)
        workflow.add_node("generate_reply", self._generate_reply_node)
        
        workflow.set_entry_point("plan_query")
        workflow.add_edge("plan_query", "read_tabs")
        workflow.add_edge("read_tabs", "extract_youtube_transcripts")
        workflow.add_edge("extract_youtube_transcripts", "classify_tabs")
        workflow.add_edge("classify_tabs", "extract_prices")
        workflow.add_edge("extract_prices", "generate_summaries")
        workflow.add_edge("generate_summaries", "analyze_workspace")
        workflow.add_edge("analyze_workspace", "check_alerts")
        workflow.add_edge("check_alerts", "save_memory")
        workflow.add_edge("save_memory", "generate_reply")
        workflow.add_edge("generate_reply", END)
        
        return workflow.compile()
    
    def _plan_query_node(self, state: AgentState) -> AgentState:
        """Analyze query and create execution plan."""
        query = state.get("query", "")
        tabs = state.get("tabs", [])
        
        logger.info(f"[PLAN] Creating execution plan for query: '{query[:50]}'")
        plan = self.prompt_planner.create_plan(query, tabs)
        state["plan"] = plan
        state["mode"] = plan.get("mode", "analysis")
        state["should_ask_cleanup"] = plan.get("should_ask_cleanup", False)
        
        logger.info(f"[PLAN] Plan created: mode={plan['mode']}, should_ask_cleanup={plan['should_ask_cleanup']}")
        return state
    
    def _extract_youtube_transcripts_node(self, state: AgentState) -> AgentState:
        """Extract YouTube video transcripts if needed."""
        plan = state.get("plan", {})
        extracted = state.get("extracted_tabs", [])
        
        if not plan.get("needs_youtube_transcript", False):
            return state
        
        logger.info("[YOUTUBE] Extracting transcripts for YouTube videos...")
        
        for tab in extracted:
            url = tab.get("url", "")
            if "youtube.com" in url or "youtu.be" in url:
                try:
                    # Extract video ID
                    video_id = None
                    if "youtube.com/watch?v=" in url:
                        video_id = url.split("v=")[1].split("&")[0]
                    elif "youtu.be/" in url:
                        video_id = url.split("youtu.be/")[1].split("?")[0]
                    
                    if video_id:
                        # Try to get transcript from YouTube (requires yt-dlp or similar)
                        # For now, we'll add a note that transcript extraction is needed
                        # In production, you'd use yt-dlp or YouTube Transcript API
                        logger.info(f"[YOUTUBE] Found video ID: {video_id}, transcript extraction would go here")
                        # Add transcript to tab text if available
                        # tab["text"] = f"{tab.get('text', '')}\n\n[YouTube Transcript would be extracted here]"
                except Exception as e:
                    logger.warning(f"[YOUTUBE] Failed to extract transcript for {url}: {e}")
        
        return state
    
    def _read_tabs_node(self, state: AgentState) -> AgentState:
        """Extract content from tabs."""
        tabs = state.get("tabs", [])
        logger.info(f"Reading {len(tabs)} tabs. Titles: {[t.get('title', 'N/A')[:50] for t in tabs]}")
        logger.info(f"Tab IDs: {[t.get('id') for t in tabs]}")
        
        extracted = self.tab_reader.extract_multiple_tabs(tabs)
        logger.info(f"Extracted {len(extracted)} tabs. Extracted IDs: {[t.get('id') for t in extracted]}")
        
        # Ensure ALL tabs are included, even if extraction failed
        extracted_ids = {t.get("id") for t in extracted}
        for tab in tabs:
            tab_id = tab.get("id")
            if tab_id not in extracted_ids:
                logger.warning(f"Tab {tab_id} ({tab.get('title', 'N/A')}) was not extracted, adding with basic info")
                extracted.append({
                    "id": tab_id,
                    "title": tab.get("title", "Untitled"),
                    "url": tab.get("url", ""),
                    "text": tab.get("text", "") or "",
                    "text_length": len(tab.get("text", "") or ""),
                })
        
        logger.info(f"Final extracted tabs count: {len(extracted)} (should match input: {len(tabs)})")
        state["extracted_tabs"] = extracted
        return state
    
    def _classify_tabs_node(self, state: AgentState) -> AgentState:
        """Classify tabs into categories."""
        plan = state.get("plan", {})
        if not plan.get("needs_classification", True):
            logger.info("[CLASSIFY] Skipping classification (not needed per plan)")
            state["classified_tabs"] = state.get("extracted_tabs", [])
            state["duplicates"] = []
            return state
        
        import time
        start = time.time()
        extracted = state.get("extracted_tabs", [])
        query = state.get("query", "").lower()
        logger.info(f"[CLASSIFY] Starting classification of {len(extracted)} tabs...")
        
        # For "analyze my tabs" or general queries, use fast heuristics instead of LLM
        # LLM classification is slow (2-5s per tab) and not needed for general analysis
        use_heuristics = (
            "analyze" in query or 
            "my tabs" in query or 
            len(extracted) > 5  # Use heuristics if more than 5 tabs
        )
        
        if use_heuristics:
            logger.info(f"[CLASSIFY] Using fast heuristic classification (query: '{query[:50]}', tabs: {len(extracted)})")
            classified = []
            for tab in extracted:
                url = (tab.get("url", "") or "").lower()
                title = (tab.get("title", "") or "").lower()
                text = (tab.get("text", "") or "").lower()[:500]
                
                category = "unknown"
                if any(x in url or x in title or x in text for x in ["amazon", "ebay", "walmart", "target", "best buy", "shopify", "product", "buy", "cart", "price", "$"]):
                    category = "shopping"
                elif any(x in url or x in title for x in ["youtube", "netflix", "twitch", "reddit", "tiktok", "instagram"]):
                    category = "entertainment"
                elif any(x in url or x in title for x in ["wikipedia", "stackoverflow", "github", "medium", "edu", "research", "arxiv", "scholar"]):
                    category = "research"
                elif any(x in url or x in title for x in ["google", "docs", "drive", "sheets", "gmail", "outlook", "slack", "notion"]):
                    category = "work"
                elif any(x in url or x in title for x in ["facebook", "twitter", "x.com", "linkedin"]):
                    category = "entertainment"  # Social media
                
                classified.append({
                    **tab,
                    "classification": {"category": category, "confidence": 0.8, "reason": "Heuristic classification"}
                })
        else:
            # Use LLM classification only for specific queries with few tabs
            try:
                logger.info("Using LLM classification (specific query with few tabs)")
                classified = self.tab_classifier.classify_multiple_tabs(extracted)
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}, falling back to heuristics")
                # Fallback to heuristics if LLM fails
                classified = []
                for tab in extracted:
                    url = (tab.get("url", "") or "").lower()
                    title = (tab.get("title", "") or "").lower()
                    text = (tab.get("text", "") or "").lower()[:500]
                    
                    category = "unknown"
                    if any(x in url or x in title or x in text for x in ["amazon", "ebay", "walmart", "target", "best buy", "shopify", "product", "buy", "cart", "price", "$"]):
                        category = "shopping"
                    elif any(x in url or x in title for x in ["youtube", "netflix", "twitch", "reddit", "tiktok", "instagram"]):
                        category = "entertainment"
                    elif any(x in url or x in title for x in ["wikipedia", "stackoverflow", "github", "medium", "edu", "research"]):
                        category = "research"
                    elif any(x in url or x in title for x in ["google", "docs", "drive", "sheets", "gmail"]):
                        category = "work"
                    elif any(x in url or x in title for x in ["facebook", "twitter", "x.com", "linkedin"]):
                        category = "entertainment"  # Social media
                    
                    classified.append({
                        **tab,
                        "classification": {"category": category, "confidence": 0.7, "reason": "Heuristic fallback"}
                    })
        
        duplicates = self.tab_classifier.detect_duplicates(classified)
        elapsed = time.time() - start
        logger.info(f"[CLASSIFY] Classified {len(classified)} tabs, found {len(duplicates)} duplicate groups in {elapsed:.3f}s")
        
        state["classified_tabs"] = classified
        state["duplicates"] = duplicates
        return state
    
    def _extract_prices_node(self, state: AgentState) -> AgentState:
        """Extract prices from shopping tabs."""
        plan = state.get("plan", {})
        if not plan.get("needs_price_extraction", False):
            logger.info("[PRICES] Skipping price extraction (not needed per plan)")
            state["shopping_tabs"] = []
            state["price_info"] = {}
            return state
        
        classified = state.get("classified_tabs", [])
        shopping_tabs = []
        price_info = {}
        
        for tab in classified:
            if tab.get("classification", {}).get("category") == "shopping":
                if self.price_extractor.is_shopping_page(tab):
                    product_info = self.price_extractor.extract_product_info(tab)
                    if product_info:
                        shopping_tabs.append(tab)
                        price_info[str(tab.get("id"))] = product_info
        
        state["shopping_tabs"] = shopping_tabs
        state["price_info"] = price_info
        return state
    
    def _generate_summaries_node(self, state: AgentState) -> AgentState:
        """Generate summaries for relevant tabs."""
        plan = state.get("plan", {})
        if not plan.get("needs_summarization", True):
            logger.info("[SUMMARIES] Skipping summary generation (not needed per plan)")
            state["summaries"] = {}
            return state
        
        query = state.get("query", "")
        classified = state.get("classified_tabs", [])
        summaries = {}
        
        logger.info(f"Generating summaries for {len(classified)} classified tabs")
        logger.info(f"Tab titles: {[t.get('title', 'N/A')[:50] for t in classified[:5]]}")
        
        query_lower = query.lower().strip()
        
        query_lower = query.lower().strip()
        logger.info(f"[SUMMARIES] Query: '{query}', tabs to process: {len(classified)}")
        
        # For "analyze my tabs" - use FAST text extraction (no LLM) to avoid timeouts
        # For specific questions - use LLM summaries (limited to 2-3 tabs max)
        is_analyze_query = "analyze" in query_lower and ("my tabs" in query_lower or "all tabs" in query_lower)
        is_general_query = any(phrase in query_lower for phrase in [
            "what tabs", "show tabs", "list tabs", "summarize all", "all of them"
        ])
        
        if is_analyze_query or is_general_query:
            # Use LLM summaries but optimized for speed (shorter prompts, parallel processing)
            logger.info(f"[SUMMARIES] Using optimized LLM summaries for '{query_lower}'")
            import time
            import concurrent.futures
            start = time.time()
            
            # Process tabs in parallel (max 3 at a time to avoid overwhelming the API)
            def summarize_one_tab(tab):
                tab_id = tab.get("id")
                title = tab.get("title", "Untitled")
                try:
                    # Use optimized LLM summary
                    summary = self.tab_summary.summarize_tab_optimized(tab, query)
                    return (tab_id, summary)
                except Exception as e:
                    logger.warning(f"[SUMMARIES] LLM failed for tab {tab_id}, using fallback: {e}")
                    # Clean fallback - remove HTML/CSS artifacts and create readable summary
                    text = (tab.get("text", "") or "").strip()
                    # Remove CSS/HTML artifacts
                    import re
                    text = re.sub(r'\{[^}]*\}', '', text)  # Remove CSS
                    text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
                    text = re.sub(r'&[a-z]+;', ' ', text, flags=re.IGNORECASE)  # Remove HTML entities
                    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
                    # Remove lines that look like CSS/HTML
                    lines = text.split('.')
                    clean_lines = []
                    for line in lines:
                        line = line.strip()
                        if len(line) > 20 and not re.match(r'^[\.#]?[a-z-]+\s*\{', line, re.IGNORECASE):
                            clean_lines.append(line)
                    
                    if clean_lines:
                        if len(clean_lines) >= 2:
                            preview = clean_lines[0] + ". " + clean_lines[1]
                            if len(clean_lines) > 2 and len(preview) < 200:
                                preview += ". " + clean_lines[2]
                            return (tab_id, preview[:250] + ("..." if len(preview) > 250 else ""))
                        else:
                            return (tab_id, clean_lines[0][:200] + ("..." if len(clean_lines[0]) > 200 else ""))
                    else:
                        category = tab.get("classification", {}).get("category", "unknown")
                        return (tab_id, f"*{category.title()}* - {title}")
            
            # Process in batches of 3 to avoid rate limits
            batch_size = 3
            for i in range(0, len(classified), batch_size):
                batch = classified[i:i+batch_size]
                with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = [executor.submit(summarize_one_tab, tab) for tab in batch]
                    for future in concurrent.futures.as_completed(futures, timeout=15):
                        try:
                            tab_id, summary = future.result()
                            summaries[tab_id] = summary
                        except Exception as e:
                            logger.warning(f"[SUMMARIES] Batch processing failed: {e}")
            
            elapsed = time.time() - start
            logger.info(f"[SUMMARIES] Generated {len(summaries)} LLM summaries in {elapsed:.2f}s")
        else:
            # Specific query: Use LLM for top 2-3 most relevant tabs only
            logger.info(f"[SUMMARIES] Using LLM summaries for specific query (limited to 3 tabs)")
            import time
            start = time.time()
            
            # Limit to max 3 tabs for LLM to avoid timeout
            tabs_to_summarize = classified[:3] if len(classified) > 3 else classified
            
            for i, tab in enumerate(tabs_to_summarize, 1):
                tab_id = tab.get("id")
                title = tab.get("title", "Untitled")
                
                try:
                    logger.info(f"[SUMMARIES] Summarizing tab {i}/{len(tabs_to_summarize)}: {title[:50]}")
                    text = (tab.get("text", "") or "")[:1500]
                    
                    if len(text) < 50:
                        category = tab.get("classification", {}).get("category", "unknown")
                        summaries[tab_id] = f"*{category.title()}* - {title}"
                        continue
                    
                    # Try LLM with short timeout
                    try:
                        summary = self.tab_summary.summarize_tab_optimized(tab, query)
                        summaries[tab_id] = summary
                        logger.info(f"[SUMMARIES] ✓ Summary generated for tab {tab_id}")
                    except Exception as e:
                        logger.warning(f"[SUMMARIES] LLM failed for tab {tab_id}, using fallback: {e}")
                        # Fast fallback
                        text_clean = (tab.get("text", "") or "").strip()
                        if text_clean:
                            sentences = [s.strip() for s in text_clean.split('.') if s.strip() and len(s.strip()) > 20]
                            if sentences:
                                preview = sentences[0][:200]
                                summaries[tab_id] = preview + ("..." if len(sentences[0]) > 200 else "")
                            else:
                                summaries[tab_id] = text_clean[:200] + "..."
                        else:
                            category = tab.get("classification", {}).get("category", "unknown")
                            summaries[tab_id] = f"*{category.title()}* - {title}"
                except Exception as e:
                    logger.warning(f"[SUMMARIES] Failed for tab {tab_id}: {e}")
                    category = tab.get("classification", {}).get("category", "unknown")
                    summaries[tab_id] = f"*{category.title()}* - {title}"
            
            # For remaining tabs, use fast extraction
            for tab in classified[len(tabs_to_summarize):]:
                tab_id = tab.get("id")
                title = tab.get("title", "Untitled")
                text = (tab.get("text", "") or "").strip()
                if text:
                    sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                    if sentences:
                        summaries[tab_id] = sentences[0][:150] + "..."
                    else:
                        summaries[tab_id] = text[:150] + "..."
                else:
                    category = tab.get("classification", {}).get("category", "unknown")
                    summaries[tab_id] = f"*{category.title()}* - {title}"
            
            elapsed = time.time() - start
            logger.info(f"[SUMMARIES] Generated {len(summaries)} summaries in {elapsed:.2f}s")
        
        elapsed = time.time() - start
        logger.info(f"[SUMMARIES] Generated {len(summaries)} summaries in {elapsed:.2f}s ({elapsed/len(classified):.2f}s per tab)")
        
        # Ensure ALL tabs have summaries (fallback for any that failed)
        for tab in classified:
            tab_id = tab.get("id")
            if tab_id not in summaries:
                logger.warning(f"[SUMMARIES] Tab {tab_id} missing summary, creating fallback")
                title = tab.get("title", "Untitled")
                category = tab.get("classification", {}).get("category", "unknown")
                text = (tab.get("text", "") or "").strip()
                if text:
                    sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                    preview = sentences[0][:150] if sentences else text[:150]
                    summaries[tab_id] = f"{preview}..."
                else:
                    summaries[tab_id] = f"*{category.title()}* - {title}"
        
        logger.info(f"Generated {len(summaries)} summaries for {len(classified)} tabs")
        state["summaries"] = summaries
        return state
    
    def _analyze_workspace_node(self, state: AgentState) -> AgentState:
        """Analyze workspace and provide clarity summary."""
        classified = state.get("classified_tabs", [])
        duplicates = state.get("duplicates", [])
        
        categories = {}
        for tab in classified:
            cat = tab.get("classification", {}).get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        
        duplicate_count = sum(len(group) - 1 for group in duplicates)
        
        workspace_summary = {
            "total_tabs": len(classified),
            "categories": categories,
            "duplicate_groups": len(duplicates),
            "duplicate_count": duplicate_count,
            "recommended_closures": duplicate_count,
            "shopping_tabs": len(state.get("shopping_tabs", [])),
        }
        
        state["workspace_summary"] = workspace_summary
        return state
    
    def _check_alerts_node(self, state: AgentState) -> AgentState:
        """Check for price alerts."""
        alerts = []
        price_info = state.get("price_info", {})
        
        for tab_id_str, info in price_info.items():
            # Check if product is in watchlist
            url = info.get("url")
            if url:
                # In real implementation, check watchlist and trigger alerts
                pass
        
        state["alerts"] = alerts
        return state
    
    def _save_memory_node(self, state: AgentState) -> AgentState:
        """Save session to memory."""
        session_id = str(uuid.uuid4())
        tabs_data = state.get("classified_tabs", [])
        categories = state.get("workspace_summary", {}).get("categories", {})
        
        self.memory_agent.save_session(session_id, tabs_data, categories)
        state["session_id"] = session_id
        return state
    
    def _generate_reply_node(self, state: AgentState) -> AgentState:
        """Generate final reply based on query mode and plan."""
        plan = state.get("plan", {})
        query = state.get("query", "").lower()
        classified = state.get("classified_tabs", [])
        summaries = state.get("summaries", {})
        workspace = state.get("workspace_summary", {})
        duplicates = state.get("duplicates", [])
        
        # Use plan's mode and should_ask_cleanup
        mode = plan.get("mode", "analysis")
        should_ask_cleanup = plan.get("should_ask_cleanup", False)
        
        if mode == "cleanup" or "close" in query or "cleanup" in query or "remove" in query:
            state["mode"] = "cleanup"
            reply, chosen_id, close_ids = self._generate_cleanup_reply(classified, workspace, duplicates)
            state["reply"] = reply
            state["chosen_tab_id"] = chosen_id
            state["suggested_close_tab_ids"] = close_ids
            state["should_ask_cleanup"] = False  # Already in cleanup mode
        elif mode == "multi" or "compare" in query or "versus" in query or "vs" in query:
            state["mode"] = "multi"
            reply, chosen_id = self._generate_comparison_reply(classified, summaries)
            state["reply"] = reply
            state["chosen_tab_id"] = chosen_id
            state["should_ask_cleanup"] = False  # Don't ask for comparisons
        elif mode == "analysis" or "analyze" in query or ("all" in query and "tab" in query):
            state["mode"] = "analysis"
            reply, chosen_id = self._generate_analysis_reply(classified, summaries, query)
            state["reply"] = reply
            state["chosen_tab_id"] = chosen_id
            state["should_ask_cleanup"] = False  # Don't ask for general "analyze all" queries
        else:  # mode == "single" or specific question
            state["mode"] = "single"
            # Check if query is about a specific tab or all tabs
            is_about_all = any(phrase in query.lower() for phrase in [
                "all tabs", "every tab", "each tab", "all of them", 
                "what tabs", "show tabs", "list tabs", "summarize all"
            ])
            
            if is_about_all:
                # User wants info about all tabs, use analysis mode
                reply, chosen_id = self._generate_analysis_reply(classified, summaries, query)
            else:
                # Specific question - find most relevant tab and answer
                reply, chosen_id = self._generate_single_reply(classified, summaries, query)
            
            state["reply"] = reply
            state["chosen_tab_id"] = chosen_id
            # Only ask cleanup for specific queries where a single tab was found
            is_general_query = any(phrase in query.lower() for phrase in ["analyze", "all tabs", "what tabs", "show tabs", "list tabs"])
            state["should_ask_cleanup"] = chosen_id is not None and not is_general_query
        
        return state
    
    def _generate_comparison_reply(self, tabs: List[Dict[str, Any]], summaries: Dict[int, str]) -> tuple[str, Optional[int]]:
        """Generate comparison reply."""
        relevant = [t for t in tabs if t.get("id") in summaries][:6]
        if not relevant:
            return ("No relevant tabs found for comparison.", None)
        
        reply = "## Comparison\n\n"
        for tab in relevant:
            summary = summaries.get(tab.get("id"), "No summary available.")
            reply += f"### {tab.get('title', 'Untitled')}\n{summary}\n\n"
        
        chosen_id = relevant[0].get("id") if relevant else None
        return (reply, chosen_id)
    
    def _generate_cleanup_reply(self, tabs: List[Dict[str, Any]], workspace: Dict[str, Any], duplicates: List[List[int]]) -> tuple[str, Optional[int], List[int]]:
        """Generate cleanup recommendation."""
        duplicate_count = workspace.get("duplicate_count", 0)
        total = workspace.get("total_tabs", 0)
        
        close_ids = []
        for group in duplicates:
            # Convert array indices to actual tab IDs (keep first, close rest)
            for idx in group[1:]:
                if 0 <= idx < len(tabs):
                    tab_id = tabs[idx].get("id")
                    if tab_id is not None:
                        close_ids.append(tab_id)
        
        reply = f"## Workspace Analysis\n\n"
        reply += f"- **Total tabs**: {total}\n"
        reply += f"- **Duplicate tabs**: {duplicate_count}\n"
        reply += f"- **Categories**: {workspace.get('categories', {})}\n\n"
        reply += f"Recommended: Close {duplicate_count} duplicate tabs."
        
        chosen_id = tabs[0].get("id") if tabs else None
        return (reply, chosen_id, close_ids)
    
    def _generate_analysis_reply(self, tabs: List[Dict[str, Any]], summaries: Dict[int, str], query: str) -> tuple[str, Optional[int]]:
        """Generate analysis reply showing all tabs."""
        if not tabs:
            return ("No tabs available.", None)
        
        query_lower = query.lower()
        matching_tabs = tabs
        
        # Filter by keyword if mentioned
        if "google" in query_lower:
            matching_tabs = [t for t in tabs if "google" in (t.get("url", "") or "").lower() or "google" in (t.get("title", "") or "").lower()]
            if not matching_tabs:
                matching_tabs = tabs  # Fallback to all tabs
        
        reply = f"## 📊 Analysis of {len(matching_tabs)} Tab(s)\n\n"
        
        # Ensure ALL tabs are shown, even if they don't have summaries
        for i, tab in enumerate(matching_tabs, 1):
            title = tab.get("title", "Untitled")
            tab_id = tab.get("id")
            summary = summaries.get(tab_id)
            
            reply += f"### {i}. {title}\n\n"
            
            if summary:
                # Clean up summary - remove redundant title/URL if already shown
                clean_summary = summary.strip()
                # Remove title if it's the same
                if title in clean_summary:
                    clean_summary = clean_summary.replace(f"**{title}**", "").strip()
                # Remove URL lines
                lines = clean_summary.split('\n')
                clean_summary = '\n'.join([l for l in lines if not (l.strip().startswith('URL:') or l.strip().startswith('**URL:**'))])
                # Remove category mentions and labels
                category_patterns = [
                    r'\*\*Main Topic:\*\*', r'Main Topic:', r'\*\*Key Information:\*\*', r'Key Information:',
                    r'\*\*Important Details:\*\*', r'Important Details:', r'\*\*Summary\*\*', r'Summary:',
                    r'Research', r'Shopping', r'Entertainment', r'Work', r'Distraction', r'Unknown'
                ]
                for pattern in category_patterns:
                    clean_summary = clean_summary.replace(pattern, "").replace(pattern.lower(), "")
                # Remove empty lines and clean up
                clean_summary = '\n'.join([l.strip() for l in clean_summary.split('\n') if l.strip()])
                # Clean up multiple newlines and bullet points that are just labels
                while '\n\n\n' in clean_summary:
                    clean_summary = clean_summary.replace('\n\n\n', '\n\n')
                # Remove standalone bullet points that are just category names
                lines = clean_summary.split('\n')
                filtered_lines = []
                for line in lines:
                    line_lower = line.lower().strip()
                    if not any(cat in line_lower for cat in ['research', 'shopping', 'entertainment', 'work', 'distraction', 'unknown', 'main topic', 'key information', 'important details']):
                        filtered_lines.append(line)
                clean_summary = '\n'.join(filtered_lines).strip()
                reply += f"{clean_summary}\n\n"
            else:
                text = (tab.get("text", "") or "").strip()
                # Get first meaningful sentence
                sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                preview = sentences[0][:200] if sentences else "No content available"
                reply += f"{preview}...\n\n"
        
        chosen_id = matching_tabs[0].get("id") if matching_tabs else None
        return (reply, chosen_id)
    
    def _generate_single_reply(self, tabs: List[Dict[str, Any]], summaries: Dict[int, str], query: str) -> tuple[str, Optional[int]]:
        """Generate single tab reply - ranks tabs by query relevance."""
        if not tabs:
            return ("No tabs available.", None)
        
        from utils.text_utils import make_tab_tokens, overlap_score
        
        # Tokenize query
        query_tokens = make_tab_tokens("", "", query, max_chars=500)
        
        # Rank tabs by relevance to query
        scored_tabs = []
        for tab in tabs:
            title = tab.get("title", "")
            url = tab.get("url", "")
            text = (tab.get("text", "") or "")[:2000]  # Use text for better matching
            
            # Create tokens from tab
            tab_tokens = make_tab_tokens(title, url, text, max_chars=2000)
            
            # Calculate relevance score
            score = overlap_score(query_tokens, tab_tokens)
            
            # Boost score if query keywords appear in title (more important)
            title_lower = title.lower()
            query_lower = query.lower()
            query_words = query_lower.split()
            title_matches = sum(1 for word in query_words if len(word) > 3 and word in title_lower)
            if title_matches > 0:
                score += title_matches * 0.3  # Boost for title matches
            
            scored_tabs.append((score, tab))
        
        # Sort by score (highest first)
        scored_tabs.sort(key=lambda x: x[0], reverse=True)
        
        # Get the most relevant tab
        if not scored_tabs or scored_tabs[0][0] < 0.01:
            # No good match, use first tab
            top_tab = tabs[0]
            logger.warning(f"No good tab match for query: {query[:50]}")
        else:
            top_tab = scored_tabs[0][1]
            logger.info(f"Selected tab '{top_tab.get('title', 'N/A')[:50]}' with score {scored_tabs[0][0]:.3f} for query: {query[:50]}")
        
        # Answer the specific question from the tab content using LLM
        title = top_tab.get("title", "Untitled Tab")
        url = top_tab.get("url", "")
        # Use MORE content for question answering (up to 8000 chars to get deeper info)
        text = (top_tab.get("text", "") or "")[:8000]
        
        # Always use LLM to answer the query directly (not just a summary)
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            
            # Check if this is a question or specific query
            is_question = "?" in query or any(qword in query.lower() for qword in ["what", "when", "where", "who", "which", "how", "why", "first", "best", "compare"])
            
            if is_question:
                # This is a specific question - answer it directly with thorough analysis
                is_chronological = any(word in query.lower() for word in ["first", "earliest", "oldest", "beginning", "start", "debut"])
                
                if is_chronological:
                    system_prompt = """You are TabSensei, an assistant that answers questions based ONLY on the provided tab content.

CRITICAL: For questions about "first", "earliest", "oldest", "beginning", or "debut" - you MUST find the CHRONOLOGICALLY EARLIEST item.

Instructions:
1. Search through ALL the content systematically - do not stop at the first mention
2. Look for dates, years, chronological lists, filmography sections, career timelines
3. Find ALL items that could answer the question, then identify which one is EARLIEST by date/year
4. If you see a list or filmography, check the ENTIRE list, not just the first few items
5. Compare dates carefully - the answer must be the item with the EARLIEST date
6. If the content mentions "first" but also shows an earlier date elsewhere, use the EARLIEST date
7. Be precise - include the exact name/title and year/date in your answer

Answer the user's question directly and accurately.
- State the exact name/title and the year/date
- If you're uncertain, say so
- Keep your answer under 200 words"""
                else:
                    system_prompt = """You are TabSensei, an assistant that answers questions based ONLY on the provided tab content.

IMPORTANT: You must thoroughly analyze the ENTIRE tab content to find the answer. Do not rely on partial information.

For factual questions:
- Search through ALL the content carefully
- Look for specific facts, dates, names, or details
- Verify your answer by checking if it's explicitly stated in the content
- If you find conflicting information, mention both and indicate which seems more reliable
- If the answer is not clearly in the content, say "The information is not available in this tab"

Answer the user's question directly and accurately using information from the tab.
- Be specific and factual
- Cite specific details from the content when possible
- If uncertain, indicate that
- Keep your answer under 200 words"""
            else:
                # General query - provide relevant information
                system_prompt = """You are TabSensei, an assistant that provides information based ONLY on the provided tab content.

Provide relevant information from the tab that addresses the user's query.
- Be concise and informative
- Focus on what's relevant to the query
- Keep it under 150 words"""
            
            user_prompt = f"""Tab Title: {title}
Tab URL: {url}

Tab Content (full text):
{text[:6000]}

User Query: {query}

{'Answer the question accurately by thoroughly analyzing the content above. Look for specific facts, dates, and chronological information.' if is_question else 'Provide relevant information based on the tab content above.'}"""
            
            try:
                import concurrent.futures
                import time
                
                # Add timeout protection for question answering
                start_time = time.time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self.tab_summary.llm.invoke,
                        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    )
                    try:
                        llm_response = future.result(timeout=12)  # 12 second timeout for question answering
                        elapsed = time.time() - start_time
                        logger.info(f"Question answering took {elapsed:.2f}s")
                    except concurrent.futures.TimeoutError:
                        elapsed = time.time() - start_time
                        logger.warning(f"Question answering timed out after {elapsed:.2f}s")
                        # Fallback to summary
                        summary = summaries.get(top_tab.get("id"), "")
                        if summary:
                            return (f"Based on the tab '{title}':\n\n{summary}", top_tab.get("id"))
                        else:
                            return (f"Information about '{title}' is available, but I couldn't process it in time. Please try again.", top_tab.get("id"))
                answer = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
                
                # For questions about "first", "earliest", etc., do a quick verification
                # Only if the answer doesn't already contain a clear date or seems incomplete
                if is_question and any(word in query.lower() for word in ["first", "earliest", "oldest", "beginning", "start"]):
                    import re
                    # Check if answer already has a year/date
                    answer_has_year = bool(re.search(r'\b(19|20)\d{2}\b', answer))
                    
                    # Only do verification if:
                    # 1. Answer doesn't have a clear year, OR
                    # 2. Answer seems too short/vague
                    if not answer_has_year or len(answer) < 50:
                        # Quick check: extract all years from text and find the earliest
                        years_in_text = [int(m.group(0)) for m in re.finditer(r'\b(19|20)\d{2}\b', text) if m.group(0).isdigit()]
                        
                        if years_in_text:
                            earliest_year = min(years_in_text)
                            # Check if answer mentions this earliest year
                            if str(earliest_year) not in answer:
                                # Do a quick LLM verification (but make it faster)
                                try:
                                    chronological_prompt = f"""The user asked: "{query}"

Previous answer: {answer}

Tab Content excerpt (focus on dates/years):
{text[:2000]}

Find the EARLIEST date/year that answers the question. If the previous answer is wrong, provide the correct one with the earliest date."""
                                    
                                    chrono_response = self.tab_summary.llm.invoke([
                                        SystemMessage(content="You are a fact-checker. Find the EARLIEST item that answers the question. Be brief."),
                                        HumanMessage(content=chronological_prompt)
                                    ])
                                    chrono_answer = chrono_response.content if hasattr(chrono_response, "content") else str(chrono_response)
                                    
                                    # If the chronological answer mentions an earlier year, use it
                                    chrono_years = [int(m.group(0)) for m in re.finditer(r'\b(19|20)\d{2}\b', chrono_answer) if m.group(0).isdigit()]
                                    if chrono_years and min(chrono_years) < earliest_year:
                                        logger.info(f"Verification found earlier date, updating answer")
                                        answer = chrono_answer
                                    elif chrono_answer != answer and len(chrono_answer) > 30:
                                        # If answer is substantially different and longer, it might be more complete
                                        answer = chrono_answer
                                except Exception as e:
                                    logger.warning(f"Chronological verification failed: {e}")
                                    # Continue with original answer
            except Exception as e:
                logger.error(f"Failed to generate answer: {e}")
                # Fallback to summary
                answer = self.tab_summary.summarize_tab(top_tab, query=query)
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            # Fallback to basic summary
            answer = summaries.get(top_tab.get("id"), f"Content from: {title}")
        
        reply = f"{answer}"
        logger.info(f"Generated reply for tab: {top_tab.get('title', 'N/A')[:50]}")
        return (reply, top_tab.get("id"))
    
    def _fast_answer_question(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fast path for specific questions - skips full pipeline."""
        from utils.text_utils import make_tab_tokens, overlap_score
        from langchain_core.messages import SystemMessage, HumanMessage
        import concurrent.futures
        import time
        
        logger.info(f"[FAST] Fast path for question: '{query[:50]}'")
        
        # Find most relevant tab quickly
        query_tokens = make_tab_tokens("", "", query, max_chars=500)
        scored_tabs = []
        
        for tab in tabs:
            title = tab.get("title", "")
            url = tab.get("url", "")
            text = (tab.get("text", "") or "")[:3000]  # Use less text for speed
            
            tab_tokens = make_tab_tokens(title, url, text, max_chars=2000)
            score = overlap_score(query_tokens, tab_tokens)
            
            # Boost for title matches
            title_lower = title.lower()
            query_lower = query.lower()
            query_words = query_lower.split()
            title_matches = sum(1 for word in query_words if len(word) > 3 and word in title_lower)
            if title_matches > 0:
                score += title_matches * 0.3
            
            scored_tabs.append((score, tab))
        
        scored_tabs.sort(key=lambda x: x[0], reverse=True)
        
        if not scored_tabs or scored_tabs[0][0] < 0.01:
            top_tab = tabs[0] if tabs else None
        else:
            top_tab = scored_tabs[0][1]
        
        if not top_tab:
            return {
                "reply": "No tabs available to answer your question.",
                "mode": "single",
                "chosen_tab_id": None,
            }
        
        # Answer question directly with LLM (fast, no summarization)
        title = top_tab.get("title", "Untitled")
        url = top_tab.get("url", "")
        text = (top_tab.get("text", "") or "")[:4000]  # Reduced for speed (was 6000)
        
        system_prompt = """You are TabSensei. Answer the user's question based ONLY on the provided tab content.

- Be direct and factual
- If the answer is in the content, provide it
- If not, say "The information is not available in this tab"
- Keep your answer concise (under 100 words)"""
        
        user_prompt = f"""Tab: {title}
URL: {url}

Content:
{text[:3000]}

Question: {query}

Answer:"""
        
        try:
            start_time = time.time()
            max_wait_time = 12  # Maximum 12 seconds for LLM call
            
            # Use ThreadPoolExecutor with timeout as a safety mechanism
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.tab_summary.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                try:
                    response = future.result(timeout=max_wait_time)
                    elapsed = time.time() - start_time
                    logger.info(f"[FAST] Question answered in {elapsed:.2f}s")
                    
                    answer = response.content if hasattr(response, "content") else str(response)
                    
                    # If answer is too short or seems like an error, use fallback
                    if not answer or len(answer) < 10:
                        raise ValueError("LLM returned empty or invalid answer")
                        
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    logger.warning(f"[FAST] LLM call timed out after {elapsed:.2f}s")
                    # Fall through to fallback instead of raising
                    raise TimeoutError(f"LLM call exceeded {max_wait_time} second timeout")
        except (TimeoutError, Exception) as llm_error:
            elapsed = time.time() - start_time if 'start_time' in locals() else 0
            logger.warning(f"[FAST] LLM call failed after {elapsed:.2f}s: {llm_error}")
            # Fast fallback - extract answer from text directly
            import re
            query_lower = query.lower()
            if "birthdate" in query_lower or "birthday" in query_lower or "born" in query_lower:
                # Look for dates in text
                dates = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', text, re.IGNORECASE)
                if dates:
                    answer = f"Based on the tab '{title}': {dates[0]}"
                else:
                    # Look for year patterns
                    years = re.findall(r'\b(19|20)\d{2}\b', text)
                    if years:
                        answer = f"Based on the tab '{title}': The information appears to be in the content, but I couldn't extract the exact date. Please check the tab directly."
                    else:
                        answer = f"Based on the tab '{title}': The birthdate information is not clearly available in this tab's content."
            else:
                # Generic fallback
                sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                if sentences:
                    answer = f"Based on '{title}': {sentences[0][:150]}..."
                else:
                    answer = f"Based on '{title}': The information might be available, but I couldn't process it. Please check the tab directly."
        except Exception as e:
            logger.error(f"[FAST] Error answering question: {e}")
            answer = f"Error processing your question. Please try again or check the tab directly."
        
        return {
            "reply": answer,
            "mode": "single",
            "chosen_tab_id": top_tab.get("id"),
            "suggested_close_tab_ids": [],
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
    
    def process(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process query through agent workflow."""
        import time
        start_time = time.time()
        
        logger.info(f"PlannerAgent.process() called with query: '{query}' and {len(tabs)} tabs")
        
        # FAST PATH: For specific questions, skip full pipeline
        query_lower = query.lower().strip()
        is_specific_question = (
            "?" in query or
            any(qword in query_lower for qword in [
                "what", "when", "where", "who", "which", "how", "why",
                "first", "last", "birthdate", "birthday", "born", "age",
                "best", "worst", "compare", "difference", "tell me about"
            ]) and
            not any(phrase in query_lower for phrase in [
                "analyze", "all tabs", "my tabs", "what tabs", "show tabs", "list tabs", "summarize all"
            ])
        )
        
        if is_specific_question and len(tabs) <= 10:
            logger.info(f"[FAST] Using fast path for specific question (skipping full pipeline)")
            try:
                result = self._fast_answer_question(query, tabs)
                elapsed = time.time() - start_time
                logger.info(f"[FAST] Fast path completed in {elapsed:.2f}s")
                return result
            except Exception as e:
                logger.error(f"[FAST] Fast path failed: {e}")
                # Return error immediately instead of falling through to slow pipeline
                return {
                    "reply": f"I encountered an error while processing your question. Please try again or rephrase your question.",
                    "mode": "single",
                    "chosen_tab_id": None,
                    "suggested_close_tab_ids": [],
                    "workspace_summary": {},
                    "alerts": [],
                    "price_info": {},
                    "should_ask_cleanup": False,
                }
        
        # FULL PIPELINE: For general queries or if fast path fails
        initial_state: AgentState = {
            "query": query,
            "tabs": tabs,
            "plan": {},  # Will be set by plan_query_node
            "extracted_tabs": [],
            "classified_tabs": [],
            "summaries": {},
            "shopping_tabs": [],
            "price_info": {},
            "alerts": [],
            "should_ask_cleanup": False,
            "workspace_summary": {},
            "reply": "",
            "mode": "single",
            "chosen_tab_id": None,
            "suggested_close_tab_ids": [],
        }
        
        try:
            logger.info(f"Starting graph execution with {len(tabs)} tabs")
            final_state = self.graph.invoke(initial_state)
            elapsed = time.time() - start_time
            logger.info(f"Graph execution complete in {elapsed:.2f}s, reply length: {len(final_state.get('reply', ''))}")
            
            return {
                "reply": final_state.get("reply", ""),
                "mode": final_state.get("mode", "single"),
                "chosen_tab_id": final_state.get("chosen_tab_id"),
                "suggested_close_tab_ids": final_state.get("suggested_close_tab_ids", []),
                "workspace_summary": final_state.get("workspace_summary", {}),
                "alerts": final_state.get("alerts", []),
                "price_info": final_state.get("price_info", {}),
                "should_ask_cleanup": final_state.get("should_ask_cleanup", False),
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"PlannerAgent failed after {elapsed:.2f}s: {e}")
            return {
                "reply": f"Error: {str(e)}",
                "mode": "single",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }

