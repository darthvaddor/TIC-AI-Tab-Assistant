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
      try { existingDialog.close(); } catch { }
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
    try { ticaiDialog.showModal(); } catch { }
    setTimeout(() => (ticaiContainer.style.opacity = "1"), 50);
    
    // Wait for iframe to load, then tell it to refresh history
    ticaiContainer.addEventListener("load", () => {
      // Give iframe a moment to initialize, then refresh history
      setTimeout(() => {
        if (ticaiContainer.contentWindow) {
          ticaiContainer.contentWindow.postMessage({ action: "refreshHistory" }, "*");
        }
      }, 200);
    });

    // Listen for close from iframe
    const messageHandler = (event) => {
      if (event.data === "ticai-close") {
        removePopup();
        window.removeEventListener("message", messageHandler);
      }

      // Handle Dragging
      if (event.data && event.data.action === "ticai-start-drag") {
        const startX = event.data.screenX;
        const startY = event.data.screenY;
        const rect = ticaiDialog.getBoundingClientRect();
        const startRight = document.documentElement.clientWidth - rect.right;
        const startBottom = document.documentElement.clientHeight - rect.bottom;

        // Create a transparent overlay to capture all mouse events (even over iframe)
        const dragOverlay = document.createElement("div");
        dragOverlay.style.position = "fixed";
        dragOverlay.style.top = "0";
        dragOverlay.style.left = "0";
        dragOverlay.style.width = "100%";
        dragOverlay.style.height = "100%";
        dragOverlay.style.zIndex = "2147483647"; // Max z-index
        dragOverlay.style.cursor = "move";
        document.body.appendChild(dragOverlay);

        const onMouseMove = (e) => {
          // Calculate new position (right/bottom based)
          const deltaX = startX - e.screenX;
          const deltaY = startY - e.screenY;

          ticaiDialog.style.right = `${startRight + deltaX}px`;
          ticaiDialog.style.bottom = `${startBottom + deltaY}px`;
        };

        const onMouseUp = () => {
          window.removeEventListener("mousemove", onMouseMove);
          window.removeEventListener("mouseup", onMouseUp);
          dragOverlay.remove(); // Remove overlay
          // Notify iframe drag ended
          ticaiContainer.contentWindow.postMessage({ action: "ticai-drag-end" }, "*");
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
      }
    };
    window.addEventListener("message", messageHandler);
  }

  function removePopup() {
    if (ticaiContainer) { ticaiContainer.remove(); ticaiContainer = null; }
    if (ticaiDialog) { try { ticaiDialog.close(); } catch { } ticaiDialog.remove(); ticaiDialog = null; }
  }

  chrome.runtime.onMessage.addListener((req) => {
    if (req.action === "toggleAssistant") {
      if (ticaiContainer || ticaiDialog) removePopup();
      else createPopup();
    }
    if (req.action === "closeAssistant") {
      // Explicitly close (used when switching tabs)
      if (ticaiContainer || ticaiDialog) {
        removePopup();
      }
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
}
