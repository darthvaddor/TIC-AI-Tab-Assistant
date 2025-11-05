# TIC-AI Tab Assistant

An intelligent Chrome extension that uses AI to analyze, compare, and manage your open browser tabs. TIC-AI (Tab Intelligence & Context Assistant) provides a conversational interface that understands your open tabs and helps you make decisions, find information, and clean up your browsing session.

## 🌟 Features

### 🤖 AI-Powered Tab Analysis
- **Query your tabs**: Ask questions about the content in your open tabs
- **Tab comparison**: Compare multiple tabs side-by-side (e.g., "compare 3 laptops")
- **Smart recommendations**: Get AI-powered recommendations based on tab content
- **Context-aware responses**: Answers are grounded only in your open tabs (no external web search)

### 📊 Intelligent Tab Management
- **Auto-focus**: Automatically switches to the most relevant tab based on your query
- **Tab cleanup**: Automatically suggests closing irrelevant tabs after analysis
- **Persistent overlay**: Assistant window stays open across tab switches
- **Multi-tab reasoning**: Understands relationships between multiple open tabs

### 💬 Conversational Interface
- **Chat-based UI**: Clean, modern chat interface with markdown support
- **Follow-up questions**: Ask follow-ups like "price is no longer a constraint"
- **Table rendering**: Beautiful comparison tables for multi-tab queries
- **New Chat**: Start fresh conversations with a single click

### 🎨 User Experience
- **Movable window**: Drag the assistant window to any position (currently fixed position, drag feature coming soon)
- **Responsive design**: Works seamlessly across different screen sizes
- **Persistent state**: Remembers your conversation history
- **Clean UI**: Dark-themed interface with smooth animations

## 🏗️ Architecture

### Components

1. **Chrome Extension** (`/extension`)
   - `background.js`: Service worker handling tab data collection and backend communication
   - `content/overlay.js`: Injected overlay UI for on-page assistant
   - `popup/panel.js`: Chat interface for popup and overlay modes
   - Manifest V3 compliant

2. **FastAPI Backend** (`/backend`)
   - `agent_server.py`: FastAPI server with LangChain integration
   - Supports multiple LLM providers (OpenAI, Groq, Ollama)
   - Intelligent mode detection (single/multi/cleanup)
   - Tab ranking and comparison logic

### Data Flow

```
User Query → Extension Popup
    ↓
Background Service Worker (collects tab data)
    ↓
FastAPI Backend (LLM reasoning)
    ↓
Extension (takes action: switch tabs, close tabs, display results)
```

## 🚀 Getting Started

### Prerequisites

- Python 3.13+
- Node.js (for extension development)
- Chrome/Edge browser
- API key for your chosen LLM provider:
  - OpenAI API key (recommended)
  - Groq API key (alternative)
  - Ollama (local setup)

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

3. Create a `.env` file in the `backend/` directory:
```env
MODEL_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
MODEL_TEMPERATURE=0.2

# Optional: Groq configuration
# MODEL_PROVIDER=groq
# GROQ_API_KEY=your_groq_api_key_here
# GROQ_MODEL=llama-3.1-70b

# Optional: Ollama configuration
# MODEL_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.1
```

4. Start the backend server:
```bash
uvicorn agent_server.py:app --host 0.0.0.0 --port 8000 --reload
```

5. Verify the server is running:
```bash
curl http://localhost:8000/health
# Should return: {"ok":true,"status":"running"}
```

### Extension Setup

1. Open Chrome and navigate to `chrome://extensions/`

2. Enable "Developer mode" (toggle in top-right)

3. Click "Load unpacked" and select the `extension/` directory

4. The extension should now appear in your extensions list

5. Pin the extension to your toolbar for easy access

6. Click the extension icon to open the assistant

## 📖 Usage

### Basic Queries

1. **Single Tab Query**: Ask about a specific tab
   ```
   "What is the price of this laptop?"
   "Summarize the key features"
   ```

2. **Multi-Tab Comparison**: Compare multiple tabs
   ```
   "compare 3 laptops"
   "which laptop is better for gaming?"
   ```

3. **Follow-up Questions**: Refine your search
   ```
   User: "compare 3 laptops"
   Assistant: [recommends Lenovo based on price]
   User: "price is no longer a constraint"
   Assistant: [recommends Dell with better specs]
   ```

### Tab Management

