// background.js — Tab Sensei
console.log("Tab Sensei background service running.");
console.log("[TabSensei] Service Worker initialized at", new Date().toLocaleString());

// Verify alarm listener is registered
console.log("[TabSensei] Alarm listener registered:", typeof chrome.alarms.onAlarm.addListener);

// Test function to manually trigger notification (for debugging)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "testNotification") {
    console.log("[TabSensei] 🧪 TEST: Manually triggering notification");
    const testMessage = request.message || "Test reminder notification";
    
    // Use the same injection code as the real alarm handler
    injectReminderNotification(testMessage);
    
    sendResponse({ success: true });
    return true;
  }
  
  if (request.action === "checkAlarms") {
    chrome.alarms.getAll((alarms) => {
      console.log(`[TabSensei] 📋 All alarms (${alarms.length}):`);
      alarms.forEach((alarm) => {
        const timeUntil = Math.round((alarm.scheduledTime - Date.now()) / 1000 / 60);
        console.log(`[TabSensei]   - "${alarm.name}" scheduled for ${new Date(alarm.scheduledTime).toLocaleString()} (in ${timeUntil} minutes)`);
      });
      sendResponse({ alarms: alarms, count: alarms.length });
    });
    return true;
  }
  
  if (request.action === "closeReminderNotification") {
    // Close notification in ALL tabs
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const notification = document.getElementById('tab-sensei-reminder-notification');
              if (notification && notification.parentNode) {
                notification.remove();
              }
            }
          }).catch(() => {
            // Ignore errors
          });
        }
      });
    });
    
    // Clear storage
    chrome.storage.local.remove(['activeReminderNotification', 'reminderNotificationTime']);
    
    sendResponse({ success: true });
    return true;
  }
  
  if (request.action === "listAlarms") {
    chrome.alarms.getAll((alarms) => {
      console.log(`[TabSensei] All alarms (${alarms.length}):`, alarms);
      sendResponse({ alarms: alarms.map(a => ({
        name: a.name,
        scheduledTime: a.scheduledTime,
        scheduledTimeFormatted: new Date(a.scheduledTime).toLocaleString(),
        timeUntil: Math.round((a.scheduledTime - Date.now()) / 1000 / 60) + " minutes"
      })) });
    });
    return true;
  }
});

// Check for price alerts on startup
chrome.runtime.onStartup.addListener(() => {
  checkPriceAlerts();
});

