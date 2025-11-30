# How to Verify Which Model You're Using

## Method 1: Check the Config Endpoint (Recommended)

Once your server is running, visit:
```
http://localhost:8000/config
```

Or use curl:
```bash
curl http://localhost:8000/config
```

This will show:
- Current provider (ollama, groq, or openai)
- Which API keys are present
- Which model is configured for each provider

## Method 2: Test the LLM Connection

Visit:
```
http://localhost:8000/test-llm
```

Or use curl:
```bash
curl http://localhost:8000/test-llm
```

This will:
- Test if the LLM is working
- Show the provider being used
- Show response time
- Show a sample response

## Method 3: Check Your .env File

Open `backend/.env` and check:
```env
MODEL_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

## Method 4: Check Server Logs

When you start the server, look for logs that show:
- Which provider is being used
- Any connection errors

## Method 5: Check Health Endpoint

Visit:
```
http://localhost:8000/health
```

This shows the current provider.

## Quick Verification Steps:

1. **Start your server:**
   ```bash
   cd backend
   python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Open in browser:**
   - Config: http://localhost:8000/config
   - Test LLM: http://localhost:8000/test-llm
   - Health: http://localhost:8000/health

3. **Verify Ollama is running:**
   ```bash
   ollama list
   ```
   This shows installed models.

4. **Test Ollama directly:**
   ```bash
   ollama run llama3.1
   ```
   This confirms Ollama is working.

