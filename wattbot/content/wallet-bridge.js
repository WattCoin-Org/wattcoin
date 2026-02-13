/**
 * WattBot Wallet Bridge — Content Script
 * Bridges extension context (sidepanel/service-worker) ↔ page context (wallet-inject.js)
 *
 * Flow:
 *   Sidepanel → chrome.tabs.sendMessage → THIS SCRIPT → window.postMessage → wallet-inject.js
 *   wallet-inject.js → window.postMessage → THIS SCRIPT → chrome.runtime.sendMessage → Sidepanel
 */

(function() {
  "use strict";

  var WATTBOT_MSG = "WATTBOT_WALLET";
  var WATTBOT_RESP = "WATTBOT_WALLET_RESPONSE";
  var injected = false;
  var pendingCallbacks = {}; // requestId → sendResponse callback

  /**
   * Inject the wallet-inject.js script into the page context.
   * This gives it access to window.phantom.solana.
   */
  function ensureInjected() {
    if (injected) return;
    try {
      var script = document.createElement("script");
      script.src = chrome.runtime.getURL("content/wallet-inject.js");
      script.onload = function() {
        script.remove(); // Clean up DOM after execution
      };
      (document.head || document.documentElement).appendChild(script);
      injected = true;
    } catch (e) {
      console.error("[WattBot Wallet Bridge] Failed to inject:", e);
    }
  }

  /**
   * Listen for responses from wallet-inject.js (page context)
   */
  window.addEventListener("message", function(event) {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== WATTBOT_RESP) return;

    var requestId = event.data.requestId;
    var data = event.data.data;

    // If there's a pending callback for this request, resolve it
    if (requestId && pendingCallbacks[requestId]) {
      pendingCallbacks[requestId](data);
      delete pendingCallbacks[requestId];
    }
  });

  /**
   * Listen for commands from the extension (sidepanel/service-worker)
   */
  chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
    if (!message || message.target !== "wattbot-wallet") return false;

    // Ensure inject script is loaded
    ensureInjected();

    var requestId = "req_" + Date.now() + "_" + Math.random().toString(36).substr(2, 6);

    // Store callback
    pendingCallbacks[requestId] = sendResponse;

    // Forward to page context with small delay to ensure inject is ready
    setTimeout(function() {
      window.postMessage({
        type: WATTBOT_MSG,
        command: message.command,
        requestId: requestId,
        payload: message.payload || {}
      }, "*");
    }, injected ? 10 : 200); // Longer delay on first inject

    // Timeout after 30s (wallet prompts can take time)
    setTimeout(function() {
      if (pendingCallbacks[requestId]) {
        pendingCallbacks[requestId]({ error: "Wallet request timed out (30s)." });
        delete pendingCallbacks[requestId];
      }
    }, 30000);

    // Return true to keep sendResponse channel open (async)
    return true;
  });

  // Pre-inject on load so Phantom detection is fast
  if (document.readyState === "complete" || document.readyState === "interactive") {
    ensureInjected();
  } else {
    document.addEventListener("DOMContentLoaded", function() {
      ensureInjected();
    });
  }
})();
