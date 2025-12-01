import { marked } from "./libs/marked.esm.js";

// === DOM Elements ===
const btn = document.getElementById("askBtn");
const promptBox = document.getElementById("prompt");
const output = document.getElementById("output");
const thinking = document.getElementById("thinking");
const closeBtn = document.getElementById("closeBtn");
// Dynamically add New Chat button in header
const header = document.querySelector(".bot-header");
let newChatBtn = null;

// === Local chat history (stored in chrome.storage.local) ===
let chatHistory = [];
let isProcessing = false; // Prevent multiple simultaneous queries
let lastBackendSessionId = null; // Track backend session to detect restarts

// === Test alarm creation (for debugging) ===
async function testAlarm() {
  console.log("[TabSensei] Testing alarm creation...");
  const testTime = Date.now() + (30 * 1000); // 30 seconds from now
  const testMessage = "Test alarm - 30 seconds";
  
  chrome.alarms.create(testMessage, { when: testTime }, () => {
    if (chrome.runtime.lastError) {
      console.error("[TabSensei] ❌ Test alarm creation failed:", chrome.runtime.lastError);
    } else {
      console.log("[TabSensei] ✅ Test alarm created for", new Date(testTime).toLocaleString());
      
      // Verify it was created
      setTimeout(() => {
        chrome.alarms.get(testMessage, (alarm) => {
          if (alarm) {
            console.log("[TabSensei] ✓ Test alarm verified:", new Date(alarm.scheduledTime).toLocaleString());
          } else {
            console.error("[TabSensei] ❌ Test alarm NOT found!");
          }
        });
      }, 500);
    }
  });
  
  // Also list all alarms
  chrome.alarms.getAll((alarms) => {
    console.log(`[TabSensei] All alarms (${alarms.length}):`, alarms.map(a => ({
      name: a.name,
      time: new Date(a.scheduledTime).toLocaleString(),
      in: Math.round((a.scheduledTime - Date.now()) / 1000) + " seconds"
    })));
  });
}

// === Function to list all active reminders ===
async function listActiveReminders() {
  return new Promise((resolve) => {
    chrome.alarms.getAll((alarms) => {
      if (!alarms || alarms.length === 0) {
        resolve([]);
        return;
      }
      
      const now = Date.now();
      const activeReminders = alarms
        .filter(alarm => alarm.scheduledTime > now)
        .map(alarm => ({
          name: alarm.name,
          scheduledTime: alarm.scheduledTime,
          when: new Date(alarm.scheduledTime)
        }))
        .sort((a, b) => a.scheduledTime - b.scheduledTime);
      
      resolve(activeReminders);
    });
  });
}

// === Safe message sender (handles extension context invalidation) ===
function safeSendMessage(message, callback) {
  try {
    // Check if chrome.runtime is available and has a valid ID
    if (!chrome.runtime) {
      if (callback) {
        callback({ error: "Extension context invalidated. Please reload the extension from chrome://extensions/" });
      }
      return;
    }

    // Check if runtime ID exists (indicates extension is still valid)
    try {
      const runtimeId = chrome.runtime.id;
      if (!runtimeId) {
        if (callback) {
          callback({ error: "Extension context invalidated. Please reload the extension from chrome://extensions/" });
        }
        return;
      }
    } catch (idError) {
      // Runtime ID check failed - context is invalidated
      if (callback) {
        callback({ error: "Extension context invalidated. Please reload the extension from chrome://extensions/" });
      }
      return;
    }

    // Check if sendMessage method exists
    if (!chrome.runtime.sendMessage) {
      if (callback) {
        callback({ error: "Extension context invalidated. Please reload the extension from chrome://extensions/" });
      }
      return;
    }

    // Try to send message with error handling
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        const error = chrome.runtime.lastError.message;
        // Handle context invalidation gracefully
        if (error.includes("Extension context invalidated") ||
          error.includes("message channel closed") ||
          error.includes("Could not establish connection")) {
          if (callback) {
            callback({ error: "Extension context invalidated. Please reload the extension from chrome://extensions/" });
          }
          return;
        }
        // Other errors
        if (callback) {
          callback({ error: error });
        }
        return;
      }
      // Success
      if (callback) {
        callback(response || {});
      }
    });
  } catch (err) {
    console.error("Failed to send message:", err);
    if (callback) {
      callback({ error: err.message || "Failed to send message. Please reload the extension." });
    }
  }
}

// --- Check backend session and clear history if backend restarted ---
async function checkBackendSession() {
  // First check if extension context is still valid
  try {
    if (!chrome.runtime || !chrome.runtime.id) {
      // Extension context invalidated - silently return false
      return false;
    }
  } catch (e) {
    // Extension context invalidated - silently return false
    return false;
  }
  
  try {
    const res = await fetch("http://localhost:8000/health");
    if (!res.ok) {
      console.warn("[TabSensei] Backend health check failed");
      return false; // Backend might be down
    }
    
    const data = await res.json();
    const currentSessionId = data.session_id;
    
    if (!currentSessionId) {
      console.warn("[TabSensei] No session ID in backend response");
      return false;
    }
    
    // Check extension context again before accessing storage
    try {
      if (!chrome.runtime || !chrome.runtime.id) {
        return false;
      }
    } catch (e) {
      return false;
    }
    
    // Get stored session ID
    const stored = await chrome.storage.local.get(["backendSessionId", "ticaiHistory"]).catch(() => null);
    if (!stored) {
      // Storage access failed (context invalidated)
      return false;
    }
    
    const storedSessionId = stored.backendSessionId;
    
    // If session ID changed, backend restarted - FORCE CLEAR everything
    if (storedSessionId && storedSessionId !== currentSessionId) {
      console.log("[TabSensei] Backend restarted (session changed), clearing ALL chat history AND alarms");
      chatHistory = []; // Clear in-memory
      
      // Clear ALL Chrome alarms
      try {
        chrome.alarms.getAll((alarms) => {
          console.log(`[TabSensei] Clearing ${alarms.length} existing alarms`);
          alarms.forEach((alarm) => {
            chrome.alarms.clear(alarm.name, (wasCleared) => {
              if (wasCleared) {
                console.log(`[TabSensei] Cleared alarm: "${alarm.name}"`);
              } else {
                // This usually just means the alarm already fired or was cleared elsewhere.
                // Downgrade to debug-style log so it doesn't look like an error.
                console.log(`[TabSensei] Alarm was already cleared or not found: "${alarm.name}"`);
              }
            });
          });
        });
      } catch (e) {
        console.error("[TabSensei] Error clearing alarms:", e);
      }
      
      // Force clear from storage (both keys)
      try {
        // Check context again before saving
        if (!chrome.runtime || !chrome.runtime.id) {
          return false;
        }
        await chrome.storage.local.set({
          ticaiHistory: [],
          chatHistory: [], // Clear both keys
          backendSessionId: currentSessionId
        });
        // Also remove any other chat-related data
        await chrome.storage.local.remove(["ticaiAskedCleanup"]);
        renderHistory(); // Re-render empty history
      } catch (e) {
        // Context invalidated during save - check if it's actually invalidated or another error
        const errorMsg = e.message || String(e);
        if (!errorMsg.includes("Extension context invalidated")) {
          console.warn("[TabSensei] Error clearing history:", e);
        }
        // Even if save fails, we've cleared in-memory
        renderHistory(); // Still render empty history
      }
      return true; // Indicates history was cleared
    } else if (!storedSessionId) {
      // First time - store the session ID, but also clear any existing history and alarms
      console.log("[TabSensei] First session, clearing any existing history AND alarms");
      chatHistory = [];
      
      // Clear ALL Chrome alarms on first session
      try {
        chrome.alarms.getAll((alarms) => {
          console.log(`[TabSensei] First session - clearing ${alarms.length} existing alarms`);
          alarms.forEach((alarm) => {
            chrome.alarms.clear(alarm.name, (wasCleared) => {
              if (wasCleared) {
                console.log(`[TabSensei] Cleared alarm: "${alarm.name}"`);
              }
            });
          });
        });
      } catch (e) {
        console.error("[TabSensei] Error clearing alarms on first session:", e);
      }
      
      try {
        // Check context again before saving
        if (!chrome.runtime || !chrome.runtime.id) {
          return false;
        }
        await chrome.storage.local.set({
          ticaiHistory: [],
          chatHistory: [], // Clear both keys
          backendSessionId: currentSessionId
        });
        renderHistory();
      } catch (e) {
        // Context invalidated during save - check if it's actually invalidated or another error
        const errorMsg = e.message || String(e);
        if (!errorMsg.includes("Extension context invalidated")) {
          console.warn("[TabSensei] Error clearing history:", e);
        }
        // Even if save fails, we've cleared in-memory
        renderHistory(); // Still render empty history
      }
      return true;
    }
    
    lastBackendSessionId = currentSessionId;
    return false; // History was not cleared
  } catch (err) {
    // Check if error is due to context invalidation or fetch failure
    const errorMsg = err.message || String(err) || "";
    const isContextInvalidated = errorMsg.includes("Extension context invalidated") || 
                                  errorMsg.includes("message channel closed") ||
                                  errorMsg.includes("Could not establish connection");
    
    // Only log if it's not a context invalidation error
    if (!isContextInvalidated) {
      // Might be a network error (backend down) - log it
      if (errorMsg.includes("Failed to fetch") || errorMsg.includes("NetworkError")) {
        // Backend is probably down - don't log as error, just silently return
        return false;
      }
      // Other errors - log them
      console.warn("[TabSensei] Failed to check backend session:", err);
    }
    // If backend is down or context invalidated, don't clear history - might just be temporarily unavailable
    return false;
  }
}