chrome.runtime.onInstalled.addListener(() => {
  checkPriceAlerts();
  // Enable Side Panel to open on action click (if API is available)
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
      .catch((error) => console.error("Failed to set side panel behavior:", error));
  }
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
          let price = null; // Price extracted from page
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
          } else if (hostname.includes('amazon.com') || hostname.includes('amazon.co.uk') || hostname.includes('amazon.ca')) {
            // Amazon: extract product details and price
            const productTitle = document.querySelector('#productTitle')?.innerText?.trim() || 
              document.querySelector('h1.a-size-large')?.innerText?.trim() ||
              document.querySelector('h1')?.innerText?.trim() || "";
            
            // Try multiple Amazon price selectors (they change frequently)
            // First, try the offscreen price (most reliable, contains full price)
            const offscreenPrice = document.querySelector('.a-price .a-offscreen');
            if (offscreenPrice) {
              const priceText = offscreenPrice.innerText || offscreenPrice.textContent || "";
              const cleaned = priceText.replace(/[^\d.,]/g, '').replace(/,/g, '');
              price = parseFloat(cleaned);
            }
            
            // If offscreen didn't work, try combining whole + fraction parts
            if (!price || price <= 0) {
              const wholePart = document.querySelector('.a-price-whole');
              const fractionPart = document.querySelector('.a-price-fraction');
              if (wholePart && fractionPart) {
                const whole = wholePart.innerText.replace(/[^\d]/g, '');
                const fraction = fractionPart.innerText.replace(/[^\d]/g, '');
                price = parseFloat(whole + '.' + fraction);
              }
            }
            
            // Fallback to other selectors
            if (!price || price <= 0) {
              const priceSelectors = [
                '#priceblock_ourprice',    // Our price
                '#priceblock_dealprice',   // Deal price
                '#priceblock_saleprice',   // Sale price
                '[data-a-color="price"] .a-offscreen', // Price in data attribute
                '.a-price[data-a-color="price"] .a-offscreen',
                '#corePriceDisplay_desktop_feature_div .a-price .a-offscreen',
                '#corePrice_feature_div .a-price .a-offscreen',
                '.a-price-range .a-offscreen', // Price range
              ];
              
              for (const selector of priceSelectors) {
                const priceEl = document.querySelector(selector);
                if (priceEl) {
                  const priceText = priceEl.innerText || priceEl.textContent || priceEl.getAttribute('aria-label') || "";
                  const cleaned = priceText.replace(/[^\d.,]/g, '').replace(/,/g, '');
                  price = parseFloat(cleaned);
                  if (price && price > 0 && price < 1000000) {
                    break; // Found valid price
                  }
                }
              }
            }
            
            // Fallback: try to find price in text content
            if (!price || price <= 0) {
              const pricePatterns = [/\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, /(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD/g];
              const bodyText = document.body?.innerText || "";
              for (const pattern of pricePatterns) {
                const matches = [...bodyText.matchAll(pattern)];
                if (matches.length > 0) {
                  const priceStr = matches[0][1] || matches[0][0];
                  price = parseFloat(priceStr.replace(/,/g, ""));
                  if (price > 0 && price < 1000000) break;
                }
              }
            }
            
            // Extract product description/details
            const productDetails = document.querySelector('#feature-bullets')?.innerText || 
              document.querySelector('#productDescription')?.innerText ||
              document.querySelector('#productDescription_feature_div')?.innerText ||
              document.querySelector('.a-unordered-list')?.innerText || "";
            
            // Combine title, price, and details
            const parts = [];
            if (productTitle) parts.push(`Product: ${productTitle}`);
            if (price) parts.push(`Price: $${price.toFixed(2)}`);
            if (productDetails) parts.push(`Details: ${productDetails.substring(0, 5000)}`);
            
            text = parts.join('\n\n') || document.body?.innerText || "";
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
            .slice(0, 50000); // Increased to 50k to capture full page content on large apps

          // Extract price (only if not already extracted by site-specific logic like Amazon)
          if (price === null) {
            const pricePatterns = [/\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g, /(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD/g];
            for (const pattern of pricePatterns) {
              const matches = [...text.matchAll(pattern)];
              if (matches.length > 0) {
                const priceStr = matches[0][1] || matches[0][0];
                price = parseFloat(priceStr.replace(/,/g, ""));
                if (price > 0 && price < 1000000) break;
              }
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
        // Save to both keys to keep them in sync
        await chrome.storage.local.set({ 
          chatHistory: newHistory,
          ticaiHistory: newHistory 
        });
        console.log("[TabSensei] Saved chat history to storage before potential tab switch (both keys)");
      } catch (err) {
        console.warn("[TabSensei] Failed to save chat history:", err);
      }
    }

    // === Handle each mode ===
    if (data.mode === "single") {
      console.log("Mode: SINGLE → focusing on one tab");
      if (data.chosen_tab_id) {
        try {
          // Get current active tab and close overlay there if open
          const currentTabs = await chrome.tabs.query({ active: true, currentWindow: true });
          if (currentTabs.length > 0 && currentTabs[0].id !== data.chosen_tab_id) {
            const currentTabId = currentTabs[0].id;
            // Close overlay on current tab (explicitly close, don't toggle)
            chrome.tabs.sendMessage(currentTabId, { action: "closeAssistant" }).catch(() => {
              // Ignore errors - tab might not have overlay
            });
          }
          
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            if (!tab.active) {
              await chrome.tabs.update(data.chosen_tab_id, { active: true });
            }
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            // Wait a bit for overlay to inject, then open it and refresh history
            setTimeout(() => {
              chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
                console.warn("Failed to send message to tab:", err);
              });
              // Also send refreshHistory after a longer delay to ensure overlay is fully loaded
              setTimeout(() => {
                chrome.tabs.sendMessage(data.chosen_tab_id, { action: "refreshHistory" }).catch(err => {
                  console.warn("Failed to send refreshHistory message:", err);
                });
              }, 300);
            }, 150);
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
          // Get current active tab and close overlay there if open
          const currentTabs = await chrome.tabs.query({ active: true, currentWindow: true });
          if (currentTabs.length > 0 && currentTabs[0].id !== data.chosen_tab_id) {
            const currentTabId = currentTabs[0].id;
            // Close overlay on current tab (explicitly close, don't toggle)
            chrome.tabs.sendMessage(currentTabId, { action: "closeAssistant" }).catch(() => {
              // Ignore errors - tab might not have overlay
            });
          }
          
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            if (!tab.active) {
              await chrome.tabs.update(data.chosen_tab_id, { active: true });
            }
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            // Wait a bit for overlay to inject, then open it and refresh history
            setTimeout(() => {
              chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
                console.warn("Failed to send message to tab:", err);
              });
              // Also send refreshHistory after a longer delay to ensure overlay is fully loaded
              setTimeout(() => {
                chrome.tabs.sendMessage(data.chosen_tab_id, { action: "refreshHistory" }).catch(err => {
                  console.warn("Failed to send refreshHistory message:", err);
                });
              }, 300);
            }, 150);
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
          // Get current active tab and close overlay there if open
          const currentTabs = await chrome.tabs.query({ active: true, currentWindow: true });
          if (currentTabs.length > 0 && currentTabs[0].id !== data.chosen_tab_id) {
            const currentTabId = currentTabs[0].id;
            // Close overlay on current tab (explicitly close, don't toggle)
            chrome.tabs.sendMessage(currentTabId, { action: "closeAssistant" }).catch(() => {
              // Ignore errors - tab might not have overlay
            });
          }
          
          // Check if tab still exists
          const tab = await chrome.tabs.get(data.chosen_tab_id).catch(() => null);
          if (tab) {
            await chrome.tabs.update(data.chosen_tab_id, { active: true });
            await ensureOverlay(data.chosen_tab_id);
            await chrome.storage.local.set({ ticaiOpen: true });
            // Wait a bit for overlay to inject, then open it and refresh history
            setTimeout(() => {
              chrome.tabs.sendMessage(data.chosen_tab_id, { action: "ensureAssistantOpen" }).catch(err => {
                console.warn("Failed to send message to tab:", err);
              });
              // Also send refreshHistory after a longer delay to ensure overlay is fully loaded
              setTimeout(() => {
                chrome.tabs.sendMessage(data.chosen_tab_id, { action: "refreshHistory" }).catch(err => {
                  console.warn("Failed to send refreshHistory message:", err);
                });
              }, 300);
            }, 150);
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

// === Ensure overlay script is injected ===
async function ensureOverlay(tabId) {
  try {
    // Check if script is already injected by trying to send a message
    // If it fails, inject the script
    try {
      await chrome.tabs.sendMessage(tabId, { action: "ping" });
    } catch (e) {
      // Script not injected yet, inject it
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["content/overlay.js"]
      });
    }
  } catch (err) {
    console.warn("Failed to ensure overlay:", err);
    throw err;
  }
}

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
  console.log("Tab Sensei installed successfully.");
});

