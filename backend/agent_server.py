"""TabSensei: Autonomous Browser Brain - FastAPI Backend."""
from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import MODEL_PROVIDER
from database.db import init_db
from agents.simple_agent import SimpleAgent

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("tabsensei.backend")

# Initialize database
init_db()

# Initialize simple agent (fast, direct processing)
agent = SimpleAgent()

# =========================
# Pydantic Models
# =========================
class TabInput(BaseModel):
    """Input model for tab data."""
    id: int
    title: str = ""
    url: str = ""
    text: Optional[str] = Field(default="", description="Visible text from page (~4k chars)")

    @validator("text", pre=True, always=True)
    def coerce_text(cls, v: Any) -> str:
        if v is None:
            return ""
        import re
        return re.sub(r"\s+", " ", str(v)).strip()


class QueryInput(BaseModel):
    """Input model for user query."""
    query: str
    tabs: List[TabInput] = Field(default_factory=list)
    chat_history: List[Dict[str, str]] = Field(default_factory=list)


class AgentReply(BaseModel):
    """Response model from agent."""
    reply: str
    mode: str
    chosen_tab_id: Optional[int] = None
    suggested_close_tab_ids: List[int] = Field(default_factory=list)
    workspace_summary: Optional[Dict[str, Any]] = None
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    price_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    should_ask_cleanup: bool = Field(default=False, description="Whether to prompt user to close irrelevant tabs")


class WatchlistRequest(BaseModel):
    """Request to add product to watchlist."""
    product_name: str
    url: str
    price: float
    currency: str = "USD"
    alert_threshold: Optional[float] = None  # Threshold value (percentage 0-100 or absolute amount)
    threshold_type: str = "percentage"  # "percentage" or "absolute"


# =========================
# FastAPI App
# =========================
app = FastAPI(
    title="TabSensei: Autonomous Browser Brain",
    description="Multi-agent system for intelligent tab management and price tracking",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*", "http://localhost", "http://127.0.0.1", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# API Routes
# =========================
@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"ok": True, "status": "running", "provider": MODEL_PROVIDER}

@app.get("/test-llm")
def test_llm() -> Dict[str, Any]:
    """Test if LLM is working and how fast."""
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from config import get_llm, MODEL_PROVIDER, OPENAI_MODEL, GROQ_MODEL, GEMINI_MODEL, OLLAMA_MODEL
        
        llm = get_llm()  # Uses MODEL_PROVIDER from .env
        
        import time
        start = time.time()
        response = llm.invoke([SystemMessage(content="Say 'OK'"), HumanMessage(content="Test")])
        elapsed = time.time() - start
        
        # Determine which model was actually used
        if MODEL_PROVIDER == "ollama":
            model_name = OLLAMA_MODEL
        elif MODEL_PROVIDER in ["gemini", "google"]:
            model_name = GEMINI_MODEL
        elif MODEL_PROVIDER == "groq":
            model_name = GROQ_MODEL
        else:
            model_name = OPENAI_MODEL
        
        return {
            "ok": True,
            "provider": MODEL_PROVIDER,
            "model": model_name,
            "response": response.content if hasattr(response, "content") else str(response),
            "time_seconds": round(elapsed, 2)
        }
    except Exception as e:
        logger.exception("LLM test failed")
        return {"ok": False, "error": str(e)}


@app.get("/config")
def config() -> Dict[str, Any]:
    """Runtime configuration diagnostics."""
    from config import (
        OPENAI_API_KEY, GROQ_API_KEY, GOOGLE_API_KEY, OLLAMA_BASE_URL,
        OPENAI_MODEL, GROQ_MODEL, GEMINI_MODEL, OLLAMA_MODEL
    )
    
    # Determine which model is actually being used
    if MODEL_PROVIDER == "ollama":
        active_model = OLLAMA_MODEL
        active_provider = "ollama"
    elif MODEL_PROVIDER in ["gemini", "google"] and GOOGLE_API_KEY:
        active_model = GEMINI_MODEL
        active_provider = "gemini"
    elif MODEL_PROVIDER == "groq" and GROQ_API_KEY:
        active_model = GROQ_MODEL
        active_provider = "groq"
    else:
        active_model = OPENAI_MODEL
        active_provider = "openai"
    
    return {
        "provider": MODEL_PROVIDER,
        "active_provider": active_provider,
        "active_model": active_model,
        "keys_present": {
            "openai": bool(OPENAI_API_KEY),
            "groq": bool(GROQ_API_KEY),
            "gemini": bool(GOOGLE_API_KEY),
            "ollama": bool(OLLAMA_BASE_URL),
        },
        "models": {
            "openai": OPENAI_MODEL,
            "groq": GROQ_MODEL,
            "gemini": GEMINI_MODEL,
            "ollama": OLLAMA_MODEL,
        },
    }