// --- Load existing history ---
async function loadHistory() {
  // First check if backend restarted - this will clear history if needed
  const historyWasCleared = await checkBackendSession();
  
  // Only load from storage if history was NOT cleared (to avoid loading old data)
  if (!historyWasCleared) {
    // Try both storage keys - background.js uses "chatHistory", panel.js uses "ticaiHistory"
    const stored = await chrome.storage.local.get(["ticaiHistory", "chatHistory"]);
    // Prefer chatHistory (used by background.js) if it exists, otherwise use ticaiHistory
    const storedHistory = stored.chatHistory || stored.ticaiHistory || [];
    
    // Only load if stored history is longer than current (or current is empty)
    // This prevents overwriting with older data if we already have more recent data in memory
    if (storedHistory.length >= chatHistory.length) {
      chatHistory = storedHistory;
    }
    
    // Sync both keys to keep them in sync
    if (stored.chatHistory && !stored.ticaiHistory) {
      await chrome.storage.local.set({ ticaiHistory: stored.chatHistory }).catch(() => {});
    } else if (stored.ticaiHistory && !stored.chatHistory) {
      await chrome.storage.local.set({ chatHistory: stored.ticaiHistory }).catch(() => {});
    }
  } else {
    // History was cleared, ensure it's empty
    chatHistory = [];
  }
  
  renderHistory();

  // Check for alerts on panel load
  checkAlerts();
}

// Check for price alerts
async function checkAlerts() {
  try {
    // Check stored alerts first
    const stored = await chrome.storage.local.get(["pendingAlerts"]);
    if (stored.pendingAlerts && stored.pendingAlerts.length > 0) {
      renderAlerts(stored.pendingAlerts);
      try {
        chrome.action.setBadgeText({ text: "" });
      } catch (err) {
        // Silently ignore if context invalidated
        console.warn("Could not clear badge:", err);
      }
      chrome.storage.local.remove(["pendingAlerts"]);
    }

    // Also fetch from backend
    const res = await fetch("http://localhost:8000/alerts");
    const data = await res.json();
    if (data.ok && data.alerts && data.alerts.length > 0) {
      renderAlerts(data.alerts);
    }
  } catch (err) {
    console.warn("Failed to fetch alerts:", err);
  }
}

// --- Save updated history ---
// --- Save updated history ---
function saveHistory() {
  try {
    // Check if extension context is valid
    if (chrome.runtime && chrome.runtime.id) {
      // Use callback style to prevent Promise return and unhandled rejections
      // Save to both keys to keep them in sync (background.js uses "chatHistory", panel.js uses "ticaiHistory")
      chrome.storage.local.set({ ticaiHistory: chatHistory, chatHistory: chatHistory }, () => {
        // Check for errors in callback (e.g. context invalidated during save)
        if (chrome.runtime.lastError) {
          console.warn("Ignored saveHistory error:", chrome.runtime.lastError.message);
        }
      });
    }
  } catch (e) {
    // Ignore context invalidation errors during reload
    console.warn("Could not save history (context invalidated)");
  }
}

// --- Listen for storage changes (sync across popups/reloads) ---
chrome.storage.onChanged.addListener(async (changes, namespace) => {
  if (namespace === 'local') {
    // Check for both ticaiHistory and chatHistory keys
    const historyChange = changes.ticaiHistory || changes.chatHistory;
    
    if (historyChange) {
      // Before loading new history, check if backend session changed
      // This prevents loading old history from another instance after backend restart
      try {
        if (!chrome.runtime || !chrome.runtime.id) {
          return; // Context invalidated, ignore changes
        }
      } catch (e) {
        return; // Context invalidated, ignore changes
      }
      
      const wasCleared = await checkBackendSession();
      if (wasCleared) {
        // History was cleared due to backend restart, don't load old history
        return;
      }
      
      // Use the value from whichever key changed, or check both
      const newHistory = historyChange.newValue || [];
      
      // Only update if:
      // 1. New history is longer (has more messages) - it's more recent
      // 2. Same length but different content - might be an update from another tab
      // 3. Current history is empty and new one isn't
      // This prevents overwriting with older/stale data
      const shouldUpdate = (newHistory.length > chatHistory.length) ||
                          (newHistory.length === chatHistory.length && 
                           JSON.stringify(newHistory) !== JSON.stringify(chatHistory) &&
                           newHistory.length > 0) ||
                          (chatHistory.length === 0 && newHistory.length > 0);
      
      if (shouldUpdate && newHistory.length > 0) {
        chatHistory = newHistory;
        renderHistory();
        // If we were processing and now have a response, stop processing UI
        if (isProcessing && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role !== 'user') {
          isProcessing = false;
          thinking.style.display = "none";
        }
      }
    }
  }
});

// --- Render conversation thread ---
function renderHistory() {
  output.innerHTML = chatHistory
    .map(
      (m) =>
        `<div class="msg ${m.role}">
           <b>${m.role === "user" ? "You" : "Tab Sensei"}:</b>
           <div class="msg-text markdown-body">${marked.parse(m.text)}</div>
         </div>`
    )
    .join("<hr style='opacity:0.05;border:none;'>");

  // Auto-scroll to bottom on new message
  setTimeout(() => {
    output.scrollTop = output.scrollHeight;
  }, 10);
  
  // Also scroll after a longer delay to catch any async content
  setTimeout(() => {
    output.scrollTop = output.scrollHeight;
  }, 100);
}

