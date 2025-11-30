"""Configuration management for TabSensei."""
import os
from pathlib import Path
from typing import Optional, Any
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# LLM Configuration
MODEL_PROVIDER: str = os.getenv("MODEL_PROVIDER", "openai").lower()  # Default to OpenAI
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_ORG_ID: Optional[str] = os.getenv("OPENAI_ORG_ID")
GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-pro")  # Default Gemini model
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3:latest")  # Default Ollama model
MODEL_TEMPERATURE: float = float(os.getenv("MODEL_TEMPERATURE", "0.2"))


def get_llm(temperature: Optional[float] = None) -> Any:
    """
    Get LLM instance based on MODEL_PROVIDER from .env file.
    
    This is the SINGLE SOURCE OF TRUTH for LLM provider selection.
    All agents should use this function to get their LLM instance.
    
    Args:
        temperature: Optional temperature override. Defaults to MODEL_TEMPERATURE from config.
    
    Returns:
        LLM instance (ChatOpenAI, ChatGroq, ChatGoogleGenerativeAI, or ChatOllama)
    
    Raises:
        ValueError: If MODEL_PROVIDER is invalid or required API keys are missing.
    """
    if temperature is None:
        temperature = MODEL_TEMPERATURE
    
    provider = MODEL_PROVIDER.lower()
    
    if provider == "gemini" or provider == "google":
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY (or GEMINI_API_KEY) not found in environment. Set it in backend/.env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=temperature,
            timeout=10  # 10 second timeout
        )
    
    elif provider == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in environment. Set it in backend/.env")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=GROQ_MODEL, 
            api_key=GROQ_API_KEY, 
            temperature=temperature,
            timeout=10  # 10 second timeout
        )
    
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=OLLAMA_MODEL, 
            base_url=OLLAMA_BASE_URL, 
            temperature=temperature,
            timeout=10  # 10 second timeout
        )
    
    elif provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not found in environment. Set it in backend/.env")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            organization=OPENAI_ORG_ID,
            temperature=temperature,
            timeout=10,  # 10 second timeout for API calls
            max_retries=1  # Only retry once
        )
    
    else:
        raise ValueError(
            f"Invalid MODEL_PROVIDER: '{provider}'. "
            f"Must be one of: 'openai', 'groq', 'gemini', 'google', 'ollama'. "
            f"Set MODEL_PROVIDER in backend/.env file."
        )

# Database Configuration
DB_PATH: Path = Path(__file__).parent / "data" / "tabsensei.db"
DB_PATH.parent.mkdir(exist_ok=True)

# Price Tracking
PRICE_DROP_THRESHOLD: float = float(os.getenv("PRICE_DROP_THRESHOLD", "0.1"))  # 10% drop
ALERT_ENABLED: bool = os.getenv("ALERT_ENABLED", "true").lower() == "true"

# Tab Classification
CLASSIFICATION_CATEGORIES = [
    "research",
    "shopping",
    "entertainment",
    "work",
    "distraction",
    "duplicate",
    "unknown"
]

# Memory
MEMORY_ENABLED: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
SESSION_MEMORY_PATH: Path = Path(__file__).parent / "data" / "session_memory.json"
LONG_TERM_MEMORY_PATH: Path = Path(__file__).parent / "data" / "long_term_memory.json"


