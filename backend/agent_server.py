# agent_server.py
# TIC-AI Tab Assistant — FastAPI backend
# --------------------------------------
# Env (.env alongside this file):
#   MODEL_PROVIDER=openai|groq|ollama
#   OPENAI_API_KEY=...
#   OPENAI_MODEL=gpt-4o-mini
#   OPENAI_ORG_ID=org_xxx            # optional
#   GROQ_API_KEY=...
#   GROQ_MODEL=llama-3.1-70b-versatile
#   OLLAMA_BASE_URL=http://localhost:11434
#   OLLAMA_MODEL=llama3.1
#   MODEL_TEMPERATURE=0.2
#
# Contract (POST /run_agent):
#   request: { "query": str, "tabs": [{id:int,title:str,url:str,text:str<=~4000}, ...] }
#   response: {
#     "reply": str,                      # markdown
#     "mode": "single"|"multi"|"cleanup",
#     "chosen_tab_id": int | null,
#     "suggested_close_tab_ids": [int, ...]
#   }

from __future__ import annotations

import os
import re
import math
import logging
from typing import List, Optional, Dict, Any, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

# ---- Load environment variables next to this file ----
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

# ---- LangChain LLM clients (provider selectable by env) ----
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


# =========================
# Logging
# =========================
logger = logging.getLogger("ticai.backend")
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


# =========================
# Pydantic models
# =========================
class TabInput(BaseModel):
    id: int
    title: str = ""
    url: str = ""
    text: Optional[str] = Field(default="", description="Visible text from page (~4k chars)")

    @validator("text", pre=True, always=True)
    def coerce_text(cls, v: Any) -> str:
        if v is None:
            return ""
        # normalize whitespace; keep lightweight
        return re.sub(r"\s+", " ", str(v)).strip()


class QueryInput(BaseModel):
    query: str
    tabs: List[TabInput] = Field(default_factory=list)


class AgentReply(BaseModel):
    reply: str
    mode: str
    chosen_tab_id: Optional[int] = None
    suggested_close_tab_ids: List[int] = Field(default_factory=list)