// === Auto-grow text area (ChatGPT-style) ===
promptBox.addEventListener("input", () => {
  promptBox.style.height = "auto";
  promptBox.style.height = Math.min(promptBox.scrollHeight, 150) + "px";
});

// === Allow Enter key to trigger Ask ===
promptBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    btn.click();
  }
});

// === Handle Ask button click ===
btn.addEventListener("click", async () => {
  const query = promptBox.value.trim();
  if (!query) return;

  // Prevent multiple simultaneous queries
  if (isProcessing) {
    console.warn("Already processing a query, please wait...");
    return;
  }
  isProcessing = true;

  // Clear any previous thinking/error messages from the last query
  thinking.style.display = "none";

  // Check backend session first - if backend restarted, clear history
  const historyWasCleared = await checkBackendSession();
  
  // Only load from storage if history was NOT cleared (to avoid loading old data)
  // But preserve existing in-memory history if it's more recent/longer
  if (!historyWasCleared) {
    try {
      // Check context before accessing storage
      if (!checkExtensionContext()) {
        console.warn("[TabSensei] Extension context invalidated, skipping storage access");
        // Continue with existing in-memory history
      } else {
        const latestHistory = await chrome.storage.local.get(["ticaiHistory", "chatHistory"]);
        const storedHistory = latestHistory.chatHistory || latestHistory.ticaiHistory || [];
        
        // Only update if stored history is longer (has more messages) than current
        // This prevents overwriting with older data
        if (storedHistory.length > chatHistory.length) {
          chatHistory = storedHistory;
        }
        // If they're equal length but different, use stored (it might have updates from another tab)
        else if (storedHistory.length === chatHistory.length && 
                 JSON.stringify(storedHistory) !== JSON.stringify(chatHistory)) {
          chatHistory = storedHistory;
        }
        // Otherwise keep current in-memory history (it's more up-to-date)
      }
    } catch (e) {
      console.warn("[TabSensei] Failed to load history from storage:", e.message);
      // Continue with existing in-memory history
    }
  } else {
    // History was cleared, ensure it's empty
    chatHistory = [];
  }

  // Append user message (this will be the first message if history was cleared)
  chatHistory.push({ role: "user", text: query });
  renderHistory(); // Render immediately so user sees their message
  saveHistory(); // Save to storage

  // Reset UI
  promptBox.value = "";
  promptBox.style.height = "auto";
  thinking.style.display = "block";
  thinking.textContent = "Thinking";

  // Animated thinking dots
  let dots = 0;
  const dotInterval = setInterval(() => {
    dots = (dots + 1) % 4;
    thinking.textContent = "Thinking" + ".".repeat(dots);
  }, 500);

  // Track if timeout message was added
  let timeoutMessageAdded = false;

  // Send message to background.js with timeout
  const messageTimeout = setTimeout(() => {
    if (!timeoutMessageAdded) {
      clearInterval(dotInterval);
      thinking.style.display = "none";
      const msg = `<span style="color:red;">Request is taking longer than expected. The backend might be processing your tabs. Please wait a moment and try again, or check if the backend server is running at http://localhost:8000</span>`;
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      timeoutMessageAdded = true;
      isProcessing = false;
    }
  }, 65000); // 65 second timeout

  // Check if user wants to test notification or alarm
  const queryLower = query.toLowerCase();

  // Detect intent to explicitly close tabs via natural language, e.g.:
  // "please close tabs not relevant to kaggle and leetcode"
  const wantsAutoCloseTabs =
    queryLower.includes("close tabs") ||
    queryLower.includes("close the tabs") ||
    queryLower.includes("close all other tabs") ||
    queryLower.includes("close unrelated tabs") ||
    queryLower.includes("close tabs not relevant");
  if (queryLower === "test notification" || queryLower === "test" || queryLower.includes("test notification")) {
    clearTimeout(messageTimeout);
    clearInterval(dotInterval);
    thinking.style.display = "none";
    isProcessing = false;
    
    testNotification();
    chatHistory.push({ role: "assistant", text: "✅ Test notification sent! Check your open webpages for a purple popup in the top-right corner. If you see it, notifications are working!" });
    saveHistory();
    renderHistory();
    return;
  }
  
  if (queryLower === "test alarm" || queryLower.includes("test alarm")) {
    clearTimeout(messageTimeout);
    clearInterval(dotInterval);
    thinking.style.display = "none";
    isProcessing = false;
    
    testAlarm();
    chatHistory.push({ role: "assistant", text: "✅ Test alarm created for 30 seconds from now! Check the console for logs. Also check Service Worker console (chrome://extensions → service worker) to see if alarm fires." });
    saveHistory();
    renderHistory();
    return;
  }
  
  // Check if user is asking about reminders before sending to backend
  if (queryLower.includes("show my reminders") || queryLower.includes("list reminders") || 
      queryLower.includes("my reminders") || queryLower.includes("what reminders") ||
      queryLower.includes("check reminders") || queryLower.includes("active reminders")) {
    // Handle reminder listing locally
    listActiveReminders().then(reminders => {
      clearTimeout(messageTimeout);
      clearInterval(dotInterval);
      thinking.style.display = "none";
      isProcessing = false;
      
      if (reminders.length === 0) {
        const msg = `📋 **No active reminders**\n\nYou don't have any reminders set at the moment.`;
        chatHistory.push({ role: "assistant", text: msg });
      } else {
        let reminderList = `📋 **You have ${reminders.length} active reminder${reminders.length !== 1 ? 's' : ''}:**\n\n`;
        reminders.forEach((reminder, index) => {
          const timeUntil = Math.round((reminder.scheduledTime - Date.now()) / (1000 * 60 * 60));
          const days = Math.floor(timeUntil / 24);
          const hours = timeUntil % 24;
          let timeText = "";
          if (days > 0) {
            timeText = `${days} day${days > 1 ? 's' : ''} and ${hours} hour${hours !== 1 ? 's' : ''}`;
          } else {
            timeText = `${hours} hour${hours !== 1 ? 's' : ''}`;
          }
          reminderList += `${index + 1}. **${reminder.name}**\n   📅 ${reminder.when.toLocaleString()}\n   ⏰ In ${timeText}\n\n`;
        });
        chatHistory.push({ role: "assistant", text: reminderList });
      }
      saveHistory();
      renderHistory();
    });
    return; // Don't send to backend
  }

  // Send the current chatHistory (which now includes the new user message)
  safeSendMessage({ action: "analyzeTabs", query, chatHistory }, (response) => {
    clearTimeout(messageTimeout);
    clearInterval(dotInterval);
    thinking.style.display = "none";
    isProcessing = false;

    // Handle errors from safeSendMessage
    if (response && response.error) {
      const errorMsg = response.error;
      let userMsg = `<span style="color:red;">Error: ${errorMsg}</span>`;
      if (errorMsg.includes("Extension context invalidated")) {
        userMsg = `<span style="color:red;">Extension context invalidated. Please reload the extension from chrome://extensions/</span>`;
      } else if (errorMsg.includes("message channel closed") || errorMsg.includes("timeout")) {
        userMsg = `<span style="color:red;">Request timed out. The backend is taking too long to respond. This might happen if you have many tabs open. Please try again or check if the backend server is running at http://localhost:8000</span>`;
      }
      // Remove timeout message if it was added
      if (timeoutMessageAdded && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "system") {
        chatHistory.pop();
      }
      chatHistory.push({ role: "system", text: userMsg });
      renderHistory();
      saveHistory();
      return;
    }

    if (!response) {
      const msg = `<span style="color:red;">No response received. Please check if the backend server is running at http://localhost:8000</span>`;
      // Remove timeout message if it was added
      if (timeoutMessageAdded && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "system") {
        chatHistory.pop();
      }
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      return;
    }

    // Handle error responses from backend
    if (response.error) {
      const msg = `<span style="color:red;">Error: ${response.error}</span>`;
      // Remove timeout message if it was added
      if (timeoutMessageAdded && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "system") {
        chatHistory.pop();
      }
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      return;
    }

    if (!response.reply) {
      const msg = `<span style="color:red;">No reply in response. Please check the backend logs.</span>`;
      // Remove timeout message if it was added
      if (timeoutMessageAdded && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "system") {
        chatHistory.pop();
      }
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      return;
    }

    // Remove timeout message if it was added
    if (timeoutMessageAdded && chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "system") {
      chatHistory.pop();
    }

    // Append assistant message (but clean up any ugly ISO timestamps first)
    let cleanReply = response.reply;
    // Replace ISO timestamp patterns like "2025-11-30T21:18:00-08:00" with formatted date
    cleanReply = cleanReply.replace(/\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})\b/g, (match) => {
      try {
        const dt = new Date(match);
        return dt.toLocaleString('en-US', { 
          month: 'short', 
          day: 'numeric', 
          year: 'numeric',
          hour: 'numeric', 
          minute: '2-digit',
          hour12: true 
        });
      } catch {
        return match; // If parsing fails, return original
      }
    });
    chatHistory.push({ role: "assistant", text: cleanReply });
    saveHistory(); // Save immediately so it's available when tab switches (saves to both keys)

    // Store response for cleanup prompt (will be shown after typewriter completes)
    const shouldShowCleanup = response && response.mode !== "cleanup" && response.should_ask_cleanup;

    // Handle reminder - check both response.reminder and response.mode === "reminder"
    console.log(`[TabSensei] 🔍 Checking for reminder in response:`, {
      hasReminder: !!response.reminder,
      reminder: response.reminder,
      mode: response.mode,
      reply: response.reply?.substring(0, 100)
    });
    
    if (response.reminder || response.mode === "reminder") {
      console.log(`[TabSensei] ✅ REMINDER DETECTED! Processing...`);
      
      // Extract reminder data - should normally be in response.reminder
      let reminderData = response.reminder || response;
      const { message, timestamp, recurring } = reminderData;
      
      console.log(`[TabSensei] Reminder data extracted:`, { message, timestamp, recurring });
      
      // If backend replied with mode="reminder" but didn't include structured reminder data,
      // treat this as a soft failure instead of throwing an extension error.
      if (!message || !timestamp) {
        console.warn(`[TabSensei] Reminder data incomplete, skipping alarm creation.`, reminderData);
        console.warn(`[TabSensei] Missing message: ${!message}, Missing timestamp: ${!timestamp}`);
        
        const fallbackMsg = `⚠️ I couldn't reliably parse the reminder time from that message. ` +
          `Please try again with something like "remind me in 1 minute to do neetcode today" ` +
          `or "remind me at 9:10 PM today to do neetcode".`;
        chatHistory.push({ role: "system", text: fallbackMsg });
        saveHistory();
        renderHistory();
        return;
      }
      
      let targetTime = new Date(timestamp).getTime();
      const now = Date.now();
      const timeUntil = targetTime - now;
      
      console.log(`[TabSensei] ⏰ REMINDER DETECTED!`);
      console.log(`[TabSensei] Reminder message: "${message}"`);
      console.log(`[TabSensei] Reminder timing: targetTime=${new Date(targetTime).toLocaleString()}, now=${new Date(now).toLocaleString()}, timeUntil=${Math.round(timeUntil/1000/60)} minutes`);
      
      // Debug: Log all alarms before creating new one
      chrome.alarms.getAll((allAlarms) => {
        console.log(`[TabSensei] Existing alarms before creating new one: ${allAlarms.length}`);
        if (allAlarms.length > 0) {
          allAlarms.forEach(a => {
            const timeUntil = Math.round((a.scheduledTime - Date.now()) / 1000 / 60);
            console.log(`  - "${a.name}" scheduled for ${new Date(a.scheduledTime).toLocaleString()} (in ${timeUntil} minutes)`);
          });
        }
      });
      
      // Ensure alarm is at least 1 minute in the future (Chrome alarms need a small buffer)
      // If time is more than 1 minute away, it's fine (e.g., 4 minutes = OK)
      const oneMinute = 60 * 1000;
      
      // Check if time has already passed (negative timeUntil)
      if (timeUntil < 0) {
        // Time has passed
        if (recurring) {
          // For recurring, move to tomorrow
          const oneDay = 24 * 60 * 60 * 1000;
          targetTime = targetTime + oneDay;
          // Find the next occurrence of this time
          while (targetTime <= now + oneMinute) {
            targetTime += oneDay;
          }
          // Update the reminder message to reflect tomorrow's date
          const tomorrowDate = new Date(targetTime);
          const friendlyDate = tomorrowDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
          const updateMsg = `⏰ Reminder adjusted: The time has passed today, so I've set it for **${friendlyDate}** instead.`;
          chatHistory.push({ role: "system", text: updateMsg });
          saveHistory();
          renderHistory();
        } else {
          // For single reminders, if time has passed, show error and don't create alarm
          const pastTime = new Date(targetTime);
          const friendlyPastTime = pastTime.toLocaleString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            year: 'numeric',
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
          });
          const errorMsg = `⚠️ **The specified time (${friendlyPastTime}) has already passed.** The reminder cannot be set for a time in the past. Please set it for a future time.`;
          // Replace the assistant's reply with the error message
          if (chatHistory.length > 0 && chatHistory[chatHistory.length - 1].role === "assistant") {
            chatHistory[chatHistory.length - 1].text = errorMsg;
          } else {
            // If no assistant message, add system message
            chatHistory.push({ role: "system", text: errorMsg });
          }
          saveHistory();
          renderHistory();
          return; // Don't create alarm for past time
        }
      } else if (timeUntil <= oneMinute && timeUntil >= 0) {
        // Time is too close (within 1 minute) - move to at least 1 minute in future
        if (recurring) {
          const oneDay = 24 * 60 * 60 * 1000;
          targetTime = targetTime + oneDay;
          while (targetTime <= now + oneMinute) {
            targetTime += oneDay;
          }
        } else {
          // For single reminders, move to at least 2 minutes from now
          targetTime = now + (2 * oneMinute);
          const adjustedDate = new Date(targetTime);
          const friendlyAdjusted = adjustedDate.toLocaleString('en-US', { 
            month: 'short', 
            day: 'numeric', 
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
          });
          const updateMsg = `⏰ Reminder time was too close, adjusted to **${friendlyAdjusted}** (2 minutes from now).`;
          chatHistory.push({ role: "system", text: updateMsg });
          saveHistory();
          renderHistory();
        }
      }

      if (targetTime > now) {
        // Create alarm(s)
        if (recurring) {
          // For recurring reminders, create alarms for the next 30 days starting from targetTime
          const oneDay = 24 * 60 * 60 * 1000; // milliseconds in a day
          let alarmCount = 0;
          for (let i = 0; i < 30; i++) {
            const alarmTime = targetTime + (i * oneDay);
            if (alarmTime > now + oneMinute) {
              const alarmName = `${message} (Day ${i + 1})`;
              
              // Check context before creating alarm
              try {
                if (!checkExtensionContext()) {
                  console.error(`[TabSensei] ❌ Extension context invalidated, cannot create alarm "${alarmName}"`);
                  continue; // Skip this alarm
                }
                
                chrome.alarms.create(alarmName, { when: alarmTime }, () => {
                  if (chrome.runtime.lastError) {
                    console.error(`[TabSensei] ❌ Failed to create alarm "${alarmName}":`, chrome.runtime.lastError.message);
                  } else {
                    const timeUntil = Math.round((alarmTime - Date.now()) / 1000 / 60);
                    console.log(`[TabSensei] ✅ Created alarm "${alarmName}" for ${new Date(alarmTime).toLocaleString()} (in ${timeUntil} minutes)`);
                  }
                });
              } catch (e) {
                console.error(`[TabSensei] ❌ Error creating alarm "${alarmName}":`, e);
              }
              alarmCount++;
            }
          }
          const timeUntilFirst = Math.round((targetTime - Date.now()) / 1000 / 60);
          console.log(`[TabSensei] Attempted to create ${alarmCount} daily alarms starting from ${new Date(targetTime).toLocaleString()} (first alarm in ${timeUntilFirst} minutes)`);
          
          // Verify first alarm after a delay
          setTimeout(() => {
            chrome.alarms.get(`${message} (Day 1)`, (alarm) => {
              if (alarm) {
                const timeUntil = Math.round((alarm.scheduledTime - Date.now()) / 1000 / 60);
                console.log(`[TabSensei] ✓ First alarm verified: scheduled for ${new Date(alarm.scheduledTime).toLocaleString()} (in ${timeUntil} minutes)`);
              } else {
                console.error(`[TabSensei] ❌ First alarm was NOT created!`);
              }
            });
          }, 200);
        } else {
          // Single reminder
          // Check context before creating alarm
          try {
            if (!checkExtensionContext()) {
              const errorMsg = `⚠️ Extension context invalidated. Please reload the extension from chrome://extensions/`;
              chatHistory.push({ role: "system", text: errorMsg });
              saveHistory();
              renderHistory();
              return;
            }
            
            console.log(`[TabSensei] 🔔🔔🔔 CREATING ALARM 🔔🔔🔔`);
            console.log(`[TabSensei] Creating alarm with name: "${message}"`);
            console.log(`[TabSensei] Target time: ${new Date(targetTime).toLocaleString()}`);
            console.log(`[TabSensei] Current time: ${new Date().toLocaleString()}`);
            console.log(`[TabSensei] Time until alarm: ${Math.round((targetTime - Date.now()) / 1000 / 60)} minutes`);
            console.log(`[TabSensei] Alarm timestamp: ${targetTime}`);
            
            chrome.alarms.create(message, { when: targetTime }, () => {
              if (chrome.runtime.lastError) {
                console.error(`[TabSensei] ❌ FAILED to create alarm "${message}":`, chrome.runtime.lastError.message);
                const errorMsg = `⚠️ **Failed to create reminder alarm.** Error: ${chrome.runtime.lastError.message}`;
                chatHistory.push({ role: "system", text: errorMsg });
                saveHistory();
                renderHistory();
              } else {
                const timeUntilAlarm = Math.round((targetTime - Date.now()) / 1000 / 60);
                console.log(`[TabSensei] ✅✅✅ ALARM CREATED SUCCESSFULLY ✅✅✅`);
                console.log(`[TabSensei] Alarm name: "${message}"`);
                console.log(`[TabSensei] Scheduled for: ${new Date(targetTime).toLocaleString()}`);
                console.log(`[TabSensei] In ${timeUntilAlarm} minutes`);
                
                // Verify alarm was created immediately and after delay
                chrome.alarms.get(message, (alarm) => {
                  if (alarm) {
                    const timeUntil = Math.round((alarm.scheduledTime - Date.now()) / 1000 / 60);
                    console.log(`[TabSensei] ✓✓✓ IMMEDIATE VERIFICATION: Alarm exists!`);
                    console.log(`[TabSensei] Scheduled for: ${new Date(alarm.scheduledTime).toLocaleString()}`);
                    console.log(`[TabSensei] In ${timeUntil} minutes`);
                  } else {
                    console.error(`[TabSensei] ❌❌❌ IMMEDIATE VERIFICATION FAILED: Alarm NOT found!`);
                  }
                });
                
                // Verify again after delay
                setTimeout(() => {
                  if (!checkExtensionContext()) {
                    console.error(`[TabSensei] Context invalidated, cannot verify alarm`);
                    return;
                  }
                  chrome.alarms.get(message, (alarm) => {
                    if (alarm) {
                      const timeUntil = Math.round((alarm.scheduledTime - Date.now()) / 1000 / 60);
                      console.log(`[TabSensei] ✓✓✓ DELAYED VERIFICATION: Alarm still exists!`);
                      console.log(`[TabSensei] Scheduled for: ${new Date(alarm.scheduledTime).toLocaleString()}`);
                      console.log(`[TabSensei] In ${timeUntil} minutes`);
                    } else {
                      console.error(`[TabSensei] ❌❌❌ DELAYED VERIFICATION FAILED: Alarm disappeared!`);
                    }
                  });
                }, 500);
              }
            });
          } catch (e) {
            console.error(`[TabSensei] ❌ Error creating single alarm "${message}":`, e);
            const errorMsg = `⚠️ **Failed to create reminder alarm.** Please reload the extension.`;
            chatHistory.push({ role: "system", text: errorMsg });
            saveHistory();
            renderHistory();
          }
        }
        const reminderDate = new Date(targetTime);
        const formattedDate = reminderDate.toLocaleString('en-US', { 
          month: 'short', 
          day: 'numeric', 
          year: 'numeric',
          hour: 'numeric', 
          minute: '2-digit',
          hour12: true 
        });
        const timeUntilMs = targetTime - now;
        const timeUntilHours = Math.round(timeUntilMs / (1000 * 60 * 60)); // hours
        const daysUntil = Math.floor(timeUntilHours / 24);
        const hoursUntil = timeUntilHours % 24;
        const minutesUntil = Math.floor((timeUntilMs % (1000 * 60 * 60)) / (1000 * 60));
        
        let timeUntilText = "";
        if (daysUntil > 0) {
          timeUntilText = `${daysUntil} day${daysUntil > 1 ? 's' : ''} and ${hoursUntil} hour${hoursUntil !== 1 ? 's' : ''}`;
        } else if (hoursUntil > 0) {
          timeUntilText = `${hoursUntil} hour${hoursUntil !== 1 ? 's' : ''} and ${minutesUntil} minute${minutesUntil !== 1 ? 's' : ''}`;
        } else {
          timeUntilText = `${minutesUntil} minute${minutesUntil !== 1 ? 's' : ''}`;
        }
        
        console.log(`[TabSensei] Alarm set for: ${message} at ${formattedDate}`);
        
        // Verify alarm was created (check first alarm for recurring, or the single alarm)
        const checkAlarmName = recurring ? `${message} (Day 1)` : message;
        
        // Wait a moment for alarms to be created, then verify
        setTimeout(() => {
          // Also list all alarms for debugging
          chrome.alarms.getAll((allAlarms) => {
            console.log(`[TabSensei] All active alarms (${allAlarms.length}):`, allAlarms.map(a => ({
              name: a.name,
              scheduledTime: new Date(a.scheduledTime).toLocaleString(),
              timeUntil: Math.round((a.scheduledTime - Date.now()) / 1000 / 60) + " minutes"
            })));
            
            // Show alarms in chat for user to verify
            if (allAlarms.length > 0) {
              const upcomingAlarms = allAlarms
                .filter(a => a.scheduledTime > Date.now())
                .slice(0, 5) // Show first 5
                .map(a => {
                  const timeUntil = Math.round((a.scheduledTime - Date.now()) / 1000 / 60);
                  return `• ${a.name} in ${timeUntil} minutes (${new Date(a.scheduledTime).toLocaleString()})`;
                })
                .join('\n');
              
              if (upcomingAlarms) {
                console.log(`[TabSensei] Upcoming alarms:\n${upcomingAlarms}`);
              }
            }
          });
        }, 500);
        
        chrome.alarms.get(checkAlarmName, async (alarm) => {
          if (alarm) {
            const timeUntil = Math.round((alarm.scheduledTime - Date.now()) / 1000 / 60);
            console.log(`[TabSensei] ✓ Verified alarm exists: "${checkAlarmName}" scheduled for ${new Date(alarm.scheduledTime).toLocaleString()} (in ${timeUntil} minutes)`);
            // Get all active reminders to show count
            const allReminders = await listActiveReminders();
            
            // Show Chrome notification that reminder is set
            try {
              const notificationMsg = recurring 
                ? `${message}\n\nDaily reminder starting: ${formattedDate}`
                : `${message}\n\nScheduled for: ${formattedDate}`;
              chrome.notifications.create({
                type: "basic",
                iconUrl: chrome.runtime.getURL("popup/icon128.png"),
                title: "✅ Reminder Set!",
                message: notificationMsg,
                priority: 2
              }, (notificationId) => {
                if (chrome.runtime.lastError) {
                  console.error("[TabSensei] Failed to show confirmation notification:", chrome.runtime.lastError.message);
                  // If notification permission is denied, inform the user
                  if (chrome.runtime.lastError.message.includes("permission") || chrome.runtime.lastError.message.includes("denied")) {
                    const errorMsg = `⚠️ **Notification permission denied.** Please enable notifications in Chrome settings (chrome://settings/content/notifications) for this extension to receive reminders.`;
                    chatHistory.push({ role: "system", text: errorMsg });
                    saveHistory();
                    renderHistory();
                  }
                } else {
                  console.log("[TabSensei] Confirmation notification created with ID:", notificationId);
                }
              });
            } catch (err) {
              console.warn("Could not show notification:", err);
            }
            
            // Add detailed confirmation message to chat
            const recurringText = recurring ? `\n🔄 **Recurring:** Daily reminder (set for next 30 days)\n` : '';
            const nextReminderText = recurring && daysUntil > 0 
              ? `\n📌 **Note:** The first reminder will fire tomorrow at ${reminderDate.toLocaleTimeString()} (since the time has passed today).\n`
              : '';
            const reminderMsg = `✅ **Reminder confirmed and set!**\n\n` +
              `📅 **When:** ${formattedDate}${recurringText}${nextReminderText}` +
              `⏰ **Time until reminder:** ${timeUntilText}\n` +
              `📝 **Message:** "${message}"\n\n` +
              `You'll receive a desktop notification at the scheduled time.\n\n` +
              `💡 **Tip:** You have ${allReminders.length} active reminder${allReminders.length !== 1 ? 's' : ''}. Ask "show my reminders" to see them all.`;
            chatHistory.push({ role: "system", text: reminderMsg });
            saveHistory();
            renderHistory();
          } else {
            // Alarm creation failed
            const errorMsg = `⚠️ **Reminder creation failed.** Please try again or check Chrome notification permissions.`;
            chatHistory.push({ role: "system", text: errorMsg });
            saveHistory();
            renderHistory();
          }
        });
      } else {
        console.warn("[TabSensei] Reminder time is in the past!");
        const errorMsg = `⚠️ Could not set reminder: The specified time is in the past.`;
        chatHistory.push({ role: "system", text: errorMsg });
        saveHistory();
        renderHistory();
      }
    }

    // Handle price alert
    if (response.price_alert) {
      safeSendMessage({
        action: "addToWatchlist",
        data: response.price_alert
      }, (res) => {
        if (res && res.error) {
          console.error("Failed to add to watchlist:", res.error);
        } else {
          console.log("Added to watchlist via natural language");
        }
      });
    }

    // Render with typewriter animation - pass callback for when it completes
    typeText(response.reply, () => {
      // This callback runs AFTER the typewriter animation completes

      const hasSuggestedCloseTabs =
        Array.isArray(response.suggested_close_tab_ids) &&
        response.suggested_close_tab_ids.length > 0;

      // If the user explicitly asked to close tabs (e.g. "please close tabs not relevant to X and Y")
      // AND we have suggested_close_tab_ids from the backend, auto-close them immediately.
      if (wantsAutoCloseTabs && hasSuggestedCloseTabs) {
        safeSendMessage(
          { action: "closeTabs", tabIds: response.suggested_close_tab_ids },
          (res) => {
            const ok = res && res.ok;
            const msg = ok
              ? `✅ Closed ${response.suggested_close_tab_ids.length} tabs that were not relevant to your request.`
              : `⚠️ Could not close tabs: ${res?.error || "unknown error"}`;
            chatHistory.push({ role: "system", text: msg });
            saveHistory();
            renderHistory();
          }
        );
      } else if (hasSuggestedCloseTabs) {
        // Otherwise, just show a button so the user can choose to close them.
        renderCloseTabsButton(response.suggested_close_tab_ids);
      }

      // Show price info and watchlist option for shopping tabs
      if (response.price_info && Object.keys(response.price_info).length > 0) {
        renderWatchlistButtons(response.price_info);
      }

      // Show alerts if any
      if (response.alerts && response.alerts.length > 0) {
        renderAlerts(response.alerts);
      }

      // AFTER answer is fully displayed, ask whether to close unrelated tabs
      // Skip this if we already auto-closed tabs for this query.
      if (shouldShowCleanup && !wantsAutoCloseTabs) {
        askCleanupAfterAnswer();
      }
    });
  });
});

