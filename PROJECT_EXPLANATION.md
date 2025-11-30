# 📚 TabSensei Project - Complete Explanation

## 🎯 What This Project Does (In Simple Terms)

**TabSensei** is like having a smart assistant that:
1. **Reads all your open browser tabs** (like "Laptop 1", "Laptop 2", "Laptop 3")
2. **Understands what's in each tab** using AI
3. **Answers your questions** about those tabs (e.g., "Which laptop is best?")
4. **Switches to the most relevant tab** automatically
5. **Tracks prices** if you're shopping (e.g., "Alert me when this laptop price drops")
6. **Helps you clean up** by suggesting which tabs to close

**Key Point**: It ONLY uses information from your open tabs. It doesn't search the internet.

---

## 🏗️ Architecture Overview

Your project has **2 main parts**:

```
┌─────────────────────────────────────────────────────────┐
│                    CHROME EXTENSION                     │
│  (Frontend - What you see and interact with)            │
│                                                          │
│  • Popup Window (chat interface)                        │
│  • Background Service Worker (collects tab data)        │
│  • Content Scripts (injects overlay into web pages)     │
└──────────────────┬───────────────────────────────────────┘
                   │
                   │ HTTP Request (sends query + tab data)
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│              FASTAPI BACKEND SERVER                      │
│  (Backend - The "brain" that processes everything)      │
│                                                          │
│  • Receives query + tab data                            │
│  • Uses AI agents to analyze tabs                        │
│  • Returns answer + recommendations                      │
│  • Stores price history in SQLite database              │
└──────────────────┬───────────────────────────────────────┘
                   │
                   │ HTTP Response (answer + actions)
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│              CHROME EXTENSION (again)                    │
│                                                          │
│  • Displays answer in chat                               │
│  • Switches to recommended tab                           │
│  • Shows price alerts                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure Explained

```
extension-assistant/
│
├── extension/                    # Chrome Extension (Frontend)
│   ├── manifest.json             # Extension configuration
│   ├── background.js             # Service worker - collects tab data
│   ├── content/
│   │   └── overlay.js            # Injects chat window into web pages
│   └── popup/
│       ├── panel.html            # Chat UI HTML
│       ├── panel.js              # Chat logic (sends queries, displays answers)
│       └── panel.css             # Styling
│
└── backend/                      # Python Backend (The Brain)
    ├── agent_server.py           # FastAPI server (main entry point)
    ├── config.py                 # Configuration (API keys, model settings)
    ├── .env                      # Your API keys (OpenAI, Groq, etc.)
    │
    ├── agents/                   # AI Agents (specialized workers)
    │   ├── planner_agent.py     # 🎯 Orchestrator - coordinates all agents
    │   ├── tab_reader_agent.py  # 📖 Reads and extracts tab content
    │   ├── tab_classifier_agent.py  # 🏷️ Categorizes tabs (shopping, research, etc.)
    │   ├── tab_summary_agent.py # 📝 Generates summaries
    │   ├── price_extraction_agent.py  # 💰 Extracts prices from shopping pages
    │   ├── price_tracking_agent.py    # 📊 Tracks price history
    │   ├── alert_agent.py        # 🔔 Creates price drop alerts
    │   └── memory_agent.py       # 🧠 Remembers user preferences
    │
    ├── database/                 # Database (stores data)
    │   ├── db.py                 # Database connection
    │   └── models.py             # Data models (WatchedProduct, PriceHistory, etc.)
    │
    └── utils/                    # Helper functions
        ├── text_utils.py         # Text processing (tokenization, similarity)
        └── price_utils.py        # Price parsing (extract $123.45 from text)
```

---

## 🔄 How It Works (Step-by-Step)

### Example: User asks "Compare 3 laptops"

#### **Step 1: User Opens Extension**
- User clicks extension icon → Chat window opens
- User types: "Compare 3 laptops"

#### **Step 2: Extension Collects Tab Data**
- `background.js` (service worker) runs
- It visits each open tab and extracts:
  - Tab title (e.g., "Dell Laptop - Amazon")
  - Tab URL (e.g., "https://amazon.com/dell-laptop")
  - Page text content (first 4000 characters)
  - Price (if it's a shopping page)

#### **Step 3: Extension Sends Data to Backend**
- Extension sends HTTP POST request to `http://localhost:8000/run_agent`
- Payload:
  ```json
  {
    "query": "Compare 3 laptops",
    "tabs": [
      {"id": 1, "title": "Dell Laptop", "url": "...", "text": "..."},
      {"id": 2, "title": "Lenovo Laptop", "url": "...", "text": "..."},
      {"id": 3, "title": "MacBook", "url": "...", "text": "..."}
    ]
  }
  ```

#### **Step 4: Backend Processes with AI Agents**

The `PlannerAgent` orchestrates a workflow using **LangGraph**:

```
┌─────────────────────────────────────────────────────────┐
│  PlannerAgent Workflow (LangGraph)                       │
│                                                           │
│  1. read_tabs          → Extract text from tabs          │
│  2. classify_tabs      → Categorize (shopping/research)  │
│  3. extract_prices    → Find prices in shopping tabs    │
│  4. generate_summaries → Create summaries using AI       │
│  5. analyze_workspace  → Understand overall tab context  │
│  6. check_alerts       → Check for price drops           │
│  7. save_memory        → Remember this session           │
│  8. generate_reply     → Create final answer             │
└─────────────────────────────────────────────────────────┘
```

**What each agent does:**

1. **TabReaderAgent**: 
   - Takes raw tab data
   - Extracts and cleans text content
   - Output: Clean, normalized tab data

2. **TabClassifierAgent**:
   - Uses AI (Groq/OpenAI) to categorize each tab
   - Categories: `research`, `shopping`, `entertainment`, `work`, `distraction`, `duplicate`, `unknown`
   - Also detects duplicate tabs

3. **PriceExtractionAgent**:
   - Looks for shopping pages
   - Extracts product name and price
   - Uses regex patterns to find prices like "$1,299.99"

4. **TabSummaryAgent**:
   - Uses AI to generate concise summaries
   - Each tab gets a 100-word summary
   - Focuses on key information

5. **PriceTrackingAgent**:
   - Stores watched products in SQLite database
   - Tracks price history over time
   - Detects price drops

6. **AlertAgent**:
   - Checks if any watched products had price drops
   - Creates alerts if price dropped >10%

7. **MemoryAgent**:
   - Saves session data to database
   - Remembers user preferences
   - Learns patterns (e.g., "user often shops for laptops")

8. **PlannerAgent**:
   - **The Boss** - coordinates all other agents
   - Uses LangGraph to create a workflow
   - Decides which tabs are most relevant
   - Generates final answer

#### **Step 5: Backend Returns Answer**

```json
{
  "reply": "## Comparison of 3 Laptops\n\n1. **Dell Laptop** - $1,299\n2. **Lenovo Laptop** - $899\n3. **MacBook** - $1,599\n\n**Recommendation**: Lenovo (best value)",
  "mode": "multi",
  "chosen_tab_id": 2,  // Switch to Lenovo tab
  "suggested_close_tab_ids": [],  // No tabs to close
  "price_info": {
    "2": {"product_name": "Lenovo Laptop", "price": 899, "currency": "USD"}
  }
}
```

#### **Step 6: Extension Displays Answer**
- `panel.js` receives the response
- Displays markdown-formatted answer in chat
- Shows "Add to Watchlist" button for shopping tabs
- Automatically switches to tab ID 2 (Lenovo)

#### **Step 7: User Can Take Actions**
- Click "Add to Watchlist" → Price gets tracked
- Ask follow-up: "What if price is no constraint?" → Backend re-analyzes
- Click "Close unrelated tabs" → Extension closes suggested tabs

---

## 🤖 The AI Agents Explained

### **PlannerAgent** (The Orchestrator)
- **Role**: Boss of all agents
- **Tool**: LangGraph (creates workflow)
- **What it does**:
  - Receives user query + tabs
  - Decides which agents to run
  - Coordinates the workflow
  - Generates final answer