@app.post("/run_agent", response_model=AgentReply)
async def run_agent(payload: QueryInput) -> AgentReply:
    """Main agent endpoint - processes query through multi-agent system."""
    logger.info("=" * 60)
    logger.info(">>> NEW REQUEST RECEIVED <<<")
    logger.info("=" * 60)
    
    try:
        query = (payload.query or "").strip()
        tabs = payload.tabs or []
        
        logger.info(f"Query: '{query}'")
        logger.info(f"Number of tabs: {len(tabs)}")
        if tabs:
            logger.info(f"Tab IDs: {[t.id for t in tabs]}")
            logger.info(f"Tab titles: {[t.title[:50] for t in tabs[:5]]}")

        if not query:
            return AgentReply(
                reply="Please enter a non-empty query.",
                mode="single",
                chosen_tab_id=None,
                suggested_close_tab_ids=[],
                price_info={},
                should_ask_cleanup=False,
            )

        if not tabs:
            return AgentReply(
                reply="No tabs were provided. Open some pages and try again.",
                mode="single",
                chosen_tab_id=None,
                suggested_close_tab_ids=[],
                price_info={},
                should_ask_cleanup=False,
            )

        # Convert Pydantic models to dicts
        tabs_dict = [{"id": t.id, "title": t.title, "url": t.url, "text": t.text} for t in tabs]
        
        logger.info(f"Received query: '{query}' with {len(tabs_dict)} tabs")
        logger.info(f"Tab titles: {[t.get('title', 'N/A')[:50] for t in tabs_dict[:5]]}")
        logger.info(f"Tab URLs: {[t.get('url', 'N/A')[:50] for t in tabs_dict[:5]]}")

        # Process through simple agent (fast, direct)
        try:
            import time
            start_time = time.time()
            result = agent.process(query, tabs_dict, payload.chat_history)
            elapsed = time.time() - start_time
            logger.info(f"Total processing time: {elapsed:.2f}s")
            
            if elapsed > 20:
                logger.warning(f"Processing took {elapsed:.2f}s - slower than expected")
        except Exception as e:
            logger.exception(f"Agent process failed: {e}")
            return AgentReply(
                reply=f"Error processing request: {str(e)}. Please try again.",
                mode="single",
                chosen_tab_id=None,
                suggested_close_tab_ids=[],
                price_info={},
                should_ask_cleanup=False,
            )

        logger.info(f"Processed query: {query[:50]}... | mode: {result.get('mode')}")

        return AgentReply(
            reply=result.get("reply", ""),
            mode=result.get("mode", "single"),
            chosen_tab_id=result.get("chosen_tab_id"),
            suggested_close_tab_ids=result.get("suggested_close_tab_ids", []),
            workspace_summary=result.get("workspace_summary"),
            alerts=result.get("alerts", []),
            price_info=result.get("price_info", {}),
            should_ask_cleanup=result.get("should_ask_cleanup", False),
        )

    except Exception as e:
        logger.exception("run_agent failed: %s", e)
        return AgentReply(
            reply=f"Error: {str(e)}",
            mode="single",
            chosen_tab_id=None,
            suggested_close_tab_ids=[],
            price_info={},
            should_ask_cleanup=False,
        )


@app.post("/watchlist/add")
def add_to_watchlist(request: WatchlistRequest) -> Dict[str, Any]:
    """Add product to price watchlist with optional price drop threshold."""
    try:
        from agents.price_tracking_agent import PriceTrackingAgent
        tracker = PriceTrackingAgent()
        product_id = tracker.add_to_watchlist(
            request.product_name,
            request.url,
            request.price,
            request.currency,
            alert_threshold=request.alert_threshold,
            threshold_type=request.threshold_type
        )
        return {
            "ok": True, 
            "product_id": product_id,
            "message": f"Product added to watchlist. Alert will trigger when price drops by {request.alert_threshold}{'%' if request.threshold_type == 'percentage' else ' ' + request.currency}." if request.alert_threshold else "Product added to watchlist."
        }
    except Exception as e:
        logger.error(f"Failed to add to watchlist: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/watchlist")
def get_watchlist() -> Dict[str, Any]:
    """Get all watched products."""
    try:
        from agents.price_tracking_agent import PriceTrackingAgent
        tracker = PriceTrackingAgent()
        products = tracker.get_all_watched_products()
        return {"ok": True, "products": products}
    except Exception as e:
        logger.error(f"Failed to get watchlist: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/watchlist/{product_id}/history")
def get_price_history(product_id: int, days: int = 30) -> Dict[str, Any]:
    """Get price history for a product."""
    try:
        from agents.price_tracking_agent import PriceTrackingAgent
        tracker = PriceTrackingAgent()
        history = tracker.get_price_history(product_id, days)
        trend = tracker.analyze_trend(product_id)
        return {"ok": True, "history": history, "trend": trend}
    except Exception as e:
        logger.error(f"Failed to get price history: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/alerts")
def get_alerts() -> Dict[str, Any]:
    """Get all unread price alerts."""
    try:
        from agents.alert_agent import AlertAgent
        alert_agent = AlertAgent()
        alerts = alert_agent.get_unread_alerts()
        return {"ok": True, "alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int) -> Dict[str, Any]:
    """Mark an alert as read."""
    try:
        from agents.alert_agent import AlertAgent
        alert_agent = AlertAgent()
        success = alert_agent.mark_alert_read(alert_id)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Failed to mark alert as read: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/alerts/read-all")
def mark_all_alerts_read() -> Dict[str, Any]:
    """Mark all alerts as read."""
    try:
        from agents.alert_agent import AlertAgent
        alert_agent = AlertAgent()
        count = alert_agent.mark_all_alerts_read()
        return {"ok": True, "marked_read": count}
    except Exception as e:
        logger.error(f"Failed to mark all alerts as read: {e}")
        return {"ok": False, "error": str(e)}


@app.post("/watchlist/check-prices")
def check_prices() -> Dict[str, Any]:
    """Check prices for all watched products and generate alerts.
    
    This endpoint should be called periodically (e.g., on browser startup).
    In production, this would:
    1. Open each product URL
    2. Extract current price
    3. Update price in database
    4. Generate alerts if threshold is met
    
    For now, this is a placeholder that returns products needing checks.
    """
    try:
        from agents.price_tracking_agent import PriceTrackingAgent
        tracker = PriceTrackingAgent()
        products_to_check = tracker.check_all_prices()
        return {
            "ok": True, 
            "products_to_check": products_to_check,
            "message": "Price checking initiated. In production, this would fetch prices and generate alerts."
        }
    except Exception as e:
        logger.error(f"Failed to check prices: {e}")
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