// === Notification Click Handlers ===
chrome.notifications.onClicked.addListener((notificationId) => {
  console.log(`[TabSensei] Notification clicked: ${notificationId}`);
  // Open extension popup/panel when notification is clicked
  chrome.action.openPopup().catch(() => {
    // If popup can't be opened, try opening in a new tab
    chrome.tabs.create({ url: chrome.runtime.getURL("popup/panel.html") });
  });
  // Don't auto-clear - let user close manually to keep it visible
  // chrome.notifications.clear(notificationId);
});

chrome.notifications.onButtonClicked.addListener((notificationId, buttonIndex) => {
  console.log(`[TabSensei] Notification button clicked: ${notificationId}, button: ${buttonIndex}`);
  if (buttonIndex === 0) { // "Open Extension" button
    chrome.action.openPopup().catch(() => {
      // If popup can't be opened, try opening in a new tab
      chrome.tabs.create({ url: chrome.runtime.getURL("popup/panel.html") });
    });
  }
  // Don't auto-clear - let user close manually to keep it visible
  // chrome.notifications.clear(notificationId);
});

// === Helper function to inject reminder notification ===
function injectReminderNotification(reminderMessage) {
  console.log(`[TabSensei] 🔔 Injecting reminder notification: "${reminderMessage}"`);
  
  // Store notification state for cross-tab sync
  chrome.storage.local.set({ 
    activeReminderNotification: reminderMessage,
    reminderNotificationTime: Date.now()
  });
  
  // Show webpage popup notification on ALL tabs (not just active one)
  chrome.tabs.query({}, (tabs) => {
    console.log(`[TabSensei] Found ${tabs.length} total tabs - will inject into ALL http/https tabs`);
    let injectedCount = 0;
    let failedCount = 0;
    tabs.forEach((tab) => {
      // Inject on ALL http/https pages (not just active tab) - INCLUDING tabs with assistant
      if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: (message) => {
            // Remove any existing notification first
            const existing = document.getElementById('tab-sensei-reminder-notification');
            if (existing) {
              existing.remove();
            }
            
            // Create notification with MAXIMUM z-index to appear above assistant overlay.
            // Default position: top-right. If the Tab Sensei assistant dialog is present in this
            // tab (bottom-right), move the notification to the top-left so the close button
            // is not covered by the assistant iframe.
            const notification = document.createElement('div');
            notification.id = 'tab-sensei-reminder-notification';
            notification.style.cssText = `
              position: fixed !important;
              top: 20px !important;
              right: 20px !important;
              width: 320px !important;
              min-height: 80px !important;
              background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
              color: white !important;
              padding: 16px 20px !important;
              border-radius: 12px !important;
              box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
              z-index: 2147483647 !important;
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
              font-size: 14px !important;
              line-height: 1.5 !important;
              pointer-events: auto !important;
              isolation: isolate !important;
            `;

            // If the Tab Sensei assistant dialog exists (bottom-right), avoid overlapping it.
            // Move the reminder notification to the top-left corner for this tab only.
            try {
              const assistantDialog = document.getElementById('ticai-assistant-dialog');
              if (assistantDialog) {
                notification.style.right = 'auto';
                notification.style.left = '20px';
              }
            } catch (e) {
              // If anything goes wrong here, just keep the default top-right position.
            }
            
            // Add animation styles and prevent auto-close
            if (!document.getElementById('tab-sensei-reminder-styles')) {
              const style = document.createElement('style');
              style.id = 'tab-sensei-reminder-styles';
              style.textContent = `
                @keyframes slideIn {
                  from { transform: translateX(400px); opacity: 0; }
                  to { transform: translateX(0); opacity: 1; }
                }
                #tab-sensei-reminder-notification {
                  animation: slideIn 0.3s ease-out !important;
                }
                #tab-sensei-reminder-notification * {
                  pointer-events: auto !important;
                }
              `;
              document.head.appendChild(style);
            }
            
            // Play notification sound (pleasant two-tone chime)
            try {
              const audioContext = new (window.AudioContext || window.webkitAudioContext)();
              
              // First tone
              const osc1 = audioContext.createOscillator();
              const gain1 = audioContext.createGain();
              osc1.type = 'sine';
              osc1.frequency.value = 800;
              gain1.gain.setValueAtTime(0, audioContext.currentTime);
              gain1.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05);
              gain1.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.2);
              osc1.connect(gain1);
              gain1.connect(audioContext.destination);
              osc1.start(audioContext.currentTime);
              osc1.stop(audioContext.currentTime + 0.2);
              
              // Second tone (slightly delayed)
              setTimeout(() => {
                try {
                  const osc2 = audioContext.createOscillator();
                  const gain2 = audioContext.createGain();
                  osc2.type = 'sine';
                  osc2.frequency.value = 1000;
                  gain2.gain.setValueAtTime(0, audioContext.currentTime);
                  gain2.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05);
                  gain2.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.2);
                  osc2.connect(gain2);
                  gain2.connect(audioContext.destination);
                  osc2.start(audioContext.currentTime);
                  osc2.stop(audioContext.currentTime + 0.2);
                } catch (e) {
                  // Ignore errors in second tone
                }
              }, 100);
            } catch (e) {
              // If Web Audio API fails, try a simple beep
              try {
                // Create a simple beep using oscillator fallback
                const beep = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OSdTgwOUKjj8LZjHAY4kdfyzHksBSR3x/DdkEAKFF606euoVRQKRp/g8r5sIQUrgc7y2Yk2CBtpvfDknU4MDlCo4/C2YxwGOJHX8sx5LAUkd8fw3ZBAC');
                beep.volume = 0.3;
                beep.play().catch(() => {
                  // If audio fails, that's okay - notification will still show
                });
              } catch (audioError) {
                // Sound is optional - notification will still work
              }
            }
            
            // Create close button with proper event handling
            const closeBtn = document.createElement('button');
            closeBtn.innerHTML = '✕';
            closeBtn.setAttribute('type', 'button'); // Prevent form submission
            closeBtn.style.cssText = `
              position: absolute !important;
              top: 8px !important;
              right: 8px !important;
              background: rgba(255, 255, 255, 0.2) !important;
              border: none !important;
              color: white !important;
              width: 28px !important;
              height: 28px !important;
              border-radius: 50% !important;
              cursor: pointer !important;
              font-size: 18px !important;
              line-height: 1 !important;
              display: flex !important;
              align-items: center !important;
              justify-content: center !important;
              padding: 0 !important;
              transition: background 0.2s !important;
              z-index: 2147483648 !important;
              pointer-events: auto !important;
              user-select: none !important;
            `;
            
            // Hover effects
            closeBtn.addEventListener('mouseenter', () => {
              closeBtn.style.background = 'rgba(255, 255, 255, 0.3)';
            });
            closeBtn.addEventListener('mouseleave', () => {
              closeBtn.style.background = 'rgba(255, 255, 255, 0.2)';
            });
            
            // Close handler - closes in THIS tab AND syncs to all other tabs
            const closeHandler = (e) => {
              e.preventDefault();
              e.stopPropagation();
              e.stopImmediatePropagation();
              
              // Remove notification from this tab
              if (notification && notification.parentNode) {
                notification.remove();
              }
              
              // Notify background script to close in all tabs
              try {
                chrome.runtime.sendMessage({ 
                  action: 'closeReminderNotification' 
                }, () => {
                  // Ignore errors - message sent
                });
              } catch (err) {
                // Ignore errors
              }
              
              // Also clear storage to signal other tabs
              try {
                chrome.storage.local.remove(['activeReminderNotification', 'reminderNotificationTime']);
              } catch (err) {
                // Ignore errors
              }
              
              return false;
            };
            
            // Multiple event handlers to ensure close button works reliably
            closeBtn.addEventListener('click', closeHandler, true); // Capture phase
            closeBtn.addEventListener('mousedown', closeHandler, true); // Also on mousedown
            closeBtn.addEventListener('touchend', closeHandler, true); // Mobile support
            
            // Listen for close messages from other tabs
            chrome.storage.onChanged.addListener((changes, areaName) => {
              if (areaName === 'local' && changes.activeReminderNotification) {
                if (!changes.activeReminderNotification.newValue) {
                  // Notification was cleared - remove from this tab
                  if (notification && notification.parentNode) {
                    notification.remove();
                  }
                }
              }
            });
            
            // Listen for runtime messages to close
            chrome.runtime.onMessage.addListener((request) => {
              if (request.action === 'closeReminderNotification') {
                if (notification && notification.parentNode) {
                  notification.remove();
                }
              }
            });
            
            // Create content
            const title = document.createElement('div');
            title.style.cssText = 'font-weight: 600; font-size: 16px; margin-bottom: 8px;';
            title.textContent = '⏰ Tab Sensei Reminder';
            
            const messageDiv = document.createElement('div');
            messageDiv.style.cssText = 'color: rgba(255, 255, 255, 0.95); word-wrap: break-word;';
            messageDiv.textContent = message;
            
            notification.appendChild(title);
            notification.appendChild(messageDiv);
            notification.appendChild(closeBtn);
            
            // Add to page - ensure it's added to body AFTER all other elements (so it appears on top)
            const addToPage = () => {
              if (document.body) {
                // Append to body - this ensures it's after the assistant overlay
                document.body.appendChild(notification);
                
                // Force it to the top by moving it to the end of body
                // This ensures it appears above the assistant overlay
                setTimeout(() => {
                  if (notification.parentNode) {
                    document.body.appendChild(notification);
                  }
                }, 100);
              } else {
                // Wait for body to be ready
                setTimeout(addToPage, 50);
              }
            };
            addToPage();
          },
          args: [reminderMessage]
        }).then(() => {
          injectedCount++;
          console.log(`[TabSensei] ✅ Notification injected into tab ${tab.id}: ${tab.url?.substring(0, 50)}...`);
        }).catch((err) => {
          failedCount++;
          console.warn(`[TabSensei] ⚠️ Failed to inject in tab ${tab.id}: ${err.message}`);
        });
      }
    });
    
    setTimeout(() => {
      console.log(`[TabSensei] 📊 Reminder notification injection complete:`);
      console.log(`[TabSensei]   ✅ ${injectedCount} tabs succeeded`);
      console.log(`[TabSensei]   ❌ ${failedCount} tabs failed`);
      console.log(`[TabSensei]   📋 Total tabs: ${tabs.length}`);
    }, 1500);
  });
}