### **TabReaderAgent** (The Reader)
- **Role**: Extracts content from tabs
- **What it does**:
  - Takes raw tab data (title, URL, text)
  - Cleans and normalizes text
  - Limits text to 4000 characters
  - Validates tabs (skips chrome:// pages)

### **TabClassifierAgent** (The Categorizer)
- **Role**: Understands what each tab is about
- **Uses**: AI (Groq/OpenAI) to classify
- **What it does**:
  - Sends tab content to AI
  - AI returns: category + confidence + reason
  - Also detects duplicate tabs

### **TabSummaryAgent** (The Summarizer)
- **Role**: Creates short summaries
- **Uses**: AI (Groq/OpenAI)
- **What it does**:
  - Sends tab content to AI
  - AI generates 100-word summary
  - Focuses on key information

### **PriceExtractionAgent** (The Price Finder)
- **Role**: Finds prices on shopping pages
- **Uses**: Regex patterns (no AI needed)
- **What it does**:
  - Detects shopping pages (Amazon, eBay, etc.)
  - Extracts price using regex: `\$(\d+(?:,\d{3})*(?:\.\d{2})?)`
  - Extracts product name from title/text

### **PriceTrackingAgent** (The Price Tracker)
- **Role**: Tracks price history
- **Uses**: SQLite database
- **What it does**:
  - Stores watched products
  - Records price history (date + price)
  - Analyzes trends (is price going up/down?)
  - Detects price drops

### **AlertAgent** (The Notifier)
- **Role**: Creates alerts for price drops
- **What it does**:
  - Checks watched products
  - Compares current price vs. previous price
  - If drop >10%, creates alert

### **MemoryAgent** (The Rememberer)
- **Role**: Stores user preferences and sessions
- **Uses**: SQLite database
- **What it does**:
  - Saves tab sessions
  - Remembers user preferences
  - Learns recurring interests
  - Stores classification patterns

---

## 💾 Database (SQLite)

The project uses a local SQLite database (`backend/data/tabsensei.db`) to store:

1. **WatchedProduct**: Products you're tracking
   - Product name, URL, current price
   - When added, last checked

2. **PriceHistory**: Historical prices
   - Product ID, price, date
   - Used to detect price drops

3. **TabSession**: Browsing sessions
   - Session ID, tab data, categories
   - For remembering past sessions

4. **UserPreference**: User preferences
   - Key-value pairs
   - Stores learned patterns

---

## 🔧 Configuration

### **Backend Configuration** (`backend/config.py`)
- Reads from `.env` file
- Sets up:
  - LLM provider (OpenAI/Groq/Ollama)
  - API keys
  - Model names
  - Temperature (creativity level)

### **Extension Configuration** (`extension/manifest.json`)
- Defines permissions (tabs, scripting, storage)
- Sets up content scripts
- Configures popup window

---

## 🚀 How to Use It

1. **Start Backend**:
   ```bash
   cd backend
   python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Load Extension**:
   - Open Chrome → `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" → Select `extension/` folder

3. **Use It**:
   - Open multiple tabs (e.g., 3 laptop pages)
   - Click extension icon
   - Type: "Compare 3 laptops"
   - Get AI-powered comparison!

---

## 🎯 Key Features

1. **Multi-Agent Architecture**: Each agent has a specific job
2. **LangGraph Workflow**: Orchestrates agents in a pipeline
3. **Price Tracking**: Automatically tracks prices and alerts on drops
4. **Tab Classification**: Understands what each tab is about
5. **Smart Summaries**: AI-generated summaries of tab content
6. **Memory**: Remembers your preferences and sessions
7. **Auto Tab Switching**: Jumps to most relevant tab
8. **Tab Cleanup**: Suggests closing irrelevant tabs

---

## 🔑 Important Concepts

### **LangGraph**
- A library for building agent workflows
- Creates a graph of nodes (agents) connected by edges
- Each node does one job, then passes data to next node

### **FastAPI**
- Python web framework
- Creates REST API endpoints
- Handles HTTP requests/responses

### **Chrome Extension MV3**
- Manifest V3 (latest Chrome extension format)
- Service worker (background.js) runs in background
- Content scripts inject into web pages
- Popup UI for user interaction

### **SQLite**
- Lightweight database
- Stores data locally in a file
- No server needed

---

## 🐛 Common Issues & Solutions

1. **"Rate limit exceeded"**:
   - Switch to Groq (has generous free tier)
   - Change `MODEL_PROVIDER=groq` in `.env`

2. **"Extension not working"**:
   - Check backend is running: `curl http://localhost:8000/health`
   - Reload extension in Chrome

3. **"No tabs found"**:
   - Make sure tabs are regular web pages (not chrome:// pages)
   - Check browser console for errors

---

## 📊 Data Flow Diagram

```
User Types Query
    ↓
Extension (panel.js)
    ↓
Background Service Worker (background.js)
    ↓
Collects Tab Data (title, URL, text, price)
    ↓
Sends HTTP POST to Backend
    ↓
FastAPI (agent_server.py)
    ↓
PlannerAgent (orchestrates workflow)
    ↓
┌─────────────────────────────────────┐
│  LangGraph Workflow:                │
│  1. TabReaderAgent                  │
│  2. TabClassifierAgent (AI)         │
│  3. PriceExtractionAgent            │
│  4. TabSummaryAgent (AI)            │
│  5. PriceTrackingAgent (Database)   │
│  6. AlertAgent                      │
│  7. MemoryAgent (Database)          │
│  8. Generate Reply                  │
└─────────────────────────────────────┘
    ↓
Returns JSON Response
    ↓
Extension (panel.js)
    ↓
Displays Answer + Switches Tab
```

---

## 🎓 Summary

**TabSensei** is a multi-agent AI system that:
- Reads your browser tabs
- Uses AI to understand and summarize them
- Answers questions about your tabs
- Tracks prices for shopping
- Helps you manage your tabs

It's built with:
- **Frontend**: Chrome Extension (JavaScript)
- **Backend**: FastAPI + Python
- **AI**: LangChain + Groq/OpenAI
- **Database**: SQLite
- **Orchestration**: LangGraph

The key innovation is the **multi-agent architecture** where each agent has a specific job, all coordinated by the PlannerAgent using LangGraph.

