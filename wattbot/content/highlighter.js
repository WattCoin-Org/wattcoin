/**
 * WattBot Highlighter
 * Content script: visual feedback showing which element the agent is targeting.
 */

(function() {
  "use strict";
  
  let overlay = null;
  
  function createOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "wattbot-highlight";
    overlay.style.cssText = `
      position: fixed;
      pointer-events: none;
      border: 3px solid #00d4ff;
      border-radius: 4px;
      background: rgba(0, 212, 255, 0.1);
      box-shadow: 0 0 12px rgba(0, 212, 255, 0.4);
      z-index: 2147483647;
      transition: all 0.2s ease;
      display: none;
    `;
    document.body.appendChild(overlay);
    return overlay;
  }
  
  function highlightElement(el) {
    const ov = createOverlay();
    const rect = el.getBoundingClientRect();
    
    ov.style.top = (rect.top - 3) + "px";
    ov.style.left = (rect.left - 3) + "px";
    ov.style.width = (rect.width + 6) + "px";
    ov.style.height = (rect.height + 6) + "px";
    ov.style.display = "block";
    
    // Fade out after 1.5s
    setTimeout(() => {
      ov.style.display = "none";
    }, 1500);
  }
  
  // Listen for highlight events from executor
  window.addEventListener("wattbot-highlight", (e) => {
    if (e.detail && e.detail.element) {
      highlightElement(e.detail.element);
    }
  });
  
  console.log("[WattBot] Highlighter loaded");
})();