// === Smooth Typewriter Markdown Rendering ===
function typeText(text, onComplete) {
  // Find the last assistant message in the output
  const existingMessages = output.querySelectorAll('.msg.assistant');
  let typingEl = null;
  let container = null;

  if (existingMessages.length > 0) {
    container = existingMessages[existingMessages.length - 1];
    container.innerHTML = `<b>Tab Sensei:</b><div id="typing" class="msg-text"></div>`;
    typingEl = container.querySelector("#typing");
  } else {
    container = document.createElement("div");
    container.classList.add("msg", "assistant");
    container.innerHTML = `<b>Tab Sensei:</b><div id="typing" class="msg-text"></div>`;
    output.appendChild(container);
    typingEl = container.querySelector("#typing");
  }

  output.scrollTop = output.scrollHeight;

  const html = `<div class="markdown-body">${marked.parse(text)}</div>`;
  let i = 0;
  const interval = setInterval(() => {
    typingEl.innerHTML = html.slice(0, i);
    i++;
    if (i > html.length) {
      clearInterval(interval);
      // Update chat history
      const lastAssistantIdx = chatHistory.length - 1;
      if (lastAssistantIdx >= 0 && chatHistory[lastAssistantIdx].role === "assistant") {
        chatHistory[lastAssistantIdx].text = text;
        saveHistory();
      }
      renderHistory();
      if (onComplete && typeof onComplete === 'function') {
        setTimeout(onComplete, 100);
      }
    }
    output.scrollTop = output.scrollHeight;
  }, 8);
}

