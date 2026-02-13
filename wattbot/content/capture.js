/**
 * WattBot DOM Capture
 * Content script: extracts interactive elements + page text for LLM consumption.
 * Injects data-wattbot-id attributes for action targeting.
 */

(function() {
  "use strict";
  
  let idCounter = 0;
  
  /**
   * Tag all interactive elements with unique wattbot IDs.
   * Returns map of id -> element for action executor.
   */
  function tagInteractiveElements() {
    // Clear old tags
    document.querySelectorAll("[data-wattbot-id]").forEach(el => {
      el.removeAttribute("data-wattbot-id");
    });
    idCounter = 0;
    
    const selectors = [
      "a[href]",
      "button",
      "input",
      "textarea",
      "select",
      "[role='button']",
      "[role='link']",
      "[role='tab']",
      "[role='menuitem']",
      "[role='checkbox']",
      "[role='radio']",
      "[role='textbox']",
      "[role='combobox']",
      "[onclick]",
      "[contenteditable='true']",
      "[contenteditable='plaintext-only']"
    ];
    
    const elements = document.querySelectorAll(selectors.join(", "));
    const tagged = {};
    
    elements.forEach(el => {
      // Skip hidden/invisible elements
      if (!isVisible(el)) return;
      
      const id = `wb-${String(idCounter++).padStart(3, "0")}`;
      el.setAttribute("data-wattbot-id", id);
      tagged[id] = el;
    });
    
    return tagged;
  }
  
  /**
   * Check if element is visible in the page.
   */
  function isVisible(el) {
    if (!el.offsetParent && el.tagName !== "BODY" && el.tagName !== "HTML") return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    return true;
  }
  
  /**
   * Get human-readable label for an interactive element.
   */
  function getElementLabel(el) {
    // Try aria-label first
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim();
    
    // Try inner text (short)
    const text = el.innerText || el.textContent || "";
    const trimmed = text.trim().replace(/\s+/g, " ");
    if (trimmed && trimmed.length <= 80) return trimmed;
    if (trimmed) return trimmed.substring(0, 77) + "...";
    
    // Try placeholder
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder.trim();
    
    // Try title
    const title = el.getAttribute("title");
    if (title) return title.trim();
    
    // Try alt (for images in links/buttons)
    const img = el.querySelector("img");
    if (img && img.alt) return img.alt.trim();
    
    // Try name/id as last resort
    const name = el.getAttribute("name") || el.getAttribute("id");
    if (name) return `[${name}]`;
    
    return "[unlabeled]";
  }
  
  /**
   * Get element type description.
   */
  function getElementType(el) {
    const tag = el.tagName.toLowerCase();
    // Contenteditable detection first (chat boxes, rich editors)
    if (el.getAttribute("contenteditable") === "true" || el.isContentEditable) {
      const role = el.getAttribute("role");
      if (role === "textbox") return "rich-textbox";
      return "editable";
    }
    if (el.getAttribute("role") === "textbox") return "rich-textbox";
    if (tag === "a") return "link";
    if (tag === "button" || el.getAttribute("role") === "button") return "button";
    if (tag === "select") return "dropdown";
    if (tag === "textarea") return "textarea";
    if (tag === "input") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "submit") return "submit-button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "password") return "password-input";
      if (type === "search") return "search-input";
      if (type === "email") return "email-input";
      if (type === "file") return "file-input";
      return "input";
    }
    if (el.getAttribute("role")) return el.getAttribute("role");
    return tag;
  }
  
  /**
   * Build structured description of all interactive elements.
   */
  function captureInteractiveElements(tagged) {
    const lines = [];
    
    for (const [id, el] of Object.entries(tagged)) {
      const type = getElementType(el);
      const label = getElementLabel(el);
      const value = el.value !== undefined && el.value !== "" ? ` value="${el.value}"` : "";
      const checked = el.checked !== undefined ? ` checked=${el.checked}` : "";
      const disabled = el.disabled ? " [disabled]" : "";
      const href = el.tagName === "A" ? ` href="${el.href}"` : "";
      
      lines.push(`[${id}] ${type} "${label}"${value}${checked}${disabled}${href}`);
    }
    
    return lines.join("\n");
  }
  
  /**
   * Extract visible page text content (headings + paragraphs).
   * Truncated to token budget.
   */
  function capturePageText(maxLength) {
    maxLength = maxLength || 3000;
    const parts = [];
    
    // Get headings for structure
    const headings = document.querySelectorAll("h1, h2, h3");
    headings.forEach(h => {
      const text = h.innerText.trim();
      if (text) {
        const level = h.tagName.toLowerCase();
        parts.push(`[${level}] ${text}`);
      }
    });
    
    // Get main content paragraphs
    const paragraphs = document.querySelectorAll("p, li, td, th, label, span.text, div.text");
    paragraphs.forEach(p => {
      const text = p.innerText.trim().replace(/\s+/g, " ");
      if (text && text.length > 10) {
        parts.push(text);
      }
    });
    
    let result = parts.join("\n");
    if (result.length > maxLength) {
      result = result.substring(0, maxLength) + "\n[...truncated]";
    }
    return result;
  }
  
  /**
   * Main capture function — returns full page state for LLM.
   */
  function capturePage(options) {
    options = options || {};
    const maxTextLength = options.maxTextLength || 3000;
    
    const tagged = tagInteractiveElements();
    const interactiveElements = captureInteractiveElements(tagged);
    const pageText = capturePageText(maxTextLength);
    
    return {
      url: window.location.href,
      title: document.title,
      interactiveElements: interactiveElements,
      elementCount: Object.keys(tagged).length,
      pageText: pageText,
      scrollPosition: {
        x: window.scrollX,
        y: window.scrollY,
        maxY: document.documentElement.scrollHeight - window.innerHeight
      },
      timestamp: Date.now()
    };
  }
  
  // Listen for capture requests from service worker
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "CAPTURE_PAGE") {
      try {
        const pageState = capturePage(message.options);
        sendResponse(pageState);
      } catch (e) {
        sendResponse({ error: e.message });
      }
    }
  });
  
  // Expose for executor
  window.__wattbot_capture = capturePage;
  
  console.log("[WattBot] DOM capture loaded");
})();