- **Auto-switch**: The extension automatically switches to the most relevant tab
- **Cleanup prompt**: After queries, the assistant asks if you want to close unrelated tabs
- **Manual close**: Use the "Close N tabs" button when suggested

### Keyboard Shortcuts

- `Alt+Shift+T`: Toggle TIC-AI Assistant (can be customized in Chrome settings)

## 🔧 Configuration

### Backend Configuration

Edit `backend/.env` to configure:
- **MODEL_PROVIDER**: Choose `openai`, `groq`, or `ollama`
- **Model selection**: Specify which model to use
- **Temperature**: Adjust creativity (0.0-1.0, lower = more deterministic)

### Extension Configuration

- **Popup mode**: Click extension icon for popup window
- **Overlay mode**: Extension icon on active tab opens overlay
- **Persistent overlay**: Overlay stays open when switching tabs

## 🛠️ Development

### Project Structure

```
extension-assistant/
├── backend/
│   ├── agent_server.py      # FastAPI backend
│   ├── pyproject.toml       # Python dependencies
│   └── .env                 # Environment variables (create this)
├── extension/
│   ├── manifest.json        # Extension manifest
│   ├── background.js        # Service worker
│   ├── content/
│   │   ├── overlay.js       # Overlay injection script
│   │   └── overlay.css     # Overlay styles
│   └── popup/
│       ├── panel.html       # Chat UI
│       ├── panel.js         # Chat logic
│       ├── panel.css         # Chat styles
│       └── libs/
│           └── marked.esm.js # Markdown parser
└── README.md
```

### Running in Development

1. **Backend**: Start with `--reload` flag for auto-reload
2. **Extension**: Use Chrome's "Reload" button after code changes
3. **Debugging**: 
   - Backend logs appear in terminal
   - Extension logs: `chrome://extensions/` → Service Worker → Inspect
   - Content script logs: Right-click page → Inspect → Console

### API Endpoints

- `GET /health`: Health check
- `GET /config`: Runtime configuration diagnostics
- `POST /run_agent`: Main query endpoint
  ```json
  {
    "query": "compare 3 laptops",
    "tabs": [
      {
        "id": 123,
        "title": "Laptop Page",
        "url": "https://example.com",
        "text": "Page content..."
      }
    ]
  }
  ```

## 🐛 Troubleshooting

### Extension Issues

**Assistant window is too small:**
- Reload the extension
- Hard refresh the page (Ctrl+Shift+R)
- Check browser zoom level (should be 100%)

**Assistant doesn't close:**
- Click the X button in the top-right
- If in overlay mode, it should close via postMessage

**Tabs not being analyzed:**
- Ensure tabs are regular http/https pages (not chrome:// pages)
- Check browser console for errors
- Verify backend is running on port 8000

### Backend Issues

**Rate limit errors:**
- Check your API key limits
- Switch to a different provider (Groq has generous free tier)
- Reduce temperature to minimize token usage

**Model not found errors:**
- Verify model name matches your provider's available models
- For Groq: Use `llama-3.1-70b` (not `llama-3.1-70b-versatile`)
- Check provider documentation for correct model names

**Connection errors:**
- Verify backend is running: `curl http://localhost:8000/health`
- Check CORS settings in `agent_server.py`
- Ensure Chrome extension has permission to access `localhost:8000`

## 🔐 Security & Privacy

- **Local processing**: All tab data is processed locally via your backend
- **No external calls**: Answers are grounded only in your open tabs
- **API keys**: Stored securely in `.env` file (never commit to git)
- **Tab data**: Only sent to your local backend server

## 📝 TODO / Roadmap

- [ ] Draggable overlay window
- [ ] Tab grouping and organization
- [ ] Export conversation history
- [ ] Multi-window support
- [ ] Custom model fine-tuning
- [ ] Voice input support
- [ ] Browser extension for Firefox/Edge

## 🤝 Contributing

This is currently a personal project, but contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is open source. See LICENSE file for details.

## 🙏 Acknowledgments

- Built with [LangChain](https://www.langchain.com/) for LLM integration
- Uses [FastAPI](https://fastapi.tiangolo.com/) for backend
- Markdown rendering with [marked.js](https://marked.js.org/)

## 📧 Contact

For questions or issues, please open an issue on GitHub.

---

**Note**: This extension requires a running backend server. Make sure to start the FastAPI server before using the extension.