// === Close button handler ===
if (closeBtn) {
  closeBtn.addEventListener("click", () => {
    // If in iframe (overlay mode), send message to parent to close
    if (window.parent !== window) {
      window.parent.postMessage("ticai-close", "*");
      safeSendMessage({ action: "setTicaiOpen", value: false }, (response) => {
        if (response && response.error) {
          if (!response.error.includes("Extension context invalidated") &&
            !response.error.includes("message port closed")) {
            console.warn("Could not notify background of close:", response.error);
          }
        }
      });
    } else {
      // Popup mode - close normally
      const container = document.querySelector(".container");
      if (container) {
        container.classList.add("fade-out");
        setTimeout(() => window.close(), 300);
      } else {
        window.close();
      }
    }
  });
}

// === Check extension context validity on load ===
function checkExtensionContext() {
  try {
    // Try to access chrome.runtime - if context is invalidated, this will throw
    if (typeof chrome === 'undefined' || !chrome.runtime) {
      return false;
    }
    
    // Try to access chrome.runtime.id - this can throw if context is invalidated
    try {
      const runtimeId = chrome.runtime.id;
      if (!runtimeId) {
        return false;
      }
    } catch (e) {
      // Context invalidated - accessing id throws
      return false;
    }
    
    return true;
  } catch (e) {
    // Context invalidated - accessing chrome.runtime throws
    return false;
  }
}

