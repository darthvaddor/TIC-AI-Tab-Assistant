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

// --- Load existing history ---
async function loadHistory() {
  const stored = await chrome.storage.local.get("ticaiHistory");
  chatHistory = stored.ticaiHistory || [];
  renderHistory();
}

// --- Save updated history ---
function saveHistory() {
  chrome.storage.local.set({ ticaiHistory: chatHistory });
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

  // Send message to background.js
  chrome.runtime.sendMessage({ action: "analyzeTabs", query }, (response) => {
    clearInterval(dotInterval);
    thinking.style.display = "none";

    // Handle runtime or missing reply errors
    if (chrome.runtime.lastError) {
      const msg = `<span style="color:red;">${chrome.runtime.lastError.message}</span>`;
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      return;
    }

    if (!response || !response.reply) {
      const msg = `<span style="color:red;">No response received.</span>`;
      chatHistory.push({ role: "system", text: msg });
      renderHistory();
      saveHistory();
      return;
    }

    // Append assistant message
    chatHistory.push({ role: "assistant", text: response.reply });
    saveHistory();

    // Render with typewriter animation
    typeText(response.reply);

    // If cleanup suggestions exist, render a Close Tabs button
    if (Array.isArray(response.suggested_close_tab_ids) && response.suggested_close_tab_ids.length) {
      renderCloseTabsButton(response.suggested_close_tab_ids);
    }

    // After first answer (non-cleanup), ask whether to close unrelated tabs
    if (response && response.mode !== "cleanup") {
      askCleanupAfterAnswer();
    }
  });
});

// === Smooth Typewriter Markdown Rendering ===
function typeText(text) {
  const html = `<div class="markdown-body">${marked.parse(text)}</div>`;
  const container = document.createElement("div");
  container.classList.add("msg", "assistant");
  container.innerHTML = `<b>TIC-AI:</b><div id="typing" class="msg-text"></div>`;
  output.appendChild(container);
  output.scrollTop = output.scrollHeight;

  const typingEl = container.querySelector("#typing");

  let i = 0;
  const interval = setInterval(() => {
    typingEl.innerHTML = html.slice(0, i);
    i++;
    if (i > html.length) {
      clearInterval(interval);
      renderHistory(); // finalize render
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
      // Also notify background to clear state
      chrome.runtime.sendMessage({ action: "setTicaiOpen", value: false });
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
      chrome.runtime.sendMessage({ action: "analyzeTabs", query: "keep only the tabs relevant to my current focus" }, (response) => {
        // Suppress verbose cleanup reply; just act and confirm
        // If we have suggested tabs to close, close them immediately (user already said Yes)
        if (response && Array.isArray(response.suggested_close_tab_ids) && response.suggested_close_tab_ids.length) {
          chrome.runtime.sendMessage({ action: "closeTabs", tabIds: response.suggested_close_tab_ids }, (res) => {
            const msg = res?.ok ? `Closed ${response.suggested_close_tab_ids.length} tabs.` : `Could not close tabs: ${res?.error || "unknown error"}`;
            chatHistory.push({ role: "system", text: msg });
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
    chrome.runtime.sendMessage({ action: "closeTabs", tabIds }, (res) => {
      // Optionally notify
      const msg = res?.ok ? `Closed ${tabIds.length} tabs.` : `Could not close tabs: ${res?.error || "unknown error"}`;
      chatHistory.push({ role: "system", text: msg });
      saveHistory();
      renderHistory();
    });
  });
  wrap.appendChild(btnEl);
  output.appendChild(wrap);
  output.scrollTop = output.scrollHeight;
}
