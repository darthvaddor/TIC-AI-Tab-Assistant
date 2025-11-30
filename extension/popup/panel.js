import { marked } from "./libs/marked.esm.js";

// === DOM Elements ===
const btn = document.getElementById("askBtn");
const promptBox = document.getElementById("prompt");
const output = document.getElementById("output");
const thinking = document.getElementById("thinking");
const closeBtn = document.getElementById("closeBtn");
const clearBtn = document.getElementById("clearBtn");
// Dynamically add New Chat button in header
const header = document.querySelector(".bot-header");
let newChatBtn = null;

// === Local chat history (stored in chrome.storage.local) ===
let chatHistory = [];
let isProcessing = false; // Prevent multiple simultaneous queries

// Clear chat history
if (clearBtn) {
  clearBtn.addEventListener("click", () => {
    chatHistory = [];
    saveHistory();
    renderHistory();
  });
}

// === Safe message sender (handles extension context invalidation) ===
function safeSendMessage(message, callback) {
  try {
    // Check if chrome.runtime is available
    if (!chrome.runtime || !chrome.runtime.sendMessage) {
      if (callback) {
        callback({ error: "Extension context invalidated. Please reload the extension." });
      }
      return;
    }

    // Try to send message with error handling
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        const error = chrome.runtime.lastError.message;
        // Handle context invalidation gracefully
        if (error.includes("Extension context invalidated") ||
          error.includes("message channel closed")) {
          // Silently handle context invalidation - common during reloading
          if (callback) {
            callback({ error: "Extension context invalidated. Please reload the extension." });
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
        callback(response);
      }
    });
  } catch (err) {
    console.error("Failed to send message:", err);
    if (callback) {
      callback({ error: err.message || "Failed to send message" });
    }
  }
}

// --- Load existing history ---
async function loadHistory() {
  const stored = await chrome.storage.local.get("ticaiHistory");
  chatHistory = stored.ticaiHistory || [];
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
function saveHistory() {
  try {
    // Check if extension context is valid
    if (chrome.runtime && chrome.runtime.id) {
      // Use callback style to prevent Promise return and unhandled rejections
      chrome.storage.local.set({ ticaiHistory: chatHistory }, () => {
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

// --- Render conversation thread ---
function renderHistory() {
  output.innerHTML = chatHistory
    .map(
      (m) =>
        `<div class="msg ${m.role}">
           <b>${m.role === "user" ? "You" : "TIC-AI"}:</b>
           <div class="msg-text markdown-body">${marked.parse(m.text)}</div>
         </div>`
    )
    .join("<hr style='opacity:0.05;border:none;'>");

  // Auto-scroll to bottom on new message
  output.scrollTop = output.scrollHeight;
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

  // Append user message
  chatHistory.push({ role: "user", text: query });
  renderHistory();
  saveHistory();

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

    // Append assistant message
    chatHistory.push({ role: "assistant", text: response.reply });
    saveHistory();

    // Store response for cleanup prompt (will be shown after typewriter completes)
    const shouldShowCleanup = response && response.mode !== "cleanup" && response.should_ask_cleanup;

    // Render with typewriter animation - pass callback for when it completes
    typeText(response.reply, () => {
      // This callback runs AFTER the typewriter animation completes

      // If cleanup suggestions exist, render a Close Tabs button
      if (Array.isArray(response.suggested_close_tab_ids) && response.suggested_close_tab_ids.length) {
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
      // Only ask if backend indicates it should (for specific single-tab queries, not "analyze all")
      if (shouldShowCleanup) {
        askCleanupAfterAnswer();
      }
    });
  });
});

// === Smooth Typewriter Markdown Rendering ===
function typeText(text, onComplete) {
  // Find the last assistant message in the output (should be the one we just added)
  const existingMessages = output.querySelectorAll('.msg.assistant');
  let typingEl = null;
  let container = null;

  if (existingMessages.length > 0) {
    // Use the last assistant message container
    container = existingMessages[existingMessages.length - 1];
    // Clear its content and add typing element
    container.innerHTML = `<b>TIC-AI:</b><div id="typing" class="msg-text"></div>`;
    typingEl = container.querySelector("#typing");
  } else {
    // Fallback: create new container if none exists
    container = document.createElement("div");
    container.classList.add("msg", "assistant");
    container.innerHTML = `<b>TIC-AI:</b><div id="typing" class="msg-text"></div>`;
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
      // Update chat history to ensure it matches
      const lastAssistantIdx = chatHistory.length - 1;
      if (lastAssistantIdx >= 0 && chatHistory[lastAssistantIdx].role === "assistant") {
        chatHistory[lastAssistantIdx].text = text;
        saveHistory();
      }
      // Final render to ensure consistency (this replaces the typewriter container with final rendered version)
      renderHistory();
      // Call completion callback if provided
      if (onComplete && typeof onComplete === 'function') {
        setTimeout(onComplete, 100); // Small delay to ensure render is complete
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
      // Also notify background to clear state (silently fail if context invalidated)
      safeSendMessage({ action: "setTicaiOpen", value: false }, (response) => {
        if (response && response.error) {
          // Silently ignore context invalidation errors during close
          if (!response.error.includes("Extension context invalidated")) {
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

// === Initialize panel on load ===
loadHistory();

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
    <b>TIC-AI:</b>
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