// === Listen for refresh history message from parent (when overlay opens on new tab) ===
window.addEventListener("message", (event) => {
  // Only accept messages from same origin (extension pages)
  if (event.data && event.data.action === "refreshHistory") {
    console.log("[TabSensei] Received refresh history request");
    // Force reload from storage and re-render
    loadHistory(); // Reload history from storage
    // Scroll to bottom after delays to ensure content is rendered
    setTimeout(() => {
      const output = document.getElementById("output");
      if (output) {
        output.scrollTop = output.scrollHeight;
      }
    }, 100);
    setTimeout(() => {
      const output = document.getElementById("output");
      if (output) {
        output.scrollTop = output.scrollHeight;
      }
    }, 300);
    setTimeout(() => {
      const output = document.getElementById("output");
      if (output) {
        output.scrollTop = output.scrollHeight;
      }
    }, 500);
  }
});

// === Initialize panel on load ===
try {
  if (checkExtensionContext()) {
    // Load history - this will check backend session and clear if needed
    loadHistory();
    
    // Periodically check backend session to catch restarts (every 5 seconds)
    setInterval(async () => {
      try {
        // Check context before each check
        if (!checkExtensionContext()) {
          return; // Context invalidated, skip this check
        }
        const wasCleared = await checkBackendSession();
        if (wasCleared) {
          console.log("[TabSensei] Backend session changed, history cleared");
          // History already cleared and rendered by checkBackendSession
        }
      } catch (e) {
        // Silently fail - backend might be temporarily down
        console.warn("[TabSensei] Failed to check backend session:", e.message);
      }
    }, 5000); // Check every 5 seconds
  } else {
    // Context invalidated - show error message
    try {
      const errorMsg = "⚠️ Extension context invalidated. Please reload the extension from chrome://extensions/";
      chatHistory = [{ role: "system", text: errorMsg }];
      renderHistory();
    } catch (renderError) {
      // Can't even render error - context is fully invalidated
      console.error("[TabSensei] Context invalidated, cannot render error message");
    }
  }
} catch (e) {
  // If anything throws during initialization, show error
  console.error("[TabSensei] Error during initialization:", e);
  try {
    const errorMsg = "⚠️ Extension context invalidated. Please reload the extension from chrome://extensions/";
    chatHistory = [{ role: "system", text: errorMsg }];
    renderHistory();
  } catch (renderError) {
    // Can't render - context is fully invalidated
    console.error("[TabSensei] Context invalidated, cannot render error message");
  }
}

