// background.js — TIC-AI Tab Assistant
console.log("TIC-AI background service running.");

// Check for price alerts on startup
chrome.runtime.onStartup.addListener(() => {
  checkPriceAlerts();
});

chrome.runtime.onInstalled.addListener(() => {
  checkPriceAlerts();
});

async function checkPriceAlerts() {
  try {
    const res = await fetch("http://localhost:8000/alerts");
    const data = await res.json();
    if (data.ok && data.alerts && data.alerts.length > 0) {
      // Store alerts for display when panel opens
      chrome.storage.local.set({ pendingAlerts: data.alerts });
      // Show badge with alert count
      chrome.action.setBadgeText({ text: String(data.count) });
      chrome.action.setBadgeBackgroundColor({ color: "#ff4444" });
    } else {
      chrome.action.setBadgeText({ text: "" });
    }
  } catch (e) {
    console.warn("Failed to check alerts:", e);
  }
}

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
          // Smart content extraction with site-specific logic
          let text = "";
          const url = window.location.href.toLowerCase();
          const hostname = window.location.hostname.toLowerCase();

          // Site-specific extraction
          if (hostname.includes('wikipedia.org')) {
            // Wikipedia: get main article content
            const mwContent = document.getElementById('mw-content-text') ||
              document.querySelector('.mw-parser-output') ||
              document.querySelector('#content');
            if (mwContent) {
              // Remove navigation boxes, infoboxes, references
              const clone = mwContent.cloneNode(true);
              clone.querySelectorAll('.navbox, .infobox, .reference, .mw-references-wrap, .hatnote, .dablink').forEach(el => el.remove());
              text = clone.innerText || "";
            }
          } else if (hostname.includes('google.com') && url.includes('/search')) {
            // Google Search: extract search results with multiple selector strategies
            const resultTexts = [];

            // Try multiple selectors for Google search results (Google changes their DOM frequently)
            const selectors = [
              '#search .g',           // Standard results
              '.g',                   // Generic result class
              '[data-ved]',           // Results with data-ved attribute
              '.tF2Cxc',              // Modern Google results
              '.yuRUbf',              // Another modern selector
              '.MjjYud',              // Another variant
              'div[data-hveid]',      // Results with hveid
              '.kp-header',           // Knowledge Panel Header
              '.kno-rdesc',           // Knowledge Panel Description
              '.xpdopen',             // Expanded results
              '.ifM9O',               // Featured Snippets
              '.c2xzTb',              // Answer box
              '.LGOjhe',              // Info box
              '[data-attrid]',        // Knowledge Graph attributes (birthdate, height, etc.)
              '.Z0LcW',               // Direct answer text
              '.wob_t'                // Weather temp
            ];

            let results = [];
            for (const selector of selectors) {
              results = document.querySelectorAll(selector);
              if (results.length > 0) break; // Use first selector that finds results
            }

            // Also try to get the search query itself
            const searchQuery = document.querySelector('input[name="q"]')?.value ||
              document.querySelector('textarea[name="q"]')?.value ||
              new URLSearchParams(window.location.search).get('q') || "";

            if (searchQuery) {
              resultTexts.push(`Search Query: ${searchQuery}`);
            }

            // Extract Knowledge Panel / Featured Snippet specifically
            const knowledgePanel = document.querySelector('.kp-header, .kno-rdesc, .xpdopen, .ifM9O, .c2xzTb, .LGOjhe, [data-attrid], .Z0LcW');
            if (knowledgePanel) {
              // For data-attrid, get the parent or specific text
              let kpText = "";
              if (knowledgePanel.hasAttribute('data-attrid')) {
                // Try to get the whole row or container
                const container = knowledgePanel.closest('.rVusze') || knowledgePanel.parentElement;
                kpText = container ? container.innerText : knowledgePanel.innerText;
              } else {
                kpText = knowledgePanel.innerText;
              }

              if (kpText && kpText.length > 5) {
                resultTexts.push(`*** Knowledge Panel / Answer ***\n${kpText}\n******************************`);
              }
            }

            // Extract results
            results.forEach((result, idx) => {
              // Try multiple title selectors
              const titleSelectors = ['h3', '.LC20lb', '.DKV0Md', 'h3.LC20lb', '.DKV0Md'];
              let title = "";
              for (const sel of titleSelectors) {
                const titleEl = result.querySelector(sel);
                if (titleEl) {
                  title = titleEl.innerText || titleEl.textContent || "";
                  break;
                }
              }

              // Try multiple snippet selectors
              const snippetSelectors = ['.VwiC3b', '.s', '.IsZvec', '.aCOpRe', '.MUxGbd', '.yXK7lf'];
              let snippet = "";
              for (const sel of snippetSelectors) {
                const snippetEl = result.querySelector(sel);
                if (snippetEl) {
                  snippet = snippetEl.innerText || snippetEl.textContent || "";
                  break;
                }
              }

              // Also try to get URL
              const linkEl = result.querySelector('a[href]');
              const url = linkEl ? linkEl.href : "";

              if (title || snippet) {
                const resultText = [];
                if (title) resultText.push(`Title: ${title}`);
                if (url) resultText.push(`URL: ${url}`);
                if (snippet) resultText.push(`Snippet: ${snippet}`);
                resultTexts.push(resultText.join('\n'));
              }
            });

            // If no results found with selectors, try fallback: extract visible text
            if (resultTexts.length === 0 || (resultTexts.length === 1 && resultTexts[0].startsWith('Search Query:'))) {
              const mainContent = document.querySelector('#main, #search, #center_col, [role="main"], #rso');
              if (mainContent) {
                // Get all text but filter out navigation/UI
                const clone = mainContent.cloneNode(true);
                clone.querySelectorAll('nav, header, footer, script, style, .gb, #gb, .gb_8, #gb_8').forEach(el => el.remove());
                const fallbackText = clone.innerText || "";
                if (fallbackText && fallbackText.length > 20) {
                  resultTexts.push(`Search Results Content:\n${fallbackText.substring(0, 5000)}`);
                }
              }

              // Last resort: try to get ANY visible text from body
              if (resultTexts.length === 0 || (resultTexts.length === 1 && resultTexts[0].startsWith('Search Query:'))) {
                const bodyClone = document.body.cloneNode(true);
                bodyClone.querySelectorAll('nav, header, footer, script, style, .gb, #gb, .gb_8, #gb_8, #gbwa, #gbwa').forEach(el => el.remove());
                const bodyText = bodyClone.innerText || "";
                // Extract lines that look like search results (have URLs, titles, etc.)
                const lines = bodyText.split('\n').filter(line => {
                  const trimmed = line.trim();
                  return trimmed.length > 10 &&
                    (trimmed.includes('http') ||
                      trimmed.match(/^[A-Z][a-z]+/) || // Starts with capital (likely title)
                      trimmed.length > 50); // Long lines likely contain snippets
                });
                if (lines.length > 0) {
                  resultTexts.push(`Search Results:\n${lines.slice(0, 20).join('\n')}`);
                }
              }
            }

            text = resultTexts.join('\n\n');

            // Ensure we have at least some content - try harder to extract
            if (!text || text.length < 20) {
              // Last resort: get page title and URL params
              const urlParams = new URLSearchParams(window.location.search);
              const query = urlParams.get('q') || '';

              // Try one more time with different approach - get all links and their text
              const allLinks = document.querySelectorAll('a[href]');
              const linkTexts = [];
              allLinks.forEach(link => {
                const href = link.href;
                const linkText = link.innerText || link.textContent || "";
                // Filter out navigation links
                if (href && !href.includes('google.com/search') &&
                  !href.includes('google.com/webhp') &&
                  linkText && linkText.length > 5 &&
                  !linkText.includes('Images') &&
                  !linkText.includes('Videos') &&
                  !linkText.includes('Maps')) {
                  linkTexts.push(`${linkText}: ${href}`);
                }
              });

              if (linkTexts.length > 0) {
                text = `Search Query: ${query}\n\nSearch Results:\n${linkTexts.slice(0, 15).join('\n')}`;
              } else {
                text = `Search Query: ${query}\n\nSearch results page for "${query}". Content extraction from Google search results is limited due to dynamic loading.`;
              }
            }
          } else if (hostname.includes('mail.google.com') || hostname.includes('gmail.com')) {
            // Gmail: extract email content
            const emailBody = document.querySelector('.a3s, .ii.gt, [role="main"] .ii') ||
              document.querySelector('[data-message-id] .ii');
            if (emailBody) {
              text = emailBody.innerText || "";
            } else {
              // Fallback: get email list
              const emails = document.querySelectorAll('.zA');
              const emailTexts = [];
              emails.forEach(email => {
                const subject = email.querySelector('.bog')?.innerText || "";
                const snippet = email.querySelector('.y2')?.innerText || "";
                if (subject) emailTexts.push(`${subject}${snippet ? ': ' + snippet : ''}`);
              });
              text = emailTexts.join('\n\n');
            }
          } else {
            // Generic site: try main content areas
            const mainSelectors = [
              'main',
              'article',
              '[role="main"]',
              '#content',
              '#main-content',
              '.content',
              '.main-content',
              '#article',
              '.article',
              '#post-content',
              '.post-content'
            ];

            let mainContent = null;
            for (const selector of mainSelectors) {
              const el = document.querySelector(selector);
              if (el && el.innerText && el.innerText.trim().length > 100) {
                mainContent = el;
                break;
              }
            }

            if (mainContent) {
              text = mainContent.innerText;
            } else {
              // Fallback: remove navigation/UI elements from body
              const body = document.body.cloneNode(true);
              const removeSelectors = [
                'script', 'style', 'noscript'
              ];
              removeSelectors.forEach(sel => {
                body.querySelectorAll(sel).forEach(el => el.remove());
              });
              text = body.innerText || "";
            }
          }

          // Aggressive cleanup: remove common UI/navigation text and HTML/CSS artifacts
          const uiPatterns = [
            /^\d+\s+languages/i,
            /^Article\s+Talk/i,
            /^Read\s+View\s+source/i,
            /^View\s+history/i,
            /^Appearance/i,
            /^From Wikipedia/i,
            /^Jump to content/i,
            /^Main menu/i,
            /^Search/i,
            /^Donate/i,
            /^Create account/i,
            /^Log in/i,
            /^Participate/i,
            /^Accessibility/i,
            /^Share/i,
            /^Filters/i,
            /^Tools/i,
            /^All\s+Images\s+Videos/i,
            /^Print all/i,
            /^In new window/i,
            /^Remove label/i,
            /^Inbox/i,
            /^Student Beans/i,
            /^Text\s+Small\s+Standard/i,
            /^Width\s+Standard/i,
            /^Color\s+\(beta\)/i,
            /^Automatic\s+Light\s+Dark/i
          ];

          // Remove CSS and HTML artifacts
          text = text
            .replace(/\{[^}]*\}/g, '') // Remove CSS rules
            .replace(/<[^>]+>/g, '') // Remove HTML tags
            .replace(/&[a-z]+;/gi, ' ') // Remove HTML entities
            .replace(/\s+/g, ' ') // Normalize whitespace
            .split('\n')
            .map(line => line.trim())
            .filter(line => {
              if (line.length < 3) return false;
              // Filter out lines that are just CSS/HTML
              if (/^[\.#]?[a-z-]+\s*\{/i.test(line)) return false;
              if (/^<[^>]+>/.test(line)) return false;
              // Filter out lines that are just CSS/HTML
              if (/^[\.#]?[a-z-]+\s*\{/i.test(line)) return false;
              if (/^<[^>]+>/.test(line)) return false;

              return true;
            })
            .join('\n')
            .replace(/\n{3,}/g, '\n\n') // Remove excessive newlines
            .slice(0, 15000); // Increased from 8000 to 15000 for better analysis

          // Extract price
          const pricePatterns = [/\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, /(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD/g];
          let price = null;
          for (const pattern of pricePatterns) {
            const matches = [...text.matchAll(pattern)];
            if (matches.length > 0) {
              const priceStr = matches[0][1] || matches[0][0];
              price = parseFloat(priceStr.replace(/,/g, ""));
              if (price > 0 && price < 1000000) break;
            }
          }

          // Extract product name
          const h1 = document.querySelector("h1")?.innerText || "";
          const productName = h1 || document.title.split(" - ")[0].split(" | ")[0];

          return {
            title: document.title,
            url: window.location.href,
            text,
            price,
            productName,
          };
        },
      });

      if (result && result[0] && result[0].result) {
        collected.push({ id: tab.id, ...result[0].result });
      } else {
        // Even if extraction fails, include the tab with basic info
        console.warn(`Extraction returned no result for tab ${tab.id}, adding with basic info`);
        collected.push({
          id: tab.id,
          title: tab.title || "Untitled",
          url: tab.url || "",
          text: "",
          price: null,
          productName: null
        });
      }
    } catch (err) {
      console.warn(`Failed to extract from ${tab.url}:`, err.message);
      // Include tab even if extraction fails
      collected.push({
        id: tab.id,
        title: tab.title || "Untitled",
        url: tab.url || "",
        text: "",
        price: null,
        productName: null
      });
    }
  }

  console.log(`[TabSensei] Collected ${collected.length} tabs out of ${tabs.length} total tabs`);
  return collected;
}