// === Alarm Handler for Reminders ===
// Register alarm listener with explicit logging
console.log("[TabSensei] Registering alarm listener...");
chrome.alarms.onAlarm.addListener((alarm) => {
  const now = new Date();
  console.log(`[TabSensei] ⏰⏰⏰ ALARM FIRED ⏰⏰⏰`);
  console.log(`[TabSensei] Alarm name: "${alarm.name}"`);
  console.log(`[TabSensei] Fired at: ${now.toLocaleString()}`);
  console.log(`[TabSensei] Was scheduled for: ${new Date(alarm.scheduledTime).toLocaleString()}`);
  console.log(`[TabSensei] Time difference: ${Math.round((now.getTime() - alarm.scheduledTime) / 1000)} seconds`);
  
  // Log as a warning (not an error) so it shows up in logs without being treated as a failure
  console.warn(`[TabSensei] ⚠️⚠️⚠️ REMINDER ALARM FIRED: "${alarm.name}" ⚠️⚠️⚠️`);
  
  // Extract the actual reminder message (remove "(Day X)" suffix for recurring reminders)
  let reminderMessage = alarm.name;
  const dayMatch = reminderMessage.match(/^(.+?)\s*\(Day\s+\d+\)$/);
  if (dayMatch) {
    reminderMessage = dayMatch[1]; // Extract the base message
  }
  
  // Filter out test alarm messages - only show real user reminders
  if (reminderMessage.toLowerCase().includes('test alarm') || 
      reminderMessage.toLowerCase().includes('test reminder') ||
      reminderMessage.includes('30 seconds')) {
    console.log(`[TabSensei] ⚠️ Skipping test alarm: "${reminderMessage}"`);
    return; // Don't show test alarms
  }
  
  console.log(`[TabSensei] Reminder message: "${reminderMessage}"`);

  // Check if notification permission is granted
  chrome.notifications.getPermissionLevel((level) => {
    console.log(`[TabSensei] Notification permission level: ${level}`);
    if (level !== "granted") {
      console.error(`[TabSensei] ⚠️ Notification permission is "${level}", not "granted". Notifications may not work.`);
    }
  });

  // Inject notification using helper function
  injectReminderNotification(reminderMessage);
  
  // Also show Chrome notification as backup
  try {
    const notificationOptions = {
      type: "basic",
      iconUrl: chrome.runtime.getURL("popup/icon128.png"),
      title: "⏰ Tab Sensei Reminder",
      message: reminderMessage,
      priority: 2,
      requireInteraction: true,
      buttons: [
        { title: "Open Extension" }
      ],
      silent: false
    };
    
    chrome.notifications.create(notificationOptions, (notificationId) => {
      if (chrome.runtime.lastError) {
        console.error(`[TabSensei] ❌ FAILED to create Chrome notification:`, chrome.runtime.lastError.message);
      } else {
        console.log(`[TabSensei] ✅ Chrome notification created with ID: ${notificationId}`);
      }
    });
  } catch (err) {
    console.error(`[TabSensei] ❌ Exception creating Chrome notification:`, err);
  }
});