// === New Chat Button and Startup Cleanup Prompt ===
(async function initHeader() {
  if (header) {
    newChatBtn = document.createElement("button");
    newChatBtn.textContent = "New Chat";
    newChatBtn.id = "newChatBtn";
    newChatBtn.style.marginLeft = "8px";
    newChatBtn.className = "ticai-btn secondary";
    newChatBtn.addEventListener("click", async () => {
      chatHistory = [];
      await chrome.storage.local.remove(["ticaiHistory", "ticaiAskedCleanup"]);
      renderHistory();
      // Defer cleanup prompt until after first answer
    });
    header.appendChild(newChatBtn);
  }
})();

async function askCleanupAfterAnswer() {
  const { ticaiAskedCleanup } = await chrome.storage.local.get("ticaiAskedCleanup");
  if (ticaiAskedCleanup) return;

  const container = document.createElement("div");
  container.className = "msg assistant";
  container.innerHTML = `
    <b>Tab Sensei:</b>
    <div class="msg-text">
      Would you like to close unrelated tabs and focus only on relevant ones? (Yes/No)
      <div style="margin-top:8px; display:flex; gap:8px;">
        <button id="cleanupYes" class="ticai-btn">Yes</button>
        <button id="cleanupNo" class="ticai-btn secondary">No</button>
      </div>
    </div>
  `;
  output.appendChild(container);
  output.scrollTop = output.scrollHeight;

  const yesBtn = container.querySelector("#cleanupYes");
  const noBtn = container.querySelector("#cleanupNo");
  const finalize = async (val) => {
    await chrome.storage.local.set({ ticaiAskedCleanup: true });
    container.remove();
    if (val === "yes") {
      // Trigger cleanup mode with a neutral focus query
      safeSendMessage({ action: "analyzeTabs", query: "keep only the tabs relevant to my current focus" }, (response) => {
        if (response && response.error) {
          chatHistory.push({ role: "system", text: `Error: ${response.error}` });
          saveHistory();
          renderHistory();
          return;
        }
        // Suppress verbose cleanup reply; just act and confirm
        // If we have suggested tabs to close, close them immediately (user already said Yes)
        if (response && Array.isArray(response.suggested_close_tab_ids) && response.suggested_close_tab_ids.length) {
          safeSendMessage({ action: "closeTabs", tabIds: response.suggested_close_tab_ids }, (res) => {
            if (res && res.error) {
              chatHistory.push({ role: "system", text: `Could not close tabs: ${res.error}` });
            } else {
              const msg = res?.ok ? `Closed ${response.suggested_close_tab_ids.length} tabs.` : `Could not close tabs: ${res?.error || "unknown error"}`;
              chatHistory.push({ role: "system", text: msg });
            }
            saveHistory();
            renderHistory();
          });
        }
        if (!response?.suggested_close_tab_ids?.length) {
          chatHistory.push({ role: "system", text: "No unrelated tabs detected to close." });
          saveHistory();
          renderHistory();
        }
      });
    }
  };
  yesBtn.addEventListener("click", () => finalize("yes"));
  noBtn.addEventListener("click", () => finalize("no"));
}

function renderCloseTabsButton(tabIds) {
  const wrap = document.createElement("div");
  wrap.style.margin = "10px";
  const btnEl = document.createElement("button");
  btnEl.textContent = `Close ${tabIds.length} tabs`;
  btnEl.className = "ticai-btn danger";
  btnEl.addEventListener("click", () => {
    safeSendMessage({ action: "closeTabs", tabIds }, (res) => {
      if (res && res.error) {
        chatHistory.push({ role: "system", text: `Error: ${res.error}` });
      } else {
        const msg = res?.ok ? `Closed ${tabIds.length} tabs.` : `Could not close tabs: ${res?.error || "unknown error"}`;
        chatHistory.push({ role: "system", text: msg });
      }
      saveHistory();
      renderHistory();
    });
  });
  wrap.appendChild(btnEl);
  output.appendChild(wrap);
  output.scrollTop = output.scrollHeight;
}

