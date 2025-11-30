// Guard against multiple injections/redefinitions
if (window.__ticaiOverlayInjected) {
  // already initialized
} else {
  window.__ticaiOverlayInjected = true;

  let ticaiContainer = null; // iframe only (stable sizing)
  let ticaiDialog = null; // HTMLDialogElement to avoid page transforms

  async function createPopup() {
    // Check if already exists - prevent duplicates
    const existingDialog = document.getElementById("ticai-assistant-dialog");
    const existingIframe = document.getElementById("ticai-assistant");
    
    // If already exists, don't create another
    if (existingDialog || existingIframe || ticaiContainer || ticaiDialog) {
      return; // Already open, don't create duplicate
    }
    
    // Clean up any orphaned elements (safety check)
    if (existingDialog) {
      try { existingDialog.close(); } catch {}
      existingDialog.remove();
    }
    if (existingIframe && !existingIframe.parentElement) {
      existingIframe.remove();
    }

    // Use a modal dialog (top-layer) so page transforms/zoom don't shrink it
    ticaiDialog = document.createElement("dialog");
    ticaiDialog.id = "ticai-assistant-dialog";
    ticaiDialog.style.position = "fixed";
    ticaiDialog.style.right = "20px";
    ticaiDialog.style.bottom = "20px";
    ticaiDialog.style.padding = "0";
    ticaiDialog.style.border = "none";
    ticaiDialog.style.background = "transparent";
    ticaiDialog.style.width = "520px";
    ticaiDialog.style.height = "640px";
    ticaiDialog.style.zIndex = "2147483647";
    ticaiDialog.style.overflow = "visible";

    ticaiContainer = document.createElement("iframe");
    ticaiContainer.src = chrome.runtime.getURL("popup/panel.html");
    ticaiContainer.id = "ticai-assistant";
    ticaiContainer.style.position = "relative";
    ticaiContainer.style.width = "520px";
    ticaiContainer.style.height = "640px";
    ticaiContainer.style.zIndex = "2147483647";
    ticaiContainer.style.border = "none";
    ticaiContainer.style.borderRadius = "12px";
    ticaiContainer.style.boxShadow = "0 0 20px rgba(0,0,0,0.4)";
    ticaiContainer.style.background = "transparent";
    ticaiContainer.style.transition = "opacity 0.2s ease";
    ticaiContainer.style.opacity = "0";

    const style = document.createElement("style");
    style.textContent = `#ticai-assistant-dialog{position:fixed!important;right:20px!important;bottom:20px!important;width:520px!important;height:640px!important;z-index:2147483647!important;padding:0!important;border:none!important;background:transparent!important}`;
    document.head.appendChild(style);

    ticaiDialog.appendChild(ticaiContainer);
    document.body.appendChild(ticaiDialog);
    try { ticaiDialog.showModal(); } catch {}
    setTimeout(() => (ticaiContainer.style.opacity = "1"), 50);

    // Listen for close from iframe
    const closeHandler = (event) => {
      if (event.data === "ticai-close") {
        removePopup();
        window.removeEventListener("message", closeHandler);
      }
    };
    window.addEventListener("message", closeHandler);
  }

  function removePopup() {
    if (ticaiContainer) { ticaiContainer.remove(); ticaiContainer = null; }
    if (ticaiDialog) { try { ticaiDialog.close(); } catch {} ticaiDialog.remove(); ticaiDialog = null; }
  }

  chrome.runtime.onMessage.addListener((req) => {
    if (req.action === "toggleAssistant") {
      if (ticaiContainer || ticaiDialog) removePopup();
      else createPopup();
    }
    if (req.action === "ensureAssistantOpen") {
      // Only create if it doesn't already exist
      const existingDialog = document.getElementById("ticai-assistant-dialog");
      const existingIframe = document.getElementById("ticai-assistant");
      if (!existingDialog && !existingIframe && !ticaiContainer && !ticaiDialog) {
        createPopup();
      }
    }
  });

  // Only set open state when actually opened via toggle
  // State managed by background.js when overlay is created
}
