"""TabSummaryAgent: Generates summaries and key points."""
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_llm  # Centralized LLM factory - uses MODEL_PROVIDER from .env
import logging

logger = logging.getLogger(__name__)


class TabSummaryAgent:
    """Generates summaries and extracts key points from tabs."""
    
    def __init__(self):
        self.llm = get_llm()  # Uses MODEL_PROVIDER from .env
    
    def summarize_tab_optimized(self, tab: Dict[str, Any], query: Optional[str] = None) -> str:
        """Generate optimized summary for speed (shorter prompt, less text)."""
        title = tab.get("title", "")
        url = tab.get("url", "")
        text = (tab.get("text", "") or "")[:1500]  # Reduced for speed
        
        if len(text) < 50:
            category = tab.get("classification", {}).get("category", "unknown")
            return f"*{category.title()}* - {title}"
        
        # Better prompt for quality summaries while keeping it concise
        system_prompt = """You are TabSensei, a tab summarization assistant. Generate a clear, informative summary of the tab content.

Requirements:
- Write 2-3 complete sentences
- Focus on the main topic and key information
- Include important details or facts
- Use natural, flowing language
- Do NOT repeat the title
- Do NOT include category labels
- Do NOT use headers or formatting markers
- Just write a natural paragraph summary"""
        
        user_prompt = f"""Tab Title: {title}
Tab URL: {url}

Content:
{text[:1000]}

{f'User Query: {query}' if query else ''}

Generate a clear 2-3 sentence summary of this tab's content."""
        
        try:
            import time
            import concurrent.futures
            
            start_time = time.time()
            
            # Use ThreadPoolExecutor with timeout to prevent hanging
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.llm.invoke,
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                try:
                    response = future.result(timeout=8)  # 8 second timeout per tab (reduced for speed)
                    elapsed = time.time() - start_time
                    logger.info(f"LLM summary (optimized) took {elapsed:.2f}s for '{title[:30]}'")
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    logger.warning(f"LLM call timed out after {elapsed:.2f}s for '{title[:30]}'")
                    raise TimeoutError(f"LLM call exceeded 8 second timeout")
            
            summary = response.content if hasattr(response, "content") else str(response)
            
            # Clean up the summary - remove any unwanted formatting
            summary = summary.strip()
            # Remove title if it's repeated
            if title.lower() in summary.lower()[:len(title)+10]:
                summary = summary[len(title):].strip()
            # Remove common prefixes
            for prefix in ["Summary:", "**Summary:**", "Summary of", "This tab", "This page"]:
                if summary.lower().startswith(prefix.lower()):
                    summary = summary[len(prefix):].strip()
            
            # Ensure it's not empty
            if not summary or len(summary) < 20:
                raise ValueError("LLM returned empty or too short summary")
            
            return summary
                
        except Exception as e:
            logger.error(f"Optimized summarization failed for '{title[:30]}': {e}")
            # Fallback - create a meaningful summary from text
            text_clean = (text or "").strip()
            if text_clean:
                # Get first 2-3 meaningful sentences
                sentences = [s.strip() for s in text_clean.split('.') if s.strip() and len(s.strip()) > 20]
                if len(sentences) >= 2:
                    preview = sentences[0] + ". " + sentences[1]
                    if len(sentences) > 2 and len(preview) < 200:
                        preview += ". " + sentences[2]
                    return preview[:300] + ("..." if len(preview) > 300 else "")
                elif sentences:
                    return sentences[0][:250] + ("..." if len(sentences[0]) > 250 else "")
                else:
                    return text_clean[:200] + "..."
            category = tab.get("classification", {}).get("category", "unknown")
            return f"*{category.title()}* - {title}"
    
    def summarize_tab(self, tab: Dict[str, Any], query: Optional[str] = None) -> str:
        """Generate summary for a single tab."""
        title = tab.get("title", "")
        url = tab.get("url", "")
        text = (tab.get("text", "") or "")[:4000]  # Reduced from 8000 to speed up
        
        # Quick fallback: if text is too short, just return basic info
        if len(text) < 100:
            return f"**{title}**\n\nURL: {url}\n\n*Content too short to summarize.*"
        
        system_prompt = """You are TabSensei, a tab summarization assistant. Generate a concise, informative summary of the tab content.

Focus on:
- Main topic/subject
- Key information or facts
- Important details relevant to the user

Keep it under 100 words. Use clear, natural language. Be brief and to the point. 
Do NOT repeat the title or URL.
Do NOT include category labels like "Research", "Shopping", etc.
Do NOT use headers like "Summary" or "Main Topic" - just write naturally."""
        
        user_prompt = f"""Tab Title: {title}
Tab URL: {url}

Content:
{text[:3000]}

{f'User Query: {query}' if query else ''}

Generate a brief summary."""
        
        try:
            # Add timeout protection
            import time
            start_time = time.time()
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            elapsed = time.time() - start_time
            logger.info(f"LLM summary took {elapsed:.2f}s")
            
            if elapsed > 30:
                logger.warning(f"LLM call took {elapsed:.2f}s - very slow!")
            
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback summary - create a clean summary from text
            text_clean = (text or "").strip()
            if text_clean:
                # Get first meaningful sentence
                sentences = [s.strip() for s in text_clean.split('.') if s.strip() and len(s.strip()) > 20]
                preview = sentences[0][:200] if sentences else text_clean[:200]
                return f"{preview}..."
            return f"*Content unavailable*"
    
    def extract_key_points(self, tab: Dict[str, Any], max_points: int = 5) -> List[str]:
        """Extract key points from tab content."""
        title = tab.get("title", "")
        text = (tab.get("text", "") or "")[:4000]
        
        system_prompt = f"""Extract exactly {max_points} key points from the content. Return as a JSON array of strings."""
        
        user_prompt = f"""Title: {title}
Content: {text[:3000]}

Extract {max_points} key points."""
        
        try:
            response = self.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            content = response.content if hasattr(response, "content") else str(response)
            # Simple extraction - in production, parse JSON properly
            points = [line.strip("- •") for line in content.split("\n") if line.strip()][:max_points]
            return points
        except Exception as e:
            logger.error(f"Key point extraction failed: {e}")
            return []