function renderWatchlistButtons(priceInfo) {
  for (const [tabId, info] of Object.entries(priceInfo)) {
    if (!info.price) continue;
    const wrap = document.createElement("div");
    wrap.style.margin = "10px";
    wrap.innerHTML = `
      <div style="background: rgba(100,200,100,0.1); padding: 8px; border-radius: 6px; margin-bottom: 8px;">
        <strong>${info.product_name || "Product"}</strong><br>
        Price: ${info.currency || "$"}${info.price.toFixed(2)}
      </div>
    `;
    const btnEl = document.createElement("button");
    btnEl.textContent = "Track Price";
    btnEl.className = "ticai-btn";
    btnEl.addEventListener("click", () => {
      showThresholdDialog(info);
    });
    wrap.appendChild(btnEl);
    output.appendChild(wrap);
  }
  output.scrollTop = output.scrollHeight;
}

function showThresholdDialog(productInfo) {
  // Create modal overlay
  const overlay = document.createElement("div");
  overlay.style.cssText = "position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;";

  const dialog = document.createElement("div");
  dialog.style.cssText = "background: #1a1a28; padding: 20px; border-radius: 12px; max-width: 400px; width: 90%; border: 1px solid rgba(150,150,255,0.3);";
  dialog.innerHTML = `
    <h3 style="margin-top: 0; color: #e4e4ff;">Track Price Drop</h3>
    <p style="color: #8c8cff; font-size: 13px; margin-bottom: 15px;">
      Get notified when the price drops by your specified amount.
    </p>
    <div style="margin-bottom: 15px;">
      <label style="display: block; color: #e4e4ff; margin-bottom: 5px; font-size: 13px;">Alert me when price drops by:</label>
      <div style="display: flex; gap: 10px; align-items: center;">
        <input type="number" id="thresholdValue" placeholder="10" step="0.01" min="0" 
               style="flex: 1; padding: 8px; background: #0f0f1a; border: 1px solid #333; border-radius: 6px; color: #fff; font-size: 14px;">
        <select id="thresholdType" style="padding: 8px; background: #0f0f1a; border: 1px solid #333; border-radius: 6px; color: #fff; font-size: 14px;">
          <option value="percentage">%</option>
          <option value="absolute">${productInfo.currency || "$"}</option>
        </select>
      </div>
      <p style="color: #8c8cff; font-size: 11px; margin-top: 5px; margin-bottom: 0;">
        Example: 10% or ${productInfo.currency || "$"}5.00
      </p>
    </div>
    <div style="display: flex; gap: 10px; justify-content: flex-end;">
      <button id="cancelBtn" class="ticai-btn" style="background: #333;">Cancel</button>
      <button id="addBtn" class="ticai-btn">Add to Watchlist</button>
    </div>
  `;

  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  const thresholdValue = dialog.querySelector("#thresholdValue");
  const thresholdType = dialog.querySelector("#thresholdType");
  const cancelBtn = dialog.querySelector("#cancelBtn");
  const addBtn = dialog.querySelector("#addBtn");

  cancelBtn.addEventListener("click", () => {
    document.body.removeChild(overlay);
  });

  addBtn.addEventListener("click", () => {
    const value = parseFloat(thresholdValue.value);
    const type = thresholdType.value;

    if (isNaN(value) || value <= 0) {
      alert("Please enter a valid threshold value.");
      return;
    }

    safeSendMessage({
      action: "addToWatchlist",
      data: {
        product_name: productInfo.product_name,
        url: productInfo.url,
        price: productInfo.price,
        currency: productInfo.currency || "USD",
        alert_threshold: value,
        threshold_type: type,
      },
    }, (res) => {
      document.body.removeChild(overlay);
      if (res && res.error) {
        chatHistory.push({ role: "system", text: `Error: ${res.error}` });
      } else {
        const msg = res?.ok ? (res.message || `Added to watchlist! Alert set for ${value}${type === "percentage" ? "%" : " " + (productInfo.currency || "USD")} drop.`) : `Failed: ${res?.error || "unknown error"}`;
        chatHistory.push({ role: "system", text: msg });
      }
      saveHistory();
      renderHistory();
    });
  });

  // Close on overlay click
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      document.body.removeChild(overlay);
    }
  });
}

function renderAlerts(alerts) {
  if (!alerts || alerts.length === 0) return;

  const wrap = document.createElement("div");
  wrap.style.margin = "10px";
  wrap.style.background = "rgba(255,200,100,0.2)";
  wrap.style.padding = "12px";
  wrap.style.borderRadius = "8px";
  wrap.style.border = "1px solid rgba(255,200,100,0.4)";
  wrap.innerHTML = `<strong style="color: #ffcc66;">🔔 Price Alerts (${alerts.length})</strong><br>`;

  alerts.forEach((alert, index) => {
    const alertDiv = document.createElement("div");
    alertDiv.style.marginTop = index > 0 ? "10px" : "8px";
    alertDiv.style.padding = "8px";
    alertDiv.style.background = "rgba(0,0,0,0.2)";
    alertDiv.style.borderRadius = "6px";
    alertDiv.style.fontSize = "13px";

    const message = alert.message || alert.alert_type || "Price alert";
    const dropInfo = alert.drop_percent ? ` (${alert.drop_percent.toFixed(1)}% drop)` : "";
    const priceInfo = alert.old_price && alert.new_price ?
      ` <span style="color: #8c8cff;">${alert.old_price.toFixed(2)} → ${alert.new_price.toFixed(2)}</span>` : "";

    alertDiv.innerHTML = `
      <div style="color: #e4e4ff;">${message}${dropInfo}${priceInfo}</div>
      <button class="mark-read-btn" data-alert-id="${alert.id}" 
              style="margin-top: 4px; padding: 4px 8px; background: rgba(100,100,255,0.3); 
                     border: none; border-radius: 4px; color: #8c8cff; font-size: 11px; cursor: pointer;">
        Mark as read
      </button>
    `;

    const markReadBtn = alertDiv.querySelector(".mark-read-btn");
    markReadBtn.addEventListener("click", () => {
      fetch(`http://localhost:8000/alerts/${alert.id}/read`, { method: "POST" })
        .then(res => res.json())
        .then(data => {
          if (data.ok) {
            alertDiv.style.opacity = "0.5";
            markReadBtn.textContent = "Read";
            markReadBtn.disabled = true;
          }
        })
        .catch(err => console.warn("Failed to mark alert as read:", err));
    });

    wrap.appendChild(alertDiv);
  });

  // Add "Mark all as read" button
  if (alerts.length > 1) {
    const markAllBtn = document.createElement("button");
    markAllBtn.textContent = "Mark all as read";
    markAllBtn.className = "ticai-btn";
    markAllBtn.style.marginTop = "10px";
    markAllBtn.addEventListener("click", () => {
      fetch("http://localhost:8000/alerts/read-all", { method: "POST" })
        .then(res => res.json())
        .then(data => {
          if (data.ok) {
            wrap.style.opacity = "0.5";
            markAllBtn.textContent = "All read";
            markAllBtn.disabled = true;
          }
        })
        .catch(err => console.warn("Failed to mark all alerts as read:", err));
    });
    wrap.appendChild(markAllBtn);
  }

  // Insert at the top of output
  output.insertBefore(wrap, output.firstChild);
  output.scrollTop = 0;
}