// === Core logic: Send query to backend ===
async function handleQuery(queryObj) {
  try {
    const query = queryObj.query;
    const tabs = await collectTabData();
    console.log(`[TabSensei] Collected ${tabs.length} tabs:`, tabs.map(t => ({ id: t.id, title: t.title, url: t.url })));

    if (!tabs.length) {
      return { reply: "No accessible tabs found (system/extension pages blocked).", mode: "single" };
    }

    const payload = { query, tabs, chat_history: queryObj.chatHistory || [] };
    console.log(`[TabSensei] Sending query: "${query}" with ${tabs.length} tabs`);

    // Add timeout to fetch request - 20 seconds for thorough analysis
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000); // 20 seconds

    let res;
    try {
      res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
    } catch (e) {
      clearTimeout(timeoutId);
      if (e.name === 'AbortError') {
        throw new Error("Request timed out. The backend is taking too long to respond. Please try again or check if the server is running.");
      }
      throw e;
    }

    if (!res.ok) throw new Error(`Backend error ${res.status}: ${res.statusText}`);

    const data = await res.json();
    console.log("[Backend Reply]", data);

    // NEW: Save chat history immediately to persist across popup closures (e.g. when switching tabs)
    if (data.reply && queryObj.chatHistory) {
      try {
        const newHistory = [...queryObj.chatHistory, { role: "assistant", text: data.reply }];
        await chrome.storage.local.set({ chatHistory: newHistory });
        console.log("[TabSensei] Saved chat history to storage before potential tab switch");
      } catch (err) {
        console.warn("[TabSensei] Failed to save chat history:", err);
      }
    }

    // === Handle each mode ===
    if (data.mode === "single") {
      console.log("Mode: SINGLE → focusing on one tab");
      if (data.chosen_tab_id) {
        try {
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            await chrome.tabs.update(data.chosen_tab_id, { active: true });
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
              console.warn("Failed to send message to tab:", err);
            });
          } else {
            console.warn(`Tab ${data.chosen_tab_id} no longer exists`);
          }
        } catch (err) {
          console.warn("Error switching to chosen tab:", err);
        }
      }
    }

    else if (data.mode === "multi") {
      console.log("Mode: MULTI → showing comparison results");
      if (data.chosen_tab_id) {
        try {
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            await chrome.tabs.update(data.chosen_tab_id, { active: true });
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
              console.warn("Failed to send message to tab:", err);
            });
          } else {
            console.warn(`Tab ${data.chosen_tab_id} no longer exists`);
          }
        } catch (err) {
          console.warn("Error switching to chosen tab:", err);
        }
      }
    }

    else if (data.mode === "cleanup") {
      console.log("Mode: CLEANUP → cleaning unrelated tabs");
      if (data.chosen_tab_id) {
        try {
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            await chrome.tabs.update(data.chosen_tab_id, { active: true });
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
              console.warn("Failed to send message to tab:", err);
            });
          }
        } catch (err) {
          console.warn("Error in cleanup mode:", err);
        }
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
      let responded = false;
      const safeSendResponse = (data) => {
        if (!responded) {
          responded = true;
          try {
            sendResponse(data);
          } catch (e) {
            console.error("Failed to send response:", e);
          }
        }
      };

      // Set timeout to ensure response is sent even if backend is slow
      const timeout = setTimeout(() => {
        if (!responded) {
          safeSendResponse({
            reply: "Request is taking longer than expected. The backend might be processing your tabs. Please wait a moment and try again.",
            mode: "single",
            error: "timeout"
          });
        }
      }, 35000); // 35 second timeout (slightly longer than fetch timeout)

      try {
        const result = await handleQuery(req);
        clearTimeout(timeout);
        safeSendResponse(result);
      } catch (e) {
        clearTimeout(timeout);
        console.error("Error in analyzeTabs:", e);
        safeSendResponse({
          reply: `Error: ${e?.message || String(e)}. Please check if the backend server is running.`,
          mode: "single",
          error: e?.message || String(e)
        });
      }
    })();
    return true; // Keep async channel open
  }
  if (req.action === "closeTabs" && Array.isArray(req.tabIds)) {
    (async () => {
      let responded = false;
      const safeSendResponse = (data) => {
        if (!responded) {
          responded = true;
          try {
            sendResponse(data);
          } catch (e) {
            console.error("Failed to send response:", e);
          }
        }
      };

      try {
        await chrome.tabs.remove(req.tabIds);
        safeSendResponse({ ok: true });
      } catch (e) {
        safeSendResponse({ ok: false, error: e?.message || String(e) });
      }
    })();
    return true;
  }
  if (req.action === "addToWatchlist") {
    (async () => {
      let responded = false;
      const safeSendResponse = (data) => {
        if (!responded) {
          responded = true;
          try {
            sendResponse(data);
          } catch (e) {
            console.error("Failed to send response:", e);
          }
        }
      };

      try {
        const res = await fetch("http://localhost:8000/watchlist/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req.data),
        });
        const data = await res.json();
        safeSendResponse(data);
      } catch (e) {
        safeSendResponse({ ok: false, error: e?.message || String(e) });
      }
    })();
    return true;
  }
  if (req.action === "getWatchlist") {
    (async () => {
      let responded = false;
      const safeSendResponse = (data) => {
        if (!responded) {
          responded = true;
          try {
            sendResponse(data);
          } catch (e) {
            console.error("Failed to send response:", e);
          }
        }
      };

      try {
        const res = await fetch("http://localhost:8000/watchlist");
        const data = await res.json();
        safeSendResponse(data);
      } catch (e) {
        safeSendResponse({ ok: false, error: e?.message || String(e) });
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
