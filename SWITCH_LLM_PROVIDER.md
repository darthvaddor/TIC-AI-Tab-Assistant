# How to Switch LLM Providers

## Quick Answer

**To switch providers, you ONLY need to change ONE line in `backend/.env`:**

```bash
MODEL_PROVIDER=openai    # For OpenAI GPT (default)
MODEL_PROVIDER=groq      # For Groq
MODEL_PROVIDER=ollama    # For local Ollama
```

Then **restart your backend server** for the change to take effect.

**That's it!** The entire codebase automatically uses the provider you specify. All agents (TabReaderAgent, TabClassifierAgent, TabSummaryAgent, PromptPlanningAgent) will automatically use the correct LLM based on `MODEL_PROVIDER` from your `.env` file.

## How It Works

The codebase uses a **centralized LLM factory function** (`get_llm()` in `backend/config.py`) that:
- Reads `MODEL_PROVIDER` from `backend/.env`
- Automatically selects the correct LLM (OpenAI, Groq, or Ollama)
- All agents use this same function, so changing `.env` affects everything

**No code changes needed** - just update `.env` and restart!

---

## Step-by-Step Guide

### 1. Create/Edit `.env` File

Create or edit `backend/.env` file (it's gitignored, so it's safe to store API keys there).

### 2. Set Your Provider

Change the `MODEL_PROVIDER` line:

#### For OpenAI (Current Default)
```bash
MODEL_PROVIDER=openai
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

**Requirements:**
- OpenAI API key from https://platform.openai.com/api-keys
- Add your API key to `backend/.env` file

#### For Local Ollama (Alternative)
```bash
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest
```

**Requirements:**
- Ollama must be installed and running
- Run `ollama serve` in a terminal
- Make sure `llama3:latest` is pulled: `ollama pull llama3:latest`

#### For Groq (Alternative)
```bash
MODEL_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key-here
GROQ_MODEL=llama-3.1-8b-instant
```

### 3. Restart Backend Server

After changing `.env`, **restart your backend server**:

**Windows (PowerShell):**
```powershell
# Stop the current server (Ctrl+C), then:
cd backend
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
```

**Or use the startup script:**
```powershell
.\START_SERVER.ps1
```

### 4. Verify It's Working

Visit `http://localhost:8000/config` in your browser to see which provider is active.

Or test the LLM directly:
```bash
curl http://localhost:8000/test-llm
```

---

## Complete `.env` Example

Here's a complete `.env` file with all options (you only need to set the ones for your chosen provider):

```bash
# ============================================
# LLM Provider Selection (CHANGE THIS!)
# ============================================
MODEL_PROVIDER=ollama

# ============================================
# Ollama (Local LLM)
# ============================================
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest

# ============================================
# OpenAI (Optional - for later)
# ============================================
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# ============================================
# Groq (Optional - for later)
# ============================================
GROQ_API_KEY=your-groq-key-here
GROQ_MODEL=llama-3.1-8b-instant

# ============================================
# General Settings
# ============================================
MODEL_TEMPERATURE=0.2
PRICE_DROP_THRESHOLD=0.1
ALERT_ENABLED=true
MEMORY_ENABLED=true
```

---

## Summary

✅ **Yes, we use `.env` files** - located at `backend/.env`

✅ **To switch providers:** Change `MODEL_PROVIDER=ollama` to `MODEL_PROVIDER=openai` or `MODEL_PROVIDER=groq`

✅ **Then restart the server** - the change takes effect immediately

✅ **No code changes needed** - the system automatically detects which provider to use based on `.env`

---

## Troubleshooting

**Q: The server still uses the old provider after changing `.env`**
- Make sure you restarted the server
- Check that `.env` is in `backend/.env` (not root directory)
- Verify the file has no syntax errors (no spaces around `=`)

**Q: How do I know which provider is active?**
- Visit `http://localhost:8000/config` to see the active provider and model

**Q: Can I have multiple providers configured at once?**
- Yes! You can have all API keys in `.env`, but only `MODEL_PROVIDER` determines which one is used.

