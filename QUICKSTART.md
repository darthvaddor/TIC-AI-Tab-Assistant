# TabSensei Quick Start Guide

## Backend Setup

### 1. Install Dependencies

```bash
cd backend

# Using uv (recommended)
uv sync

# OR using pip
pip install -r requirements.txt
# Note: requirements.txt doesn't exist yet, install from pyproject.toml:
pip install fastapi langchain-openai langchain-groq langchain-ollama langgraph sqlalchemy python-dotenv uvicorn pydantic
```

### 2. Configure Environment

Create `backend/.env`:

```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
MODEL_TEMPERATURE=0.2
```

### 3. Initialize Database

The database auto-initializes on first run, but you can verify:

```bash
cd backend
python -c "from database.db import init_db; init_db(); print('Database initialized')"
```

### 4. Run Backend Server

```bash
cd backend
uvicorn agent_server.py:app --host 0.0.0.0 --port 8000 --reload
```

Verify it's running:
```bash
curl http://localhost:8000/health
# Should return: {"ok":true,"status":"running","provider":"openai"}
```

## Demo Mode (No Browser Required)

Test the system without a live browser:

```bash
cd backend
python demo/demo_mode.py
```

This will:
- Test tab reading
- Test tab classification
- Test price extraction
- Test price tracking
- Test alerts
- Test planner agent workflow

## Extension Setup

### 1. Load Extension in Chrome

1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (top-right toggle)
3. Click "Load unpacked"
4. Select the `extension/` folder

### 2. Pin Extension

Click the puzzle icon → Find "TabSensei" → Pin to toolbar

## Testing the Full System

### Test 1: Basic Query

1. Open 3-5 tabs (mix of shopping, research, entertainment)
2. Click the TabSensei extension icon
3. Ask: "compare my tabs"
4. Should see classification and comparison

### Test 2: Price Tracking

1. Open a shopping/product page (Amazon, Best Buy, etc.)
2. Ask: "what tabs do I have open?"
3. If price detected, you'll see "Add to Watchlist" button
4. Click it to add product
5. Check watchlist: `curl http://localhost:8000/watchlist`

### Test 3: Tab Cleanup

1. Open duplicate tabs (same URL multiple times)
2. Ask: "close duplicate tabs"
3. Should detect duplicates and suggest closing

### Test 4: Workspace Analysis

1. Open 10+ mixed tabs
2. Ask: "analyze my workspace"
3. Should show categories, duplicates, recommendations

## API Testing

### Health Check
```bash
curl http://localhost:8000/health
```

### Config Check
```bash
curl http://localhost:8000/config
```

### Watchlist
```bash
# Get all watched products
curl http://localhost:8000/watchlist

# Get price history for product ID 1
curl http://localhost:8000/watchlist/1/history?days=30
```

## Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (needs 3.10+)
- Check dependencies: `pip list | grep fastapi`
- Check .env file exists in `backend/`

**Extension can't connect:**
- Verify backend is running on port 8000
- Check browser console for CORS errors
- Verify `http://localhost:8000/health` works

**Price extraction not working:**
- Check page has visible price text
- Try different shopping sites
- Check browser console for errors

**Database errors:**
- Delete `backend/data/tabsensei.db` and restart
- Check file permissions on `backend/data/`

