"""SimpleAgent: Direct, fast query processing without complex pipeline."""
from typing import Dict, Any, List, Optional
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
import logging
import time
import re
import concurrent.futures

logger = logging.getLogger(__name__)


class SimpleAgent:
    """Simple, fast agent that processes queries directly."""
    
    def __init__(self):
        self.llm = get_llm()
    
    def process(self, query: str, tabs: List[Dict[str, Any]], chat_history: List[Dict[str, str]] = []) -> Dict[str, Any]:
        """Process query - simple and fast."""
        start_time = time.time()
        query_lower = query.lower().strip()
        
        logger.info(f"[SIMPLE] Processing query: '{query[:50]}' with {len(tabs)} tabs")
        
        # Check for "how many tabs" queries first
        if any(phrase in query_lower for phrase in ["how many tabs", "how many tab", "count tabs", "number of tabs"]):
            return self._count_tabs(query, tabs, start_time)
        
        # Determine query type
        is_specific_question = (
            "?" in query or
            any(word in query_lower for word in [
                "what", "when", "where", "who", "which", "how", "why",
                "birthdate", "birthday", "born", "age", "first", "last"
            ]) and
            not any(phrase in query_lower for phrase in [
                "analyze", "all tabs", "my tabs", "what tabs", "show tabs", "list tabs", "how many tabs"
            ])
        )
        
        # If user explicitly asks to check all tabs or analyze
        check_all_tabs = any(phrase in query_lower for phrase in ["all tabs", "analyze", "summary", "summarize", "compare", "search all"])
        
        if check_all_tabs:
            return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
            
        if is_specific_question:
            # Try to find relevant tab first
            relevant_tab = self._find_relevant_tab(query, tabs)
            if relevant_tab:
                return self._answer_question(query, relevant_tab, tabs, start_time, chat_history)
            else:
                # Fallback to checking all tabs if no specific relevant tab found
                return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
        
        # Default: analyze tabs generally
        return self._analyze_tabs(query, tabs, start_time)
    
    def _count_tabs(self, query: str, tabs: List[Dict[str, Any]], start_time: float) -> Dict[str, Any]:
        """Count and list all open tabs - let LLM format the response naturally."""
        logger.info(f"[SIMPLE] Counting {len(tabs)} tabs")
        
        if not tabs:
            # Let LLM handle even the empty case
            system_prompt = "You are TabSensei, an assistant that helps users manage their browser tabs. Answer naturally and conversationally."
            user_prompt = "The user asked how many tabs are open. There are currently no tabs open."
            
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self.llm.invoke,
                        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    )
                    response = future.result(timeout=8)
                    reply = response.content if hasattr(response, "content") else str(response)
            except:
                reply = "No tabs are currently open."
            
            return {
                "reply": reply,
                "mode": "analysis",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        
        # Build data for LLM - just provide the information, let LLM format it
        tab_list = []
        for i, tab in enumerate(tabs, 1):
            title = tab.get("title", "Untitled")
            url = tab.get("url", "")
            is_google = "google.com" in url.lower() and "/search" in url.lower()
            tab_list.append({
                "number": i,
                "title": title,
                "url": url,
                "is_google_search": is_google
            })
        
        # Let LLM generate the response naturally
        system_prompt = (
            "You are TabSensei, an assistant that helps users manage their browser tabs.\n"
            "Answer the user's question about their tabs naturally and conversationally.\n"
            "Format your response in a clear, user-friendly way using markdown. Be concise but informative."
        )
        
        user_prompt = (
            f"The user asked: \"{query}\"\n\n"
            "Here are all the open tabs:\n"
            f"{chr(10).join([f'{t['number']}. {t['title']} ({'Google Search' if t['is_google_search'] else 'Regular tab'})' for t in tab_list])}\n\n"
            f"Total number of tabs: {len(tabs)}\n\n"
            "Please answer the user's question naturally. Include the count and list all tabs in a clear format."
        )
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                response = future.result(timeout=10)
                reply = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning(f"[SIMPLE] LLM failed for tab count, using fallback: {e}")
            # Fallback: simple format
            reply = f"You have {len(tabs)} tabs open:\n\n"
            for t in tab_list:
                reply += f"{t['number']}. {t['title']}\n"
        
        total_elapsed = time.time() - start_time
        logger.info(f"[SIMPLE] Tab count completed in {total_elapsed:.2f}s")
        
        return {
            "reply": reply,
            "mode": "analysis",
            "chosen_tab_id": tabs[0].get("id") if tabs else None,
            "suggested_close_tab_ids": [],
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
    
    def _find_relevant_tab(self, query: str, tabs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find most relevant tab for a question - improved matching."""
        query_lower = query.lower()
        query_words = set(word for word in query_lower.split() if len(word) > 2)
        
        # Extract key entity from query (e.g., "johnny depp" from "what is johnny depp's birthdate")
        # Look for proper nouns (capitalized words) or common name patterns
        import re as regex_module
        name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        names = regex_module.findall(name_pattern, query)
        key_entities = [name.lower() for name in names if len(name.split()) <= 3]  # Max 3 words for names
        
        best_tab = None
        best_score = 0
        
        for tab in tabs:
            title = (tab.get("title", "") or "").lower()
            url = (tab.get("url", "") or "").lower()
            text_preview = ((tab.get("text", "") or "")[:500]).lower()  # Preview of text content
            
            score = 0
            
            # Strong boost for key entity matches in title
            for entity in key_entities:
                if entity in title:
                    score += 10  # Strong match
                elif any(word in title for word in entity.split()):
                    score += 5  # Partial match
            
            # Score based on title word matches
            title_words = set(word for word in title.split() if len(word) > 2)
            matches = len(query_words & title_words)
            score += matches * 3  # Boost for matching words
            
            # Boost if query words appear in URL
            url_matches = sum(1 for word in query_words if word in url)
            score += url_matches * 2

            # Strong boost if query words match the domain name (e.g. "neetcode" in "neetcode.io")
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if any(word in domain for word in query_words):
                    score += 10  # Strong boost for domain match
            except:
                pass
            
            # Small boost if query words appear in text preview
            text_matches = sum(1 for word in query_words if word in text_preview)
            score += text_matches * 1
            
            # Boost Google Search tabs for factual queries
            is_google_search = "google.com" in url.lower() and "/search" in url.lower()
            is_factual = any(w in query_lower for w in ["who", "when", "where", "what", "birthdate", "born", "age", "height"])
            if is_google_search and is_factual:
                score += 2  # Slight boost for Google Search on factual queries (was 15, which caused irrelevant matches)
            
            if score > best_score:
                best_score = score
                best_tab = tab
        
        # Log which tab was chosen for debugging
        if best_tab:
            logger.info(f"[SIMPLE] Selected tab: '{best_tab.get('title', 'N/A')}' (score: {best_score})")
        
        # If no good match, return None (let caller handle fallback)
        return best_tab
    
    def _answer_question_all_tabs(self, query: str, tabs: List[Dict[str, Any]], start_time: float, chat_history: List[Dict[str, str]] = []) -> Dict[str, Any]:
        """Answer a specific question by checking ALL tabs."""
        logger.info(f"[SIMPLE] Answering specific question across {len(tabs)} tabs")
        
        # Get current date for relative time calculations
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        if not tabs:
            return {
                "reply": "No tabs available to answer your question.",
                "mode": "single",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        
        # Collect content from all tabs
        tab_contents = []
        for tab in tabs:
            title = tab.get("title", "Untitled")
            url = tab.get("url", "")
            text = (tab.get("text", "") or "").strip()
            
            # Clean text
            text = re.sub(r'[{][^}]*[}]', '', text)
            text = re.sub(r'<[^>]+>', '', text)
            text = " ".join(text.split())
            
            # Google search pages might have less content but still contain useful info
            is_google_search = "google.com" in url.lower() and "/search" in url.lower()
            min_content_length = 10 if is_google_search else 50
            
            if text and len(text) >= min_content_length:
                # Use up to 4000 chars per tab to fit multiple tabs
                tab_contents.append({
                    "title": title,
                    "url": url,
                    "text": text[:4000],
                    "id": tab.get("id")
                })
        
        if not tab_contents:
            return {
                "reply": "None of the tabs have enough content to answer your question.",
                "mode": "single",
                "chosen_tab_id": tabs[0].get("id") if tabs else None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        
        # Find most relevant tab for switching
        relevant_tab = self._find_relevant_tab(query, tabs)
        chosen_tab_id = relevant_tab.get("id") if relevant_tab else tab_contents[0]["id"]
        
        # Build combined content prompt
        query_lower = query.lower()
        is_chronological = any(word in query_lower for word in ["first", "earliest", "oldest", "beginning", "start", "debut", "birthdate", "birthday", "born"])
        
        if is_chronological:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content from multiple tabs.\n"
                f"Current Date: {current_date}\n\n"
                "CRITICAL for chronological questions (first, earliest, oldest, birthdate, etc.):\n"
                "1. Search through ALL tabs systematically - do not stop at the first mention\n"
                "2. Look for dates, years, chronological lists, timelines, filmography sections in EACH tab\n"
                "3. Find ALL items that could answer the question across ALL tabs, then identify which one is EARLIEST by date/year\n"
                "4. If you see lists or filmographies in any tab, check the ENTIRE list, not just the first few items\n"
                "5. Compare dates carefully across ALL tabs - the answer must be the item with the EARLIEST date\n"
                "6. If one tab mentions 'first' but another tab shows an earlier date, use the EARLIEST date\n"
                "7. Be precise - include the exact name/title, year/date, and which tab it came from\n\n"
                "Answer the user's question directly and accurately.\n"
                "- State the exact name/title and the year/date\n"
                "- Mention which tab(s) contained this information\n"
                "- If you're uncertain, say so\n"
                "- Keep your answer concise but complete\n"
                "- DO NOT list tabs that did not contain the information. Only mention the source of the answer.\n"
                "- If no information is found in any tab, simply say 'I couldn't find the answer in your open tabs.' Do NOT list what you checked."
            )
        else:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content from multiple tabs.\n"
                f"Current Date: {current_date}\n\n"
                "IMPORTANT: You must thoroughly analyze ALL tabs to find the answer. Do not rely on partial information from just one tab.\n\n"
                "For factual questions:\n"
                "- Search through ALL tabs carefully\n"
                "- Look for specific facts, dates, names, or details in each tab\n"
                "- If the answer appears in multiple tabs, verify consistency\n"
                "- If tabs have conflicting information, mention both and indicate which seems more reliable\n"
                "- If the answer is not clearly in any tab, say 'The information is not available in these tabs'\n\n"
                "Answer the user's question directly and accurately using information from the tabs.\n"
                "- Be specific and factual\n"
                "- Cite which tab(s) contained the information when possible\n"
                "- If uncertain, indicate that\n"
                "- Keep your answer concise but complete\n"
                "- DO NOT list tabs that did not contain the information. Only mention the source of the answer.\n"
                "- If no information is found in any tab, simply say 'I couldn't find the answer in your open tabs.' Do NOT list what you checked."
            )
        
        # Build user prompt with all tab contents
        content_parts = []
        for i, tab_info in enumerate(tab_contents, 1):
            content_parts.append(f"--- Tab {i}: {tab_info['title']} ---\nURL: {tab_info['url']}\n\n{tab_info['text']}\n")
        
        combined_content = "\\n".join(content_parts)
        # Limit total content to ~8000 chars to avoid token limits
        if len(combined_content) > 8000:
            # Prioritize: keep full content from most relevant tab, truncate others
            if relevant_tab:
                relevant_idx = next((i for i, t in enumerate(tab_contents) if t["id"] == relevant_tab.get("id")), 0)
                if relevant_idx < len(tab_contents):
                    # Keep full relevant tab, truncate others
                    relevant_content = tab_contents[relevant_idx]
                    other_content = [t for i, t in enumerate(tab_contents) if i != relevant_idx]
                    combined_content = f"--- Tab 1: {relevant_content['title']} ---\nURL: {relevant_content['url']}\n\n{relevant_content['text']}\n\n"
                    remaining_chars = 8000 - len(combined_content)
                    for i, tab_info in enumerate(other_content, 2):
                        tab_text = tab_info['text'][:remaining_chars // len(other_content)]
                        combined_content += f"--- Tab {i}: {tab_info['title']} ---\nURL: {tab_info['url']}\n\n{tab_text}\n\n"
            else:
                # No clear relevant tab, truncate all equally
                per_tab = 8000 // len(tab_contents)
                content_parts = []
                for i, tab_info in enumerate(tab_contents, 1):
                    content_parts.append(f"--- Tab {i}: {tab_info['title']} ---\nURL: {tab_info['url']}\n\n{tab_info['text'][:per_tab]}\n")
                combined_content = "\\n".join(content_parts)
        
        user_prompt = (
            f"I have {len(tab_contents)} tab(s) open. Please answer the question by analyzing ALL of them:\n\n"
            f"{combined_content}\n\n"
            f"Chat History:\n"
            f"{chr(10).join([f'{msg['role']}: {msg['text']}' for msg in chat_history[-6:]])}\n\n"
            f"Question: {query}\n\n"
            f"{'⚠️ CRITICAL: This is a chronological question. You MUST search through ALL tabs above to find ALL dates/years, then identify the EARLIEST one. Check complete lists, filmographies, and timelines in every tab.' if is_chronological else '⚠️ IMPORTANT: Thoroughly analyze ALL tabs above to find the accurate answer. Information might be spread across multiple tabs.'}"
        )
        try:
            llm_start = time.time()
            max_llm_time = 18  # Slightly longer for multi-tab analysis
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                try:
                    response = future.result(timeout=max_llm_time)
                    llm_elapsed = time.time() - llm_start
                    logger.info(f"[SIMPLE] LLM call (all tabs) took {llm_elapsed:.2f}s")
                    
                    answer = response.content if hasattr(response, "content") else str(response)
                    
                    if not answer or len(answer) < 5:
                        raise ValueError("LLM returned empty answer")
                        
                except concurrent.futures.TimeoutError:
                    llm_elapsed = time.time() - llm_start
                    logger.warning(f"[SIMPLE] LLM call timed out after {llm_elapsed:.2f}s")
                    raise TimeoutError("LLM call exceeded timeout")
            
            total_elapsed = time.time() - start_time
            logger.info(f"[SIMPLE] Total time (all tabs): {total_elapsed:.2f}s")
            
            return {
                "reply": answer,
                "mode": "single",
                "chosen_tab_id": chosen_tab_id,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        except (TimeoutError, Exception) as e:
            logger.error(f"[SIMPLE] LLM call failed: {e}")
            # Fallback: try to extract from most relevant tab
            if relevant_tab:
                text = (relevant_tab.get("text", "") or "").strip()
                text = re.sub(r'[{][^}]*[}]', '', text)
                text = re.sub(r'<[^>]+>', '', text)
                text = " ".join(text.split())
                answer = self._extract_fallback_answer(query, text, relevant_tab.get("title", "Untitled"))
            else:
                answer = "I couldn't analyze all tabs in time. Please try again or check the tabs directly."
            
            return {
                "reply": answer,
                "mode": "single",
                "chosen_tab_id": chosen_tab_id,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
    
    def _answer_question(self, query: str, tab: Dict[str, Any], all_tabs: List[Dict[str, Any]], start_time: float, chat_history: List[Dict[str, str]] = []) -> Dict[str, Any]:
        """Answer a specific question using a single relevant tab."""
        logger.info(f"[SIMPLE] Answering specific question using tab: {tab.get('title', 'Untitled')}")
        
        # Get current date for relative time calculations
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        title = tab.get("title", "Untitled")
        url = tab.get("url", "")
        text = (tab.get("text", "") or "").strip()
        
        # Clean text - remove HTML/CSS artifacts
        text = re.sub(r'[{][^}]*[}]', '', text)  # Remove CSS
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        text = " ".join(text.split())  # Normalize whitespace
        text = text[:6000]  # Increased for better analysis (was 3000)
        
        # Google search pages might have less content but still contain useful info
        is_google_search = "google.com" in url.lower() and "/search" in url.lower()
        min_content_length = 10 if is_google_search else 50
        
        if not text or len(text) < min_content_length:
            if is_google_search:
                # For Google search, try to answer from what we have
                if text and len(text) >= 20:
                    # Use the limited content we have
                    pass  # Continue processing
                else:
                    return {
                        "reply": f"The Google search tab '{title}' doesn't have extractable search results. The page might still be loading or the results are not accessible.",
                        "mode": "single",
                        "chosen_tab_id": tab.get("id"),
                        "suggested_close_tab_ids": [],
                        "workspace_summary": {},
                        "alerts": [],
                        "price_info": {},
                        "should_ask_cleanup": False,
                    }
            else:
                return {
                    "reply": f"The tab '{title}' doesn't have enough content to answer your question.",
                    "mode": "single",
                    "chosen_tab_id": tab.get("id"),
                    "suggested_close_tab_ids": [],
                    "workspace_summary": {},
                    "alerts": [],
                    "price_info": {},
                    "should_ask_cleanup": False,
                }
        
        # Enhanced prompt for thorough analysis
        query_lower = query.lower()
        is_chronological = any(word in query_lower for word in ["first", "earliest", "oldest", "beginning", "start", "debut", "birthdate", "birthday", "born"])
        
        if is_chronological:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content.\n"
                f"Current Date: {current_date}\n\n"
                "CRITICAL for chronological questions (first, earliest, oldest, birthdate, etc.):\n"
                "1. Search through ALL the content systematically - do not stop at the first mention\n"
                "2. Look for dates, years, chronological lists, timelines, filmography sections\n"
                "3. Find ALL items that could answer the question, then identify which one is EARLIEST by date/year\n"
                "4. If you see a list or filmography, check the ENTIRE list, not just the first few items\n"
                "5. Compare dates carefully - the answer must be the item with the EARLIEST date\n"
                "6. If the content mentions 'first' but also shows an earlier date elsewhere, use the EARLIEST date\n"
                "7. Be precise - include the exact name/title and year/date in your answer\n\n"
                "Answer the user's question directly and accurately.\n"
                "- State the exact name/title and the year/date\n"
                "- If you're uncertain, say so\n"
                "- Keep your answer concise but complete\n"
                "- DO NOT list tabs that did not contain the information. Only mention the source of the answer.\n"
                "- If no information is found, simply say 'I couldn't find the answer in the provided content.'"
            )
        else:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content.\n"
                f"Current Date: {current_date}\n\n"
                "IMPORTANT: You must thoroughly analyze the ENTIRE content to find the answer. Do not rely on partial information.\n\n"
                "For factual questions:\n"
                "- Search through ALL the content carefully\n"
                "- Look for specific facts, dates, names, or details\n"
                "- Verify your answer by checking if it's explicitly stated in the content\n"
                "- If you find conflicting information, mention both and indicate which seems more reliable\n"
                "- If the answer is not clearly in the content, say 'The information is not available in this tab'\n\n"
                "Answer the user's question directly and accurately using information from the content.\n"
                "- Be specific and factual\n"
                "- Cite specific details from the content when possible\n"
                "- If uncertain, indicate that\n"
                "- Keep your answer concise but complete\n"
                "- DO NOT list tabs that did not contain the information. Only mention the source of the answer.\n"
                "- If no information is found, simply say 'I couldn't find the answer in the provided content.'"
            )
        
        user_prompt = f"""Content from: {title}
URL: {url}

{text}

Chat History:
{chr(10).join([f"{msg['role']}: {msg['text']}" for msg in chat_history[-6:]])}

Question: {query}

{'⚠️ CRITICAL: This is a chronological question. You MUST search through ALL content above to find ALL dates/years, then identify the EARLIEST one. Check complete lists, filmographies, and timelines.' if is_chronological else '⚠️ IMPORTANT: Thoroughly analyze the content above to find the accurate answer.'}"""
        
        # Call LLM with timeout protection
        try:
            llm_start = time.time()
            max_llm_time = 15  # Increased to 15 seconds for thorough analysis (LLM has 10s timeout, ThreadPool adds safety)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                try:
                    response = future.result(timeout=max_llm_time)
                    llm_elapsed = time.time() - llm_start
                    logger.info(f"[SIMPLE] LLM call took {llm_elapsed:.2f}s")
                    
                    answer = response.content if hasattr(response, "content") else str(response)
                    
                    if not answer or len(answer) < 5:
                        raise ValueError("LLM returned empty answer")
                        
                except concurrent.futures.TimeoutError:
                    llm_elapsed = time.time() - llm_start
                    logger.warning(f"[SIMPLE] LLM call timed out after {llm_elapsed:.2f}s")
                    raise TimeoutError("LLM call exceeded timeout")
            
            total_elapsed = time.time() - start_time
            logger.info(f"[SIMPLE] Total time: {total_elapsed:.2f}s")
            
            return {
                "reply": answer,
                "mode": "single",
                "chosen_tab_id": tab.get("id"),
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        except (TimeoutError, Exception) as e:
            logger.error(f"[SIMPLE] LLM call failed: {e}")
            # Fallback: extract answer from text
            answer = self._extract_fallback_answer(query, text, title)
            
            return {
                "reply": answer,
                "mode": "single",
                "chosen_tab_id": tab.get("id"),
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
    
    def _extract_fallback_answer(self, query: str, text: str, title: str) -> str:
        """Extract answer from text when LLM fails - improved extraction."""
        query_lower = query.lower()
        
        # For birthdate/birthday/born questions
        if "birthdate" in query_lower or "birthday" in query_lower or "born" in query_lower:
            # Look for full dates first
            dates = re.findall(r'\\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},?\\s+\\d{4}\\b', text, re.IGNORECASE)
            if dates:
                # Find the earliest date if multiple
                return f"Based on '{title}': {dates[0]}"
            
            # Look for "born" followed by date/year
            born_patterns = [
                r'born\\s+(?:on\\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},?\\s+\\d{4}',
                r'born\\s+(?:on\\s+)?(\\d{1,2})[/-](\\d{1,2})[/-](\\d{4})',
                r'born\\s+[^.]*?(\\d{4})',
                r'birth[^.]*?(\\d{4})',
            ]
            for pattern in born_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 3:  # Date format
                        return f"Based on '{title}': Born on {match.group(1)}/{match.group(2)}/{match.group(3)}"
                    elif match.group(1):
                        return f"Based on '{title}': Born in {match.group(1)}"
            
            # Look for all years and find earliest
            years = re.findall(r'\\b(19\\d{2}|20\\d{2})\\b', text)
            if years:
                earliest_year = min(int(y) for y in years if 1900 <= int(y) <= 2100)
                # Try to find context around this year
                year_context = re.search(rf'[^.]*{earliest_year}[^.]*', text, re.IGNORECASE)
                if year_context:
                    context = year_context.group(0)[:100]
                    return f"Based on '{title}': {context}..."
                return f"Based on '{title}': Born in {earliest_year}"
        
        # For "first" questions - find earliest date
        if "first" in query_lower or "earliest" in query_lower:
            # Extract all years and find earliest
            years = re.findall(r'\\b(19\\d{2}|20\\d{2})\\b', text)
            if years:
                earliest_year = min(int(y) for y in years if 1900 <= int(y) <= 2100)
                # Find context around earliest year - look for movie titles, names, etc.
                # Search for patterns like "Title (year)" or "Title year"
                year_context_patterns = [
                    rf'([A-Z][^.]*?)\\s*\\(?\\s*{earliest_year}\\s*\\)?',
                    rf'({earliest_year})\\s*[:\\-]\\s*([A-Z][^.]*?)',
                ]
                for pattern in year_context_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        context = match.group(0)[:150]
                        return f"Based on '{title}': {context}..."
                
                # Fallback: just return earliest year with some context
                year_context = re.search(rf'[^.]*{earliest_year}[^.]*', text, re.IGNORECASE)
                if year_context:
                    context = year_context.group(0)[:150]
                    return f"Based on '{title}': {context}..."
        
        # Generic fallback - find most relevant sentences
        query_words = set(word for word in query_lower.split() if len(word) > 3)
        sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
        
        # Score sentences by relevance
        scored_sentences = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            score = sum(1 for word in query_words if word in sentence_lower)
            if score > 0:
                scored_sentences.append((score, sentence))
        
        if scored_sentences:
            scored_sentences.sort(key=lambda x: x[0], reverse=True)
            best_sentence = scored_sentences[0][1]
            return f"Based on '{title}': {best_sentence[:250]}..."
        elif sentences:
            return f"Based on '{title}': {sentences[0][:200]}..."
        
        return f"Based on '{title}': The information might be in the tab, but I couldn't extract it. Please check the tab directly."
    
    def _analyze_tabs(self, query: str, tabs: List[Dict[str, Any]], start_time: float) -> Dict[str, Any]:
        """Analyze all tabs - use LLM for proper summaries."""
        logger.info(f"[SIMPLE] Analyzing {len(tabs)} tabs with LLM")
        
        if not tabs:
            return {
                "reply": "No tabs available to analyze.",
                "mode": "analysis",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        
        # For "analyze my tabs", use LLM to summarize each tab
        # Process ALL tabs - don't skip any, including Google Search tabs
        summaries = []
        
        logger.info(f"[SIMPLE] Processing {len(tabs)} tabs total (including Google Search tabs)")
        
        for idx, tab in enumerate(tabs):
            title = tab.get("title", "Untitled")
            url = tab.get("url", "")
            text = (tab.get("text", "") or "").strip()
            
            # Always include the tab, even if text is empty
            is_google_search = "google.com" in url.lower() and "/search" in url.lower()
            
            logger.info(f"[SIMPLE] Processing tab {idx + 1}/{len(tabs)}: {title[:50]} (Google: {is_google_search}, Text length: {len(text)})")
            
            # Clean text
            text = re.sub(r'[{][^}]*[}]', '', text)
            text = re.sub(r'<[^>]+>', '', text)
            text = " ".join(text.split())
            text = text[:3000]  # Limit per tab for speed
            
            # Google search pages might have less content, but still analyze them
            min_content_length = 10 if is_google_search else 20  # Lower threshold for all tabs to ensure inclusion
            
            # For Google search, ALWAYS include it, even with minimal or no content
            if is_google_search:
                # Extract search query from URL or text
                search_query = ""
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(url)
                    query_params = parse_qs(parsed.query)
                    search_query = query_params.get('q', [''])[0] if 'q' in query_params else ""
                except:
                    pass
                
                if not search_query and "Search Query:" in text:
                    search_query = text.split("Search Query:")[1].split("\\n")[0].strip()
                
                # If we have some content (even minimal), try to summarize it
                if text and len(text) >= 10:
                    # Use LLM to analyze Google search results
                    try:
                        summary_prompt = f"Tab: {title}\\nURL: {url}\\n\\nThis is a Google Search results page.\\nSearch Query: {search_query if search_query else 'Unknown'}\\n\\nContent extracted from search results:\\n{text[:2000]}\\n\\nProvide a concise 2-3 sentence summary of what this search is about and what information is available in the search results."
                        
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(
                                self.llm.invoke,
                                [HumanMessage(content=summary_prompt)]
                            )
                            try:
                                response = future.result(timeout=8)
                                summary = response.content if hasattr(response, "content") else str(response)
                                summaries.append({
                                    "title": title,
                                    "summary": summary[:300]
                                })
                                logger.info(f"[SIMPLE] Successfully analyzed Google search tab {idx + 1}")
                                continue
                            except concurrent.futures.TimeoutError:
                                # Fallback
                                pass
                    except Exception as e:
                        logger.warning(f"[SIMPLE] Failed to analyze Google search: {e}")
                
                # Fallback for Google search - ALWAYS include, even with no content
                if text and len(text) >= 10:
                    # Try to extract a few key results from the text
                    lines = [l.strip() for l in text.split('\\n') if l.strip()][:5]  # Get first 5 non-empty lines
                    preview = ' '.join(lines[:3])[:150] if lines else ""
                    if preview:
                        summary_text = f"**Google Search:** '{search_query if search_query else 'unknown query'}'\\n\\n{preview}..."
                    else:
                        summary_text = f"**Google Search:** '{search_query if search_query else 'unknown query'}'\\n\\n*Search results page - content may be dynamically loaded.*"
                else:
                    # Even with no text, include the tab
                    summary_text = f"**Google Search:** '{search_query if search_query else 'unknown query'}'\\n\\n*Search results are dynamically loaded. This tab is open but content extraction is limited.*"
                
                summaries.append({
                    "title": title,
                    "summary": summary_text
                })
                continue
            
            # For non-Google tabs, check minimum content
            # BUT always include them - don't skip tabs
            if not text or len(text) < min_content_length:
                summaries.append({
                    "title": title,
                    "summary": f"*Limited content available. This tab may require manual inspection.*"
                })
                continue
            
            # Quick LLM summary for each tab
            try:
                summary_prompt = (
                    f"Tab: {title}\\n"
                    f"URL: {url}\\n\\n"
                    "Content:\\n"
                    f"{text[:2500]}\\n\\n"
                    "Provide a concise 2-3 sentence summary of what this tab is about. Focus on the main topic and key information."
                )
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self.llm.invoke,
                        [HumanMessage(content=summary_prompt)]
                    )
                    try:
                        response = future.result(timeout=8)  # 8 seconds per tab
                        summary = response.content if hasattr(response, "content") else str(response)
                        summaries.append({
                            "title": title,
                            "summary": summary[:300]  # Limit summary length
                        })
                        logger.info(f"[SIMPLE] Successfully summarized tab {idx + 1}: {title[:50]}")
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"[SIMPLE] Timeout summarizing tab {idx + 1}, using fallback")
                        # Fallback to text extraction
                        sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                        if sentences:
                            summary = ". ".join(sentences[:2]) + "."
                        else:
                            summary = f"Content from {title}: {text[:150]}..."
                        summaries.append({
                            "title": title,
                            "summary": summary[:300]
                        })
            except Exception as e:
                logger.warning(f"[SIMPLE] Failed to summarize tab '{title}': {e}")
                # Fallback - always provide something
                sentences = [s.strip() for s in text.split('.') if s.strip() and len(s.strip()) > 20]
                if sentences:
                    summary = ". ".join(sentences[:2]) + "."
                else:
                    summary = f"Content from {title}: {text[:150]}..."
                summaries.append({
                    "title": title,
                    "summary": summary[:300]
                })
        
        # Let LLM format the response naturally instead of hard-coding
        system_prompt = (
            "You are TabSensei, an assistant that helps users manage their browser tabs.\n"
            "Analyze and present tab information in a clear, user-friendly way using markdown.\n"
            "Format your response naturally - use headers, lists, and formatting as appropriate. Be concise but informative.\n"
            "CRITICAL: You MUST list ALL tabs provided in the analysis. Do not skip any tabs."
        )
        
        # Build summary text for LLM
        summary_text = f"Total tabs: {len(tabs)}\\n\\n"
        for i, summary_info in enumerate(summaries, 1):
            summary_text += f"Tab {i}: {summary_info['title']}\\n"
            summary_text += f"Summary: {summary_info['summary']}\\n\\n"
        
        user_prompt = (
            f"The user asked: \"{query}\"\\n\\n"
            "Here is the analysis of all open tabs:\\n\\n"
            f"{summary_text}\\n\\n"
            "Please present this information in a clear, well-formatted way. Use markdown formatting naturally - headers, lists, emphasis, etc. Make it easy to read and understand."
        )
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                response = future.result(timeout=12)
                reply = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning(f"[SIMPLE] LLM formatting failed, using fallback: {e}")
            # Fallback: simple format without hard-coding structure
            reply = f"Analysis of {len(tabs)} tab(s):\\n\\n"
            for i, summary_info in enumerate(summaries, 1):
                reply += f"{i}. {summary_info['title']}\\n"
                reply += f"   {summary_info['summary']}\\n\\n"
        
        total_elapsed = time.time() - start_time
        logger.info(f"[SIMPLE] Analysis completed in {total_elapsed:.2f}s")
        
        return {
            "reply": reply,
            "mode": "analysis",
            "chosen_tab_id": tabs[0].get("id") if tabs else None,
            "suggested_close_tab_ids": [],
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
