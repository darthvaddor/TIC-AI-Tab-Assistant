// background.js — TIC-AI Tab Assistant
console.log("TIC-AI background service running.");

// === Backend endpoint ===
const BACKEND_URL = "http://localhost:8000/run_agent";

// === Helper: Inject the overlay if not already active ===
async function ensureOverlay(tabId) {
  try {
    await chrome.scripting.insertCSS({
      target: { tabId },
      files: ["content/overlay.css"],
    });
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content/overlay.js"],
    });
  } catch (err) {
    console.warn("Overlay already injected or cannot inject:", err.message);
  }
}

// === Collect text from open tabs ===
async function collectTabData() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const collected = [];

  for (const tab of tabs) {
    if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
      console.warn("Skipping restricted tab:", tab.url);
      continue;
    }

    try {
      const result = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const text = document.body?.innerText?.slice(0, 4000) || "";
          return {
            title: document.title,
            url: window.location.href,
            text,
          };
        },
      });

      if (result && result[0] && result[0].result) {
        collected.push({ id: tab.id, ...result[0].result });
      }
    } catch (err) {
      console.warn(`Failed to extract from ${tab.url}:`, err.message);
    }
  }

  return collected;
}

// === Core logic: Send query to backend ===
async function handleQuery(query) {
  try {
    const tabs = await collectTabData();
    if (!tabs.length) {
      return { reply: "No accessible tabs found (system/extension pages blocked).", mode: "single" };
    }

    const payload = { query, tabs };
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`Backend error ${res.status}: ${res.statusText}`);

    const data = await res.json();
    console.log("[Backend Reply]", data);

    // === Handle each mode ===
    if (data.mode === "single") {
      console.log("Mode: SINGLE → focusing on one tab");
      if (data.chosen_tab_id) {
        await chrome.tabs.update(data.chosen_tab_id, { active: true });
        // Persist overlay on target tab
        await ensureOverlay(data.chosen_tab_id);
        await chrome.storage.local.set({ ticaiOpen: true });
        chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" });
      }
    }

    else if (data.mode === "multi") {
      console.log("Mode: MULTI → showing comparison results");
      if (data.chosen_tab_id) {
        await chrome.tabs.update(data.chosen_tab_id, { active: true });
        await ensureOverlay(data.chosen_tab_id);
        await chrome.storage.local.set({ ticaiOpen: true });
        chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" });
      }
    }

    else if (data.mode === "cleanup") {
      console.log("Mode: CLEANUP → cleaning unrelated tabs");
      if (data.chosen_tab_id) {
        await chrome.tabs.update(data.chosen_tab_id, { active: true });
        await ensureOverlay(data.chosen_tab_id);
        await chrome.storage.local.set({ ticaiOpen: true });
        chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" });
      }
      // Service workers cannot show confirm dialogs. Defer to UI layer to confirm and close.
      // Return the suggested IDs in the response so panel.js can present a button.
    }

    return data;
  } catch (err) {
    console.error("Error handling query:", err);
    return { reply: `Error: ${err.message}`, mode: "single" };
  }
}

// === Receive messages from popup (Ask button) ===
chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === "analyzeTabs") {
    (async () => {
      const result = await handleQuery(req.query);
      sendResponse(result);
    })();
    return true; // Keep async channel open
  }
  if (req.action === "closeTabs" && Array.isArray(req.tabIds)) {
    (async () => {
      try {
        await chrome.tabs.remove(req.tabIds);
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: e?.message || String(e) });
      }
    })();
    return true;
  }
});

// === Extension icon toggles overlay ===
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab || !tab.id) return;
  if (!tab.url || !tab.url.startsWith("http")) {
    console.warn("Restricted page, cannot open overlay:", tab.url);
    return;
  }

  await ensureOverlay(tab.id);
  chrome.tabs.sendMessage(tab.id, { action: "toggleAssistant" });
});

// === Remember if the assistant is open ===
chrome.runtime.onMessage.addListener((req) => {
  if (req.action === "setTicaiOpen") {
    chrome.storage.local.set({ ticaiOpen: req.value });
  }
});

// === Reinstate overlay after switching tabs (persistence) ===
chrome.tabs.onActivated.addListener(async (info) => {
  const { ticaiOpen } = await chrome.storage.local.get("ticaiOpen");
  if (ticaiOpen) {
    const tab = await chrome.tabs.get(info.tabId);
    if (tab.url.startsWith("http")) {
      try {
        await ensureOverlay(tab.id);
      } catch (e) {
        console.warn("Failed to reinject overlay:", e.message);
      }
    }
  }
});

// === On install ===
chrome.runtime.onInstalled.addListener(() => {
  console.log("TIC-AI Assistant installed successfully.");
});
