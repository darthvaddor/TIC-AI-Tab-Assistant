# 🚀 Quick Start Guide - TabSensei Extension

## Step 1: Start the Backend Server

**In VS Code Terminal (PowerShell):**

```powershell
cd backend
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
```

**OR use the batch file:**

```powershell
.\START_SERVER.bat
```

**✅ You should see:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Keep this terminal open!** The server must be running.

---

## Step 2: Load Extension in Chrome

1. **Open Chrome** and go to: `chrome://extensions/`

2. **Enable Developer Mode** (toggle in top-right corner)

3. **Click "Load unpacked"**

4. **Navigate to:** `D:\extension-assistant\extension`
   - Select the `extension` folder (not the parent folder)

5. **✅ You should see:**
   - "TIC-AI Tab Assistant" extension loaded
   - Extension icon in Chrome toolbar

---

## Step 3: Test the Extension

### Test 1: Basic Query
1. **Open 3-5 tabs** with different websites (e.g., Google, Wikipedia, YouTube)
2. **Click the extension icon** (or press `Alt+Shift+T`)
3. **Type:** `analyze my tabs`
4. **Press Enter** or click Submit
5. **Wait for response** (should show summaries of your tabs)

### Test 2: Compare Tabs
1. **Open multiple tabs** about the same topic (e.g., 3 laptop product pages)
2. **Type:** `compare the laptops`
3. **See comparison table** and recommendation

### Test 3: Filter by Keyword
1. **Open tabs** including some Google-related pages
2. **Type:** `analyze the google tabs i have open`
3. **Should only show Google-related tabs**

---

## Step 4: Check for Errors

### If extension shows "Error" or "No response":

**Check Backend Terminal:**
- Look for error messages (red text)
- Common issues:
  - `ModuleNotFoundError` → Run: `pip install -r requirements.txt` (if exists) or install missing packages
  - `API key error` → Check `.env` file has correct `OPENAI_API_KEY` or `GROQ_API_KEY`

**Check Browser Console:**
1. **Right-click extension popup** → "Inspect"
2. **Go to Console tab**
3. **Look for errors** (red text)
4. **Look for logs** starting with `[TabSensei]` - these show what tabs were collected

**Check Network:**
1. **In DevTools** → Network tab
2. **Try query again**
3. **Look for request to** `http://localhost:8000/run_agent`
4. **Check if it returns 200 OK** or shows error

---

## Step 5: Debugging Commands

### Check if backend is running:
```powershell
# In new terminal
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

### View backend logs:
- Look at the terminal where you started the server
- You should see logs like:
  ```
  [2025-01-XX XX:XX:XX] INFO tabsensei.backend: Received query: 'analyze my tabs' with 5 tabs
  [2025-01-XX XX:XX:XX] INFO tabsensei.backend: Tab titles: ['Google', 'Wikipedia', ...]
  ```

### View extension logs:
1. **Open Chrome DevTools** (F12)
2. **Go to Console**
3. **Look for:** `[TabSensei] Collected X tabs: [...]`

---

## Troubleshooting

### Extension icon not showing?
- Check `chrome://extensions/` → Make sure extension is enabled
- Reload extension (click reload button)

### "No accessible tabs found"?
- Make sure you have regular web pages open (not `chrome://` pages)
- Try refreshing the tabs

### Backend not responding?
- Check if server is running: `curl http://localhost:8000/health`
- Check if port 8000 is blocked by firewall
- Try restarting the server

### LLM errors?
- Check `.env` file in `backend/` folder
- Make sure `OPENAI_API_KEY` or `GROQ_API_KEY` is set
- Check API key is valid (not expired/revoked)

---

## Quick Test Commands

**In VS Code Terminal (while server is running):**

```powershell
# Test backend health
curl http://localhost:8000/health

# Test with sample data (if demo mode exists)
cd backend
python demo/demo_mode.py
```

---

## Next Steps

Once it's working:
- Try different queries: `"what tabs do I have open?"`, `"compare all shopping tabs"`
- Test tab switching: Ask `"which is the best laptop?"` and see if it switches tabs
- Test cleanup: Ask `"close irrelevant tabs"` and click Yes/No

---

## Need Help?

**Check logs in:**
1. **Backend terminal** - Shows what the server is processing
2. **Browser console** (F12) - Shows what the extension is doing
3. **Extension popup DevTools** - Right-click popup → Inspect

**Common fixes:**
- Restart backend server
- Reload extension in Chrome
- Clear browser cache
- Check `.env` file has correct API keys

