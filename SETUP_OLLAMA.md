# How to Use Local Ollama Model

## Step 1: Install and Start Ollama

1. **Download Ollama:**
   - Visit: https://ollama.ai
   - Download and install for Windows

2. **Start Ollama Service:**
   - Ollama should start automatically after installation
   - Or run: `ollama serve` in a terminal

3. **Pull a Model:**
   ```bash
   ollama pull llama3.1
   ```
   Or use another model:
   ```bash
   ollama pull llama3.2
   ollama pull mistral
   ollama pull phi3
   ```

4. **Verify Ollama is Running:**
   ```bash
   ollama list
   ```
   This shows all installed models.

## Step 2: Configure Your .env File

Open `backend/.env` and make sure it has:
```env
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

## Step 3: Start the Backend Server

**Option A: Using the batch file (Windows)**
- Double-click `START_SERVER.bat` in the project root

**Option B: Using PowerShell**
- Run `START_SERVER.ps1` in PowerShell

**Option C: Manual command**
```bash
cd backend
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
```

## Step 4: Verify Everything is Working

1. **Check if server is running:**
   - Open: http://localhost:8000/health
   - Should show: `{"ok": true, "status": "running", "provider": "ollama"}`

2. **Check configuration:**
   - Open: http://localhost:8000/config
   - Should show: `"provider": "ollama"` and `"active_model": "llama3.1"`

3. **Test LLM connection:**
   - Open: http://localhost:8000/test-llm
   - Should show a successful response with timing

## Troubleshooting

### "ERR_CONNECTION_REFUSED"
- **Problem:** Backend server isn't running
- **Solution:** Start the server using one of the methods above

### "Connection refused" to Ollama
- **Problem:** Ollama service isn't running
- **Solution:** 
  - Check if Ollama is installed: `ollama --version`
  - Start Ollama: `ollama serve`
  - Or restart the Ollama service from Windows Services

### "Model not found"
- **Problem:** Model isn't installed
- **Solution:** Run `ollama pull llama3.1` (or your chosen model)

### Port 8000 already in use
- **Problem:** Another service is using port 8000
- **Solution:** 
  - Stop the other service, OR
  - Change port in the command: `--port 8001`

## Quick Start Commands

```bash
# 1. Start Ollama (if not already running)
ollama serve

# 2. Pull model (if not already installed)
ollama pull llama3.1

# 3. Start backend server
cd backend
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
```

## Verify Model is Working

Once the server is running, test it:
- Browser: http://localhost:8000/test-llm
- Should return: `{"ok": true, "provider": "ollama", "model": "llama3.1", ...}`

