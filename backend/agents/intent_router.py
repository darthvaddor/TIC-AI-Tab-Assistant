"""Intent Router: Classifies user queries to dispatch to the correct agent."""
import json
import logging
from typing import Dict, Any
from config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

class IntentRouter:
    """Classifies user queries into specific intents."""
    
    def __init__(self):
        self.llm = get_llm()
        
    def route(self, query: str) -> Dict[str, Any]:
        """
        Classifies the query into one of the following intents:
        - FACT_QUERY: Specific questions requiring external knowledge (e.g., "When was Johnny Depp born?").
        - TAB_QUERY: Questions about open tabs (e.g., "Summarize this page", "What tabs are open?").
        - TAB_ACTION: Actions on tabs (e.g., "Close all YouTube tabs").
        - PRICE_ALERT: Price tracking requests.
        - REMINDER: Reminder requests.
        - GENERAL_CHAT: Conversational queries.
        
        Returns:
            Dict with 'intent' and 'confidence'.
        """
        system_prompt = """You are an Intent Classifier for a browser assistant.
        Analyze the user's query and classify it into EXACTLY one of these categories:
        
        1. FACT_QUERY: Questions asking for specific facts, dates, names, or data that might be found in a search result or general knowledge.
           Examples: "When was Johnny Depp born?", "Capital of France?", "Who is the CEO of Google?"
           
        2. TAB_QUERY: Questions about the currently open browser tabs or their content.
           Examples: "Summarize this page", "What tabs do I have open?", "Analyze my shopping tabs", "Compare these products".
           
        3. TAB_ACTION: Requests to perform an action on tabs.
           Examples: "Close all YouTube tabs", "Group my work tabs", "Mute this tab".
           
        4. PRICE_ALERT: Requests to track prices or notify about price drops.
           Examples: "Let me know if this drops below $500", "Track this price".
           
        5. REMINDER: Requests to set a reminder or alarm.
           Examples: "Remind me in 10 minutes", "Set an alarm for 5pm".
           
        6. GENERAL_CHAT: Greetings, small talk, or vague queries.
           Examples: "Hi", "Hello", "How are you?", "Cool".
           
        Output JSON ONLY: {"intent": "CATEGORY_NAME", "confidence": 0.0-1.0}
        """
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content.strip()
            
            # Clean up potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            logger.info(f"[ROUTER] Query: '{query}' -> Intent: {result.get('intent')} ({result.get('confidence')})")
            return result
            
        except Exception as e:
            logger.error(f"[ROUTER] Classification failed: {e}")
            # Fallback to general chat or tab query depending on keywords
            if "tab" in query.lower() or "page" in query.lower():
                return {"intent": "TAB_QUERY", "confidence": 0.5}
            return {"intent": "GENERAL_CHAT", "confidence": 0.5}
