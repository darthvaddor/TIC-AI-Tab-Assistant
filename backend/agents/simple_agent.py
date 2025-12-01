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
        if any(phrase in query_lower for phrase in ["how many tabs", "how many tab", "how manytabs", "count tabs", "number of tabs"]):
            return self._count_tabs(query, tabs, start_time)
        
        # Determine query type
        is_specific_question = (
            "?" in query or
            any(word in query_lower for word in [
                "what", "when", "where", "who", "which", "how", "why",
                "birthdate", "birthday", "born", "age", "first", "last"
            ]) and
            not any(phrase in query_lower for phrase in [
                "analyze", "all tabs", "my tabs", "what tabs", "show tabs", "list tabs", "how many tabs", "how manytabs"
            ])
        )
        
        # If user explicitly asks to check all tabs or analyze
        check_all_tabs = any(phrase in query_lower for phrase in ["all tabs", "analyze", "summary", "summarize", "compare", "search all", "think again", "try again", "analyze again"])
        
        if check_all_tabs:
            return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
            
        # "How many" questions should always check all tabs, not do full analysis
        if "how many" in query_lower and not any(phrase in query_lower for phrase in ["how many tabs", "how many tab"]):
            return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
            
        if is_specific_question:
            # Try to find relevant tab first
            relevant_tab = self._find_relevant_tab(query, tabs)
            if relevant_tab:
                return self._answer_question(query, relevant_tab, tabs, start_time, chat_history)
            else:
                # Fallback to checking all tabs if no specific relevant tab found
                return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
        
        # Check for price alert requests (check chat history for context if query is short/ambiguous)
        price_alert_keywords = ["price", "cost", "expensive", "cheap", "product", "item"]
        alert_keywords = ["alert", "notify", "remind", "tell me", "let me know", "set", "yes", "yeah", "please", "do it"]
        drop_keywords = ["lower", "drop", "down", "decrease", "fall", "sale", "discount"]
        
        # Check if query mentions price alert OR if recent chat history mentions price
        recent_chat = " ".join([msg.get("text", "") for msg in chat_history[-4:] if msg.get("role") in ["user", "assistant"]]).lower()
        has_price_context = any(word in recent_chat for word in price_alert_keywords) or any(word in query_lower for word in price_alert_keywords)
        has_alert_request = any(word in query_lower for word in alert_keywords)
        has_drop_mention = any(word in query_lower for word in drop_keywords) or any(word in recent_chat for word in drop_keywords)
        
        # If user is asking to set price alert (with context from recent chat about price)
        if has_price_context and has_alert_request and (has_drop_mention or "price" in query_lower or "price" in recent_chat):
            # Also check if there's a product with price in tabs
            has_product_with_price = any(tab.get("price") and tab.get("price") > 0 for tab in tabs)
            if has_product_with_price:
                return self._set_price_alert(query, tabs)

        # Check for reminder/alert requests (more flexible matching)
        # Include "alarm" phrasing as well, since users often say "set an alarm"
        reminder_phrases = [
            "remind me",
            "set a reminder",
            "set reminder",
            "alert me",
            "notify me",
            "can you set a reminder",
            "can you remind me",
            "please remind me",
            "create a reminder",
            "add a reminder",
            # Alarm-style phrasing
            "set an alarm",
            "set alarm",
            "alarm me",
            "create an alarm",
        ]
        # Also check for time patterns that indicate reminder requests
        has_time_pattern = any(word in query_lower for word in ["everyday", "every day", "daily", "at ", "pm", "am", ":", "7:45", "8:00"])
        has_reminder_intent = any(phrase in query_lower for phrase in reminder_phrases) or \
                             (has_time_pattern and any(word in query_lower for word in ["remind", "alert", "notify", "tell", "alarm"]))
        
        # Check if previous message was about setting a reminder and current query is just a time
        is_reminder_followup = False
        # Also check for corrections about reminders (e.g., "I said 9:26 pm not 9:28 pm")
        is_reminder_correction = False
        correction_keywords = ["i said", "not", "wrong", "correction", "that's wrong", "that was", "should be", "meant"]
        
        if chat_history and len(chat_history) > 0:
            # Check last assistant message for reminder
            last_assistant_msg = ""
            last_user_msg = ""
            for msg in reversed(chat_history[-3:]):  # Check last 3 messages
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("text", "").lower()
                elif msg.get("role") == "user":
                    last_user_msg = msg.get("text", "").lower()
            
            # Check if last assistant message mentioned a reminder
            if last_assistant_msg and ("reminder" in last_assistant_msg or ("set" in last_assistant_msg and "at" in last_assistant_msg)):
                # Last assistant message was about a reminder
                # Check if current query is a correction (has correction keywords + time pattern)
                if any(keyword in query_lower for keyword in correction_keywords) and has_time_pattern:
                    is_reminder_correction = True
                    logger.info(f"Reminder correction detected: {query}")
                # Or if it's just a time (follow-up)
                elif has_time_pattern and len(query_lower.split()) <= 5:
                    is_reminder_followup = True
                    logger.info(f"Reminder follow-up detected: {query}")
            
            # Also check if query mentions a time that was in the last assistant message (correction pattern)
            if last_assistant_msg and has_time_pattern:
                # Extract time from last assistant message
                import re
                last_time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)', last_assistant_msg)
                if last_time_match:
                    # Check if current query mentions a different time (correction)
                    current_time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)', query_lower)
                    if current_time_match and any(keyword in query_lower for keyword in ["not", "said", "wrong", "should", "meant", "i said"]):
                        is_reminder_correction = True
                        logger.info(f"Reminder time correction detected: {query}")
            
            # Also check if query is correcting a time mentioned in assistant's last message
            # Pattern: "i said X not Y" or "X not Y" where X and Y are times
            if last_assistant_msg and ("reminder" in last_assistant_msg or "set" in last_assistant_msg):
                import re
                # Look for time patterns in query
                time_pattern = r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)'
                times_in_query = re.findall(time_pattern, query_lower)
                if len(times_in_query) >= 1 and any(keyword in query_lower for keyword in ["not", "said", "wrong", "i said"]):
                    is_reminder_correction = True
                    logger.info(f"Reminder correction detected via time pattern: {query}")
            
            # Also check if previous user message was about reminder
            if last_user_msg and any(phrase in last_user_msg for phrase in reminder_phrases):
                # Previous message was about reminder, current might be just the time
                if has_time_pattern and len(query_lower.split()) <= 5:  # Short query with time = likely reminder time
                    is_reminder_followup = True
        
        if has_reminder_intent or is_reminder_followup or is_reminder_correction:
            logger.info(f"Reminder request detected: {query}")
            result = self._set_reminder(query, chat_history)
            if result:
                return result
            # If reminder setting failed, don't fall through to tab analysis - return an error message instead
            logger.warn("Reminder setting failed")
            return {
                "reply": "I couldn't understand when to set the reminder. Please specify a time (e.g., '9:26 PM' or 'in 5 minutes').",
                "mode": "reminder",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }
        
        # Only do full tab analysis if explicitly requested
        # Check for explicit analysis/cleanup requests - be strict to avoid random tab reports
        explicit_analysis_keywords = [
            "analyze",
            "analysis",
            "summarize",
            "summary",
            "compare",
            "what tabs",
            "show tabs",
            "list tabs",
            "all tabs",
            "my tabs",
            "tab report",
            "tab summary",
            "what's in my tabs",
            "report",
            # Explicit cleanup / close‑tab intents
            "close tabs",
            "close the tabs",
            "close all other tabs",
            "close unrelated tabs",
            "close tabs not relevant",
            "keep only the tabs",
        ]

        # Explicit close/cleanup phrasing involving tabs
        close_tabs_phrases = [
            "close tabs",
            "close the tabs",
            "close all other tabs",
            "close unrelated tabs",
            "close tabs not relevant",
            "keep only the tabs",
        ]
        has_close_tabs_intent = any(p in query_lower for p in close_tabs_phrases) and "tab" in query_lower

        # Only match if it's a clear analysis/cleanup request, not just a stray word.
        has_explicit_analysis_request = (
            "analyze" in query_lower
            or "analysis" in query_lower
            or "tab report" in query_lower
            or "tab summary" in query_lower
            # Summaries / comparisons of tabs
            or (
                any(
                    keyword in query_lower
                    for keyword in ["summarize", "summary", "compare", "report"]
                )
                and any(
                    context in query_lower
                    for context in ["tab", "tabs", "my tabs", "all tabs"]
                )
            )
            or has_close_tabs_intent
        )
        
        # If no explicit request and query doesn't match any handler, ask for clarification
        if not has_explicit_analysis_request and not is_specific_question:
            # Check if query is very short or unclear
            if len(query_lower.split()) <= 3 and not any(word in query_lower for word in ["remind", "alert", "set", "price", "how many"]):
                return {
                    "reply": "I'm not sure what you're asking. Could you please clarify? You can:\n- Ask questions about your tabs\n- Set reminders (e.g., 'remind me at 9 PM')\n- Request tab analysis (e.g., 'analyze my tabs')\n- Ask about specific information in your tabs",
                    "mode": "single",
                    "chosen_tab_id": None,
                    "suggested_close_tab_ids": [],
                    "workspace_summary": {},
                    "alerts": [],
                    "price_info": {},
                    "should_ask_cleanup": False,
                }
        
        # If user explicitly asked to close/keep tabs, run a lightweight cleanup helper
        if has_close_tabs_intent:
            return self._close_irrelevant_tabs(query, tabs)

        # Otherwise, only do full tab analysis if explicitly requested
        if has_explicit_analysis_request:
            return self._analyze_tabs(query, tabs, start_time)
        
        # For other queries that don't match, try to answer from tabs without full analysis
        # This handles general questions that might be answerable from a single tab
        if is_specific_question:
            # Already handled above, but if we get here, try to find relevant tab
            relevant_tab = self._find_relevant_tab(query, tabs)
            if relevant_tab:
                return self._answer_question(query, relevant_tab, tabs, start_time, chat_history)
            else:
                # If no relevant tab found, check all tabs but don't do full analysis
                return self._answer_question_all_tabs(query, tabs, start_time, chat_history)
        
        # Last resort: if query is unclear and doesn't match anything, ask for clarification
        return {
            "reply": "I'm not sure what you're asking. Could you please rephrase your question? You can:\n- Ask specific questions about your tabs\n- Set reminders (e.g., 'remind me at 9 PM')\n- Request tab analysis (e.g., 'analyze my tabs')\n- Ask 'how many tabs are open'",
            "mode": "single",
            "chosen_tab_id": None,
            "suggested_close_tab_ids": [],
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
    
    def _set_price_alert(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Set a price alert based on user query and open tabs."""
        # Find tab with price information
        product_tab = None
        for tab in tabs:
            if tab.get("price") and tab.get("price") > 0:
                # If query mentions product name, prioritize that tab
                if tab.get("productName") and tab.get("productName").lower() in query.lower():
                    product_tab = tab
                    break
                # Otherwise, just take the first one with a price (likely the active one or most relevant)
                if not product_tab:
                    product_tab = tab
        
        if not product_tab:
            return {
                "reply": "I couldn't find any product with a price in your open tabs. Please open a product page first.",
                "mode": "price_alert",
                "chosen_tab_id": None
            }
            
        # Use LLM to extract threshold details
        system_prompt = (
            "You are a helpful assistant that extracts price alert details.\n"
            f"Product: {product_tab.get('productName', 'Unknown Product')}\n"
            f"Current Price: {product_tab.get('price', 0)}\n"
            "Analyze the user's request to determine the alert threshold.\n"
            "Return ONLY a JSON object with keys: 'alert_threshold' (number) and 'threshold_type' ('percentage' or 'absolute').\n"
            "If the user says 'when price lowers' or 'drops', default to 5% drop (threshold_type='percentage', alert_threshold=5).\n"
            "If the user specifies a value (e.g. 'below $50'), calculate the drop or set absolute value."
        )
        
        user_prompt = f"User Request: {query}"
        
        try:
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            
            import json
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                
                price_alert = {
                    "product_name": product_tab.get("productName", product_tab.get("title", "Product")),
                    "url": product_tab.get("url"),
                    "price": product_tab.get("price"),
                    "currency": "USD", # Default for now
                    "alert_threshold": data.get("alert_threshold", 5),
                    "threshold_type": data.get("threshold_type", "percentage")
                }
                
                return {
                    "reply": f"I'm setting a price alert for {price_alert['product_name']}.",
                    "price_alert": price_alert,
                    "mode": "price_alert",
                    "chosen_tab_id": product_tab.get("id"),
                    "suggested_close_tab_ids": [],
                    "workspace_summary": {},
                    "alerts": [],
                    "price_info": {},
                    "should_ask_cleanup": False,
                }
        except Exception as e:
            logger.error(f"Error setting price alert: {e}")
            
        return {
            "reply": "I couldn't understand the price alert details. Please try again.",
            "mode": "price_alert",
            "chosen_tab_id": None
        }

    def _close_irrelevant_tabs(self, query: str, tabs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute which tabs are irrelevant and should be closed, based on a natural language close-tabs command.

        Example query: "close all tabs irrelevant to kaggle and neetcode".
        We keep tabs whose title/url/text mention the keep keywords; others go into suggested_close_tab_ids.
        """
        logger.info(f"[SIMPLE] Close-tabs request detected: '{query}'")

        query_lower = query.lower()

        # Heuristic: extract keywords after 'to ' or 'for ' as the things we want to keep
        keep_keywords: List[str] = []
        for marker in ["to ", "for ", "relevant to ", "related to "]:
            if marker in query_lower:
                tail = query_lower.split(marker, 1)[1]
                # Split on common separators
                raw_parts = [p.strip() for p in re.split(r"[,&/]", tail) if p.strip()]
                for part in raw_parts:
                    # Use only alphabetic tokens as keywords
                    tokens = [t for t in re.split(r"\s+", part) if t.isalpha()]
                    phrase = " ".join(tokens).strip()
                    if phrase:
                        keep_keywords.append(phrase)
                break

        # Fallback: if we didn't find anything after 'to/for', use non-stopwords from the query
        if not keep_keywords:
            stopwords = {"close", "tabs", "tab", "irrelevant", "relevant", "only", "keep", "and", "the", "all", "other"}
            tokens = [t for t in re.split(r"[^a-z0-9]+", query_lower) if t]
            keep_keywords = [t for t in tokens if t not in stopwords]

        logger.info(f"[SIMPLE] Close-tabs keep keywords: {keep_keywords}")

        if not tabs or not keep_keywords:
            # Nothing to do safely
            return {
                "reply": "I couldn't confidently tell which tabs are relevant, so I didn't close anything.",
                "mode": "single",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }

        # Decide which tabs to keep/close
        keep_ids: List[int] = []
        close_ids: List[int] = []

        for tab in tabs:
            tab_id = tab.get("id")
            if tab_id is None:
                continue

            title = (tab.get("title") or "").lower()
            url = (tab.get("url") or "").lower()
            text = (tab.get("text") or "").lower()

            haystack = " ".join([title, url, text])

            is_relevant = any(kw in haystack for kw in keep_keywords)

            if is_relevant:
                keep_ids.append(tab_id)
            else:
                close_ids.append(tab_id)

        logger.info(f"[SIMPLE] Close-tabs decision: keep={keep_ids}, close={close_ids}")

        if not close_ids:
            return {
                "reply": "All your current tabs look relevant to what you asked about, so I didn't close anything.",
                "mode": "single",
                "chosen_tab_id": None,
                "suggested_close_tab_ids": [],
                "workspace_summary": {},
                "alerts": [],
                "price_info": {},
                "should_ask_cleanup": False,
            }

        # Build a short, human explanation listing what we kept
        kept_titles = [tab.get("title", "Untitled") for tab in tabs if tab.get("id") in keep_ids]
        num_closed = len(close_ids)
        num_kept = len(keep_ids)

        if kept_titles:
            kept_list = "; ".join(kept_titles[:4])
            if len(kept_titles) > 4:
                kept_list += " …"
            reply = (
                f"I'll keep the tabs related to: {', '.join(keep_keywords)}.\n\n"
                f"Kept {num_kept} tab(s): {kept_list}\n"
                f"and will close {num_closed} other tab(s)."
            )
        else:
            reply = f"I'm closing {num_closed} tab(s) that look unrelated to {', '.join(keep_keywords)}."

        return {
            "reply": reply,
            "mode": "single",
            "chosen_tab_id": None,
            "suggested_close_tab_ids": close_ids,
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
    
    def _set_reminder(self, query: str, chat_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Set a reminder based on user query and chat context."""
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get current time in both local and Pacific Time
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            pacific_tz = ZoneInfo('America/Los_Angeles')
            current_pacific = datetime.now(pacific_tz)
            current_pacific_str = current_pacific.strftime("%Y-%m-%d %H:%M:%S %Z")
        except (ImportError, Exception):
            # Fallback: calculate Pacific Time manually (UTC-8 or UTC-7 depending on DST)
            # This is approximate but should work for most cases
            from datetime import timezone, timedelta
            try:
                # Try to get Pacific offset (PST = UTC-8, PDT = UTC-7)
                # We'll approximate by checking if we're in daylight saving time
                now = datetime.now()
                # Rough DST check: DST typically March-November
                is_dst = now.month in range(3, 11) or (now.month == 3 and now.day >= 8) or (now.month == 11 and now.day < 1)
                pacific_offset = timedelta(hours=-7 if is_dst else -8)
                pacific_tz_info = timezone(pacific_offset)
                current_pacific = datetime.now(pacific_tz_info)
                current_pacific_str = current_pacific.strftime("%Y-%m-%d %H:%M:%S")
            except:
                current_pacific_str = current_date  # Final fallback
        
        system_prompt = (
            f"You are a helpful assistant that extracts reminder details.\n"
            f"Current Date/Time (local): {current_date}\n"
            f"Current Date/Time (Pacific): {current_pacific_str}\n"
            "Analyze the user's request and the chat history to determine the reminder message and the target time.\n\n"
            "IMPORTANT RULES:\n"
            "1. TIME PARSING PRIORITY:\n"
            "   - If user says 'in X mins' or 'in X minutes' AND also specifies an explicit time (e.g., '9:26 PM'), ALWAYS use the explicit time, NOT the 'in X mins' calculation\n"
            "   - Example: 'set a reminder in 2 mins 9:26 pm' → use 9:26 PM, NOT 9:28 PM (9:26 + 2 mins)\n"
            "   - The 'in X mins' is just context about when that time occurs, not an instruction to add minutes\n"
            "   - Only use 'in X mins' calculation if NO explicit time is given (e.g., 'remind me in 5 minutes')\n"
            "2. CORRECTIONS:\n"
            "   - If user says 'I said X not Y' or 'that's wrong, it should be X', extract the CORRECT time (X) from their correction\n"
            "   - Look for phrases like 'I said 9:26 pm not 9:28 pm' → use 9:26 PM\n"
            "   - Ignore the incorrect time mentioned after 'not'\n"
            "3. TIMEZONE HANDLING:\n"
            "   - If user specifies 'Pacific Time', 'PT', 'PST', 'PDT', or 'Pacific', convert the time to Pacific Time\n"
            "   - If no timezone is specified, use the user's local timezone\n"
            "   - Always return timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SS-08:00 for PST or YYYY-MM-DDTHH:MM:SS-07:00 for PDT\n"
            "   - Or use UTC: YYYY-MM-DDTHH:MM:SSZ (convert Pacific Time to UTC: PST = UTC-8, PDT = UTC-7)\n"
            "4. For 'everyday'/'daily' reminders with a time:\n"
            "   - Parse the time (e.g., '7:52 PM', '7:52pm', '9:10 PM Pacific')\n"
            "   - Convert to the appropriate timezone if specified\n"
            "   - Compare with current time in that timezone\n"
            "   - If the time has NOT passed today, set for TODAY at that time\n"
            "   - If the time HAS passed today (or is within 2 minutes), set for TOMORROW at that time\n"
            "   - This ensures the first reminder happens at the next occurrence\n"
            "5. If the user provides just a time (e.g., '7:45 PM', '9:12 PM Pacific') after asking to set a reminder, combine it with the previous reminder request from chat history.\n"
            "6. If the user says '24 hrs before', '24 hours before', or similar:\n"
            "   - Look at the chat history to find the most recent event/deadline mentioned\n"
            "   - Extract the date/time of that event\n"
            "   - Subtract 24 hours from that time\n"
            "   - Use that calculated time as the reminder timestamp\n"
            "7. For recurring reminders (everyday/daily), ALWAYS set the timestamp for the NEXT occurrence of that time (tomorrow if time has passed today).\n"
            "8. Parse times like '7:45 PM', '8:00 AM', '19:45', '7:45pm', '9:10 PM Pacific Time', etc. correctly. Assume 12-hour format if AM/PM is specified.\n"
            "9. CRITICAL: If the specified time is within 2 minutes of the current time or has passed, set it for TOMORROW to ensure it fires.\n"
            "10. Combine the reminder message from chat history if the current query is just a time or a correction.\n\n"
            "Return ONLY a JSON object with keys:\n"
            "- 'message' (what to remind about - extract ONLY from the current user request, NOT from chat history. If no specific message is given, use a simple default like 'Reminder')\n"
            "- 'timestamp' (ISO 8601 format YYYY-MM-DDTHH:MM:SS with timezone, e.g., '2024-11-30T21:10:00-08:00' for 9:10 PM PST or '2024-11-30T21:10:00-07:00' for PDT)\n"
            "- 'recurring' (true if 'everyday'/'daily'/'every day' is mentioned, false otherwise)\n"
            "CRITICAL: The 'message' field should be SHORT and extracted from the current request only. Do NOT include previous chat messages or full conversation history."
        )
        
        user_prompt = (
            f"Chat History (for context only - do NOT include previous messages in the reminder message):\n"
            f"{chr(10).join([f'{msg['role']}: {msg['text']}' for msg in chat_history[-6:]])}\n\n"
            f"User Request: {query}\n\n"
            f"IMPORTANT: Extract ONLY the reminder message from the current user request. Do NOT include previous chat messages or questions in the reminder message. "
            f"If the user says 'set a reminder at 9:40 PM', the message should be something simple like 'Reminder' or extract what they want to be reminded about from THIS request only."
        )
        
        try:
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            
            # Extract JSON
            import json
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                timestamp = data.get("timestamp")
                message = data.get("message", "Reminder")
                recurring = data.get("recurring", False)
                
                if timestamp:
                    # Format timestamp nicely for display
                    try:
                        from datetime import datetime
                        # Parse ISO timestamp
                        if 'T' in timestamp:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromisoformat(timestamp)
                        
                        # Format as friendly date/time
                        friendly_time = dt.strftime("%B %d, %Y at %I:%M %p")
                    except:
                        # Fallback to just showing the time if parsing fails
                        friendly_time = timestamp.split('T')[1].split('-')[0] if 'T' in timestamp else timestamp
                    
                    # For recurring reminders, create multiple alarms (daily for next 30 days)
                    if recurring:
                        reply_text = f"I've set a daily reminder for: {message} at {friendly_time}"
                    else:
                        reply_text = f"I've set a reminder for: {message} at {friendly_time}"
                    
                    return {
                        "reply": reply_text,
                        "reminder": {
                            "message": message,
                            "timestamp": timestamp,
                            "recurring": recurring
                        },
                        "mode": "reminder",
                        "chosen_tab_id": None,
                        "suggested_close_tab_ids": [],
                        "workspace_summary": {},
                        "alerts": [],
                        "price_info": {},
                        "should_ask_cleanup": False,
                    }
        except Exception as e:
            logger.error(f"Error setting reminder: {e}")
            
        return {
            "reply": "I couldn't understand when to set the reminder. Please specify a time.",
            "mode": "reminder",
            "chosen_tab_id": None,
            "suggested_close_tab_ids": [],
            "workspace_summary": {},
            "alerts": [],
            "price_info": {},
            "should_ask_cleanup": False,
        }
    
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
                # Split domain parts (e.g. "neetcode.io" -> ["neetcode", "io"])
                domain_parts = domain.split('.')
                if any(part in query_words for part in domain_parts if len(part) > 2):
                    score += 15  # Stronger boost for domain match (was 10)
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
                "CRITICAL INSTRUCTIONS:\n"
                "1. Search through ALL tabs to find the answer\n"
                "2. For chronological questions, find ALL dates/years across ALL tabs, then identify the EARLIEST\n"
                "3. Give a DIRECT, CONCISE answer - just the answer itself\n"
                "4. Do NOT explain your search process\n"
                "5. Do NOT say 'Source:' or cite sources explicitly - just give the answer naturally\n"
                "6. If helpful, you can naturally mention where you found it (e.g., 'According to Wikipedia' or 'From the Roadmap tab'), but this is optional\n"
                "7. Keep it conversational and natural\n\n"
                "Example good response: 'Johnny Depp's birthdate is June 9, 1963.'\n"
                "Example also good: 'You have solved 99 out of 150 Neetcode problems.'\n"
                "Example bad response: 'I searched through multiple tabs... In Tab 1 I found... The answer is... Source: Wikipedia.'\n\n"
                "If no information is found, simply say: 'I couldn't find the answer in your open tabs.'"
            )
        else:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content from multiple tabs.\n"
                f"Current Date: {current_date}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Search through ALL tabs to find the answer\n"
                "2. Give a DIRECT, CONCISE answer - just the answer itself\n"
                "3. Do NOT explain your search process\n"
                "4. Do NOT say 'Source:' or cite sources explicitly - just give the answer naturally\n"
                "5. If helpful, you can naturally mention where you found it, but this is optional\n"
                "6. Keep it conversational and natural\n\n"
                "Example good response: 'You have solved 99 out of 150 Neetcode problems.'\n"
                "Example also good: 'The price is $89.99.'\n"
                "Example bad response: 'I checked Tab 1 and found... Then I looked at Tab 2... The answer is... Source: Roadmap tab.'\n\n"
                "If no information is found, simply say: 'I couldn't find the answer in your open tabs.'"
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
            f"Question: {query}\n\n"
            f"Content from {len(tab_contents)} tab(s):\n\n"
            f"{combined_content}\n\n"
            f"Chat History:\n"
            f"{chr(10).join([f'{msg['role']}: {msg['text']}' for msg in chat_history[-6:]])}\n\n"
            f"⚠️ Give a DIRECT answer immediately. Do NOT explain your search process. Do NOT say 'Source:'. Just give the answer naturally."
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
                    
                    # Clean up the answer: remove "Source:" mentions and make it more natural
                    answer = self._clean_answer(answer)
                        
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
        
        # Use raw text (already cleaned by background.js) to avoid deleting content
        text = text[:25000]  # Increased to 25k for deep analysis (Gemini can handle it)
        
        # Google search pages might have less content but still contain useful info
        is_google_search = "google.com" in url.lower() and "/search" in url.lower()
        min_content_length = 20  # Lower threshold for all tabs to ensure inclusion
        
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
                "CRITICAL INSTRUCTIONS:\n"
                "1. Search through ALL content to find the answer\n"
                "2. For chronological questions, find ALL dates/years, then identify the EARLIEST\n"
                "3. Give a DIRECT, CONCISE answer - just the answer itself\n"
                "4. Do NOT explain your search process\n"
                "5. Do NOT say 'Source:' or cite sources explicitly - just give the answer naturally\n"
                "6. Keep it conversational and natural\n\n"
                "Example good response: 'Johnny Depp's birthdate is June 9, 1963.'\n"
                "Example bad response: 'I searched through the content... I found multiple mentions... The answer is... Source: Wikipedia.'\n\n"
                "If no information is found, simply say: 'I couldn't find the answer in this tab.'"
            )
        else:
            system_prompt = (
                f"You are TabSensei, an assistant that answers questions based ONLY on the provided content.\n"
                f"Current Date: {current_date}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Search through ALL content to find the answer\n"
                "2. Give a DIRECT, CONCISE answer - just the answer itself\n"
                "3. Do NOT explain your search process\n"
                "4. Do NOT say 'Source:' or cite sources explicitly - just give the answer naturally\n"
                "5. Keep it conversational and natural\n\n"
                "Example good response: 'You have solved 99 out of 150 Neetcode problems.'\n"
                "Example bad response: 'I checked the content... I found various mentions... After analyzing... The answer is... Source: Roadmap tab.'\n\n"
                "If no information is found, simply say: 'I couldn't find the answer in this tab.'"
            )
        
        user_prompt = f"""Question: {query}

Content from: {title}
URL: {url}

{text}

Chat History:
{chr(10).join([f"{msg['role']}: {msg['text']}" for msg in chat_history[-6:]])}

⚠️ Give a DIRECT answer immediately. Do NOT explain your search process. Do NOT say 'Source:'. Just give the answer naturally."""
        
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
                    
                    # Clean up the answer: remove "Source:" mentions and make it more natural
                    answer = self._clean_answer(answer)
                        
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
    
    def _clean_answer(self, answer: str) -> str:
        """Clean up the answer to remove 'Source:' mentions and make it more natural."""
        import re
        # Remove "Source:" or "Source :" patterns (case insensitive)
        answer = re.sub(r'\s*[Ss]ource\s*:?\s*[^\n]*', '', answer, flags=re.IGNORECASE)
        # Remove standalone "Source" at the end
        answer = re.sub(r'\s+[Ss]ource\s*$', '', answer)
        # Clean up multiple spaces and newlines
        answer = re.sub(r'\s+', ' ', answer)
        answer = re.sub(r'\n\s*\n', '\n', answer)
        # Remove leading/trailing whitespace
        answer = answer.strip()
        # Remove any trailing periods that might be left after removing Source
        answer = re.sub(r'\.\s*\.+$', '.', answer)
        return answer
    
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
