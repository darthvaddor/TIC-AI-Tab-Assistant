# TabSensei Pipeline Overview

## Complete Pipeline Flow

The TabSensei system processes user queries about browser tabs through the following pipeline:

### 1. **Query Planning** (`_plan_query_node`)
- Analyzes the user's query to determine execution mode
- Creates an execution plan with flags for:
  - `needs_classification`: Whether to classify tabs
  - `needs_summarization`: Whether to generate summaries
  - `needs_price_extraction`: Whether to extract prices
  - `needs_youtube_transcript`: Whether to extract YouTube transcripts
  - `should_ask_cleanup`: Whether to suggest closing irrelevant tabs
- Modes: `analysis`, `single`, `multi`, `cleanup`

### 2. **Tab Reading** (`_read_tabs_node`)
- Extracts content from all browser tabs
- Uses site-specific extraction logic for:
  - Wikipedia: Removes navigation boxes, infoboxes, references
  - Google Search: Extracts search result titles and snippets
  - Gmail: Extracts email body/subjects
- Filters out UI elements and navigation text
- Ensures ALL tabs are included, even if extraction fails

### 3. **YouTube Transcript Extraction** (`_extract_youtube_transcripts_node`)
- Detects YouTube video tabs
- Extracts video IDs (placeholder for actual transcript fetching)

### 4. **Tab Classification** (`_classify_tabs_node`)
- Uses fast heuristic classification for "analyze my tabs" or many tabs
- Uses LLM classification for specific queries with fewer tabs
- Categories: research, shopping, entertainment, work, distraction, duplicate, unknown

### 5. **Price Extraction** (`_extract_prices_node`)
- Extracts product names and prices from shopping tabs
- Only runs if `needs_price_extraction` is true in the plan

### 6. **Summary Generation** (`_generate_summaries_node`)
- Generates LLM summaries for all tabs (with 10-second timeout per tab)
- Uses optimized prompts (shorter, faster)
- Falls back to text extraction if LLM times out
- Ensures ALL tabs have summaries

### 7. **Workspace Analysis** (`_analyze_workspace_node`)
- Analyzes tab categories and duplicates
- Creates workspace summary with statistics

### 8. **Alert Checking** (`_check_alerts_node`)
- Checks for price drop alerts
- Returns unread alerts

### 9. **Memory Saving** (`_save_memory_node`)
- Saves session to database for future reference

### 10. **Reply Generation** (`_generate_reply_node`)
- **Analysis Mode** (`_generate_analysis_reply`):
  - Shows all tabs with summaries
  - Used for: "analyze my tabs", "what tabs do I have", etc.
  
- **Single Mode** (`_generate_single_reply`):
  - Finds most relevant tab using relevance scoring
  - Answers specific questions using LLM (with 12-second timeout)
  - Handles chronological questions with verification
  - Used for: "what is X's first movie", "tell me about Y", etc.
  
- **Comparison Mode** (`_generate_comparison_reply`):
  - Compares multiple tabs
  - Used for: "compare X and Y", "X vs Y", etc.
  
- **Cleanup Mode** (`_generate_cleanup_reply`):
  - Suggests closing duplicate tabs
  - Used for: "close duplicates", "cleanup tabs", etc.

## Query Types Handled

### General Queries (All Tabs)
- "analyze my tabs"
- "what tabs do I have"
- "show all tabs"
- "summarize all tabs"
- "list all tabs"

**Response**: Shows all tabs with summaries

### Specific Queries (Single Tab)
- "what is X's first movie"
- "tell me about Y"
- "who is Z"
- "when did X happen"
- "compare A and B"

**Response**: Finds most relevant tab and answers the question directly

### Questions About All Tabs
- "what are all my tabs about"
- "summarize everything"
- "what do I have open"

**Response**: Shows all tabs with summaries

## Timeout Protection

- **LLM Summarization**: 10 seconds per tab
- **Question Answering**: 12 seconds
- **Total Processing**: 25 seconds maximum
- **Frontend Timeout**: 30 seconds
- **Fetch Timeout**: 30 seconds

If timeouts occur, the system falls back to:
- Text extraction for summaries
- Summary text for question answering
- Fast heuristics for classification

## Error Handling

- All tabs are included even if extraction fails
- LLM failures fall back to text extraction
- Timeouts trigger immediate fallbacks
- All errors are logged for debugging

## Performance Optimizations

1. **Fast Heuristics**: Used for "analyze my tabs" to avoid slow LLM calls
2. **Parallel Processing**: LLM calls use ThreadPoolExecutor with timeouts
3. **Reduced Text Length**: 1500 chars for summaries, 1000 for prompts
4. **Early Exit**: If processing takes >25 seconds, remaining tabs use fast fallbacks
5. **Smart Routing**: Query planning determines which steps to skip

## Example Flows

### Flow 1: "analyze my tabs"
1. Plan → analysis mode
2. Read all tabs
3. Fast heuristic classification
4. Generate LLM summaries (with timeouts)
5. Show all tabs with summaries

### Flow 2: "what is johnny depp's first movie"
1. Plan → single mode
2. Read all tabs
3. Fast heuristic classification
4. Generate summaries
5. Find most relevant tab (johnny depp search)
6. Answer question with LLM (chronological verification)
7. Return answer

### Flow 3: "compare these tabs"
1. Plan → multi mode
2. Read all tabs
3. Classification
4. Generate summaries
5. Compare relevant tabs
6. Return comparison

