# Quick Test Commands for VS Code Terminal

## Step 1: Start Backend Server

Open VS Code terminal (Ctrl+`) and run:

```bash
cd backend
uvicorn agent_server.py:app --host 0.0.0.0 --port 8000 --reload
```

**Keep this terminal open!** The server will keep running.

## Step 2: Verify Backend is Running

Open a NEW terminal in VS Code (Terminal → New Terminal) and run:

```bash
curl http://localhost:8000/health
```

You should see: `{"ok":true,"status":"running",...}`

## Step 3: Load Extension in Chrome

1. Open Chrome → Go to `chrome://extensions/`
2. Enable **Developer mode** (toggle top-right)
3. Click **"Load unpacked"**
4. Navigate to: `D:\extension-assistant\extension`
5. Extension should appear in your list

## Step 4: Test the Extension

1. **Open 3-5 tabs** in Chrome (mix of shopping, research, news)
2. **Click the TabSensei extension icon** (top toolbar)
3. **Type a query** like:
   - "compare my tabs"
   - "what tabs do I have open?"
   - "analyze my workspace"

## Step 5: Test Price Tracking (Optional)

1. Open a shopping page (Amazon, Best Buy, etc.)
2. Ask: "what tabs do I have open?"
3. If price detected, you'll see "Add to Watchlist" button
4. Click it to add product

## Quick Health Check Commands

```bash
# Check backend health
curl http://localhost:8000/health

# Check config
curl http://localhost:8000/config

# View watchlist (after adding products)
curl http://localhost:8000/watchlist
```

## Troubleshooting

**Backend won't start?**
```bash
cd backend
python -m pip install fastapi uvicorn langchain-openai sqlalchemy python-dotenv
```

**Extension can't connect?**
- Make sure backend is running on port 8000
- Check browser console (F12 → Console tab)
- Verify: `curl http://localhost:8000/health` works

**No response from extension?**
- Check backend terminal for errors
- Check browser console (F12)
- Make sure `.env` file exists in `backend/` with your API key