# =========================
# FastAPI app & CORS
# =========================
app = FastAPI(
    title="TIC-AI Tab Assistant Backend",
    description="Grounded, tab-local reasoning for Chrome extension",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*", "http://localhost", "http://127.0.0.1", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Model selection
# =========================
def pick_llm():
    # Prefer explicit provider; otherwise choose based on available keys (Groq first)
    env_provider = os.getenv("MODEL_PROVIDER", "").strip().lower()
    temperature = float(os.getenv("MODEL_TEMPERATURE", "0.2"))

    if env_provider:
        provider = env_provider
    else:
        provider = "openai"
        if os.getenv("GROQ_API_KEY"):
            provider = "groq"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("OLLAMA_BASE_URL"):
            provider = "ollama"

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        # Default to a supported model; remap deprecated names
        model = os.getenv("GROQ_MODEL", "llama-3.1-70b")
        deprecated_map = {
            "llama-3.1-70b-versatile": "llama-3.1-70b",
        }
        if model in deprecated_map:
            logger.warning(f"Groq model '{model}' is deprecated. Switching to '{deprecated_map[model]}'.")
            model = deprecated_map[model]
        if not api_key:
            logger.warning("GROQ_API_KEY missing; Groq requests will fail.")
        logger.info(f"Using Groq model: {model}")
        return ChatGroq(model=model, api_key=api_key, temperature=temperature)

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        logger.info(f"Using Ollama model: {model} @ {base_url}")
        return ChatOllama(model=model, base_url=base_url, temperature=temperature)

    # default: OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    org_id = os.getenv("OPENAI_ORG_ID", "").strip() or None
    if not api_key:
        logger.warning("OPENAI_API_KEY missing; OpenAI requests will fail.")
    logger.info(f"Using OpenAI model: {model}{' (org set)' if org_id else ''}")
    return ChatOpenAI(model=model, api_key=api_key, organization=org_id, temperature=temperature)


LLM = pick_llm()


def llm_complete(system: str, user: str, max_chars: int = 4000) -> str:
    """
    Safe wrapper that truncates user content, catches errors,
    and always returns plain text.
    """
    try:
        user = user[:max_chars]
        msg = LLM.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return getattr(msg, "content", str(msg)) or ""
    except Exception as e:
        logger.exception("LLM invocation failed: %s", e)
        return "Error: language model unavailable. Please try again."


# =========================
# Lightweight text scoring
# =========================
WORD_RE = re.compile(r"[A-Za-z0-9]+")


def toks(s: str) -> List[str]:
    return [t.lower() for t in WORD_RE.findall(s or "")]


def overlap_score(q_tokens: List[str], c_tokens: List[str]) -> float:
    if not q_tokens or not c_tokens:
        return 0.0
    q, c = set(q_tokens), set(c_tokens)
    # Cosine-like overlap using set intersection size normalized by lengths.
    return len(q & c) / math.sqrt(len(q) * len(c))


def make_tab_tokens(tab: TabInput) -> List[str]:
    # Title + URL + first ~2k chars of text for ranking
    base = f"{tab.title} {tab.url} " + (tab.text or "")[:2000]
    return toks(base)


# =========================
# Mode detection
# =========================
def detect_mode(query: str) -> str:
    q = (query or "").lower()

    multi_markers = [
        "compare", "versus", "vs", "difference",
        "which is better", "which one is better", "pros and cons",
        "rank", "top", "best among", "side by side"
    ]
    cleanup_markers = [
        "close others", "close remaining", "keep only", "show me only",
        "focus on", "filter to", "hide the rest", "remove other"
    ]
    single_markers = [
        "who are", "what is", "when did", "how many", "explain", "summarize", "details on",
        "members of", "specs of", "price of", "definition of"
    ]

    if any(m in q for m in multi_markers):
        return "multi"
    if any(m in q for m in cleanup_markers):
        return "cleanup"
    if any(m in q for m in single_markers) or "which tab" in q or "find the tab" in q:
        return "single"

    # Default heuristic: if question references a specific noun phrase,
    # treat as single; otherwise, multi (safer for comparisons).
    return "single"


# =========================
# Tab ranking & utilities
# =========================
def rank_tabs(query: str, tabs: List[TabInput], top_k: int = 6) -> List[Tuple[TabInput, float]]:
    q_tokens = toks(query)
    scored: List[Tuple[TabInput, float]] = []

    for t in tabs:
        score = overlap_score(q_tokens, make_tab_tokens(t))
        scored.append((t, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    # keep non-zero hits; if none, keep top two anyway
    nz = [(t, s) for (t, s) in scored if s > 0]
    return nz[:top_k] if nz else scored[: min(top_k, len(scored))]


def summarize_tab_content(tab: TabInput, query: str) -> str:
    system = (
        "You are TIC-AI, a tab-local assistant. Answer ONLY using the provided tab excerpt. "
        "If the excerpt lacks the answer, say what’s missing concisely. "
        "Respond in clean, compact Markdown (no external sources; no speculation)."
    )
    user = (
        f"User question: {query}\n\n"
        f"Tab title: {tab.title}\nTab URL: {tab.url}\n\n"
        f"Visible text (truncated):\n{(tab.text or '')[:8000]}"
    )
    return llm_complete(system, user)


def compare_tabs(query: str, tabs: List[TabInput]) -> tuple[str, Optional[int]]:
    """
    Compare multiple relevant tabs and synthesize a grounded Markdown summary.
    Returns a tuple of (markdown_reply, chosen_tab_id).
    """

    # rank_tabs() sometimes returns list[(TabInput, float)], normalize that
    ranked = rank_tabs(query, tabs)
    rel_tabs = [t[0] if isinstance(t, tuple) else t for t in ranked]

    if not rel_tabs:
        return ("No relevant tabs found for comparison.", None)

    # System message to instruct the LLM to stay grounded
    sys_prompt = (
        "You are TIC-AI, a tab comparison assistant. Compare the following open tabs "
        "**strictly using their provided text**. Create a clean Markdown table using | separators "
        "with proper headers and aligned columns. After the table, write a short summary "
        "and end with an explicit line like: 'Recommendation: <exact tab title>'."
    )

    # Combine tab texts (trimmed for token safety)
    joined = "\n\n".join(
        [
            f"---\nTitle: {t.title}\nURL: {t.url}\nText:\n{(t.text or '')[:3000]}"
            for t in rel_tabs
        ]
    )

    # Run model
    res = LLM.invoke(
        [
            HumanMessage(
                content=f"{sys_prompt}\n\nUser Query: {query}\n\n{joined}"
            )
        ]
    )
    reply = res.content if hasattr(res, "content") else str(res)

    # --- Detect which tab was recommended (LLM-specified title match)
    chosen: Optional[TabInput] = None
    rec_title = None
    # Try to parse a line like: Recommendation: <title>
    for line in (reply or "").splitlines():
        if line.lower().startswith("recommendation:"):
            rec_title = line.split(":", 1)[1].strip()
            break
    if rec_title:
        lt = rec_title.lower()
        # Exact/substring match on tab titles first
        for t in rel_tabs:
            if (t.title or "").lower() == lt or lt in (t.title or "").lower():
                chosen = t
                break
        # Fallback: first token match
        if not chosen:
            first_tok = lt.split()[0] if lt else None
            if first_tok:
                for t in rel_tabs:
                    if first_tok in (t.title or "").lower():
                        chosen = t
                        break
    # Heuristic fallback if no explicit recommendation parsed
    if not chosen:
        for t in rel_tabs:
            if t.title and t.title.lower().split()[0] in (reply or "").lower():
                chosen = t
                break

    chosen_id = chosen.id if chosen else (rel_tabs[0].id if rel_tabs else None)
    return (reply, chosen_id)




def cleanup_tabs(query: str, tabs: List[TabInput]) -> Tuple[List[TabInput], List[int]]:
    """
    Decide which tabs match the user's focus filter; return (kept_tabs, close_ids).
    We treat the 'ranked top' as the likely primary tab to keep active.
    """
    ranked = rank_tabs(query, tabs, top_k=len(tabs))
    if not ranked:
        return [], []

    # Keep non-zero matches; if all zeros, keep the top-1
    matches = [t for (t, s) in ranked if s > 0] or [ranked[0][0]]
    match_ids = {t.id for t in matches}
    to_close = [t.id for t in tabs if t.id not in match_ids]
    return matches, to_close


# =========================
# API routes
# =========================
@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "status": "running"}


@app.get("/config")
def config() -> Dict[str, Any]:
    """Runtime diagnostic: shows which provider/model is configured (no secrets)."""
    provider = os.getenv("MODEL_PROVIDER", "").strip().lower() or None
    openai_key = bool(os.getenv("OPENAI_API_KEY"))
    groq_key = bool(os.getenv("GROQ_API_KEY"))
    ollama_url = os.getenv("OLLAMA_BASE_URL") or None
    selected = type(LLM).__name__ if LLM else None
    # Try to infer model name from env, not from client
    model_env = (
        os.getenv("GROQ_MODEL")
        if (provider == "groq" or (not provider and groq_key)) else (
            os.getenv("OPENAI_MODEL") if (provider == "openai" or openai_key) else (
                os.getenv("OLLAMA_MODEL") if (provider == "ollama" or ollama_url) else None
            )
        )
    )
    return {
        "provider_env": provider,
        "keys_present": {"openai": openai_key, "groq": groq_key, "ollama": bool(ollama_url)},
        "selected_client": selected,
        "model_env": model_env,
    }


@app.post("/run_agent", response_model=AgentReply)
def run_agent(payload: QueryInput) -> AgentReply:
    try:
        query = (payload.query or "").strip()
        tabs = payload.tabs or []

        if not query:
            return AgentReply(
                reply="Please enter a non-empty query.",
                mode="single",
                chosen_tab_id=None,
                suggested_close_tab_ids=[],
            )

        if not tabs:
            return AgentReply(
                reply="No tabs were provided by the extension. Open some pages and try again.",
                mode="single",
                chosen_tab_id=None,
                suggested_close_tab_ids=[],
            )

        mode = detect_mode(query)
        logger.info("Mode detected: %s | received %d tabs", mode, len(tabs))

        # ---- SINGLE-TAB REASONING ----
        if mode == "single":
            ranked = rank_tabs(query, tabs, top_k=3)
            if not ranked:
                return AgentReply(
                    reply="I couldn’t match your question to any open tab.",
                    mode="single",
                    chosen_tab_id=None,
                    suggested_close_tab_ids=[],
                )
            top_tab = ranked[0][0]
            logger.info("Single mode → chosen tab id=%s title=%s", top_tab.id, top_tab.title[:80])
            answer = summarize_tab_content(top_tab, query)
            return AgentReply(
                reply=answer,
                mode="single",
                chosen_tab_id=top_tab.id,
                suggested_close_tab_ids=[],
            )

        # ---- MULTI-TAB COMPARISON ----
        if mode == "multi":
            ranked = rank_tabs(query, tabs, top_k=6)
            if not ranked:
                return AgentReply(
                    reply="I couldn’t find multiple relevant tabs to compare.",
                    mode="multi",
                    chosen_tab_id=None,
                    suggested_close_tab_ids=[],
                )
            relevant_tabs = [t for (t, _) in ranked]
            reply_text, chosen_id = compare_tabs(query, relevant_tabs)

            # Fallback if compare didn't identify a tab
            if chosen_id is None:
                chosen_id = relevant_tabs[0].id

            logger.info("Multi mode → recommending tab id=%s", chosen_id)

            return AgentReply(
                reply=reply_text,
                mode="multi",
                chosen_tab_id=chosen_id,
                suggested_close_tab_ids=[],
            )

        # ---- TAB CLEANUP / FOCUS ----
        if mode == "cleanup":
            kept_tabs, to_close = cleanup_tabs(query, tabs)
            if not kept_tabs:
                return AgentReply(
                    reply="I couldn’t find a set of tabs that match your filter.",
                    mode="cleanup",
                    chosen_tab_id=None,
                    suggested_close_tab_ids=[],
                )
            # Choose the first kept tab as the primary focus
            chosen = kept_tabs[0]
            # Compose a brief grounded summary for the chosen tab to explain the pick
            summary = summarize_tab_content(chosen, f"Summarize how this tab relates to: {query}")
            reply = (
                f"**Focus tabs ({len(kept_tabs)} match)** — I’ll keep these open and suggest closing the rest.\n\n"
                f"**Primary tab to focus:** [{chosen.title}]({chosen.url})\n\n"
                f"{summary}\n\n"
                f"_You will be prompted to confirm closing {len(to_close)} unrelated tab(s) in the extension UI._"
            )
            logger.info(
                "Cleanup mode → kept=%d close=%d (chosen id=%s)",
                len(kept_tabs), len(to_close), chosen.id
            )
            return AgentReply(
                reply=reply,
                mode="cleanup",
                chosen_tab_id=chosen.id,
                suggested_close_tab_ids=to_close,
            )

        # Fallback (shouldn’t hit)
        logger.warning("Unknown mode; defaulting to single.")
        ranked = rank_tabs(query, tabs, top_k=1)
        chosen = ranked[0][0] if ranked else None
        answer = summarize_tab_content(chosen, query) if chosen else "No relevant tab found."
        return AgentReply(
            reply=answer,
            mode="single",
            chosen_tab_id=chosen.id if chosen else None,
            suggested_close_tab_ids=[],
        )

    except Exception as e:
        logger.exception("run_agent failed: %s", e)
        return AgentReply(
            reply=f"Error: {str(e)}",
            mode="single",
            chosen_tab_id=None,
            suggested_close_tab_ids=[],
        )
