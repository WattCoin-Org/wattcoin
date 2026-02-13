/**
 * WattBot Service Worker v0.3.0 (MV3)
 * Handles: side panel toggle, message routing, tab management, screenshots
 */

chrome.action.onClicked.addListener(function(tab) {
  chrome.sidePanel.open({ tabId: tab.id });
});

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {

  // Capture page DOM
  if (message.type === "CAPTURE_PAGE") {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (!tabs[0]) { sendResponse({ error: "No active tab" }); return; }
      chrome.tabs.sendMessage(tabs[0].id, { type: "CAPTURE_PAGE", options: message.options || {} }, function(response) {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse(response);
        }
      });
    });
    return true;
  }

  // Execute action on active tab
  if (message.type === "EXECUTE_ACTION") {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (!tabs[0]) { sendResponse({ error: "No active tab" }); return; }
      chrome.tabs.sendMessage(tabs[0].id, { type: "EXECUTE_ACTION", action: message.action }, function(response) {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse(response);
        }
      });
    });
    return true;
  }

  // Navigate current tab
  if (message.type === "NAVIGATE") {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (!tabs[0]) { sendResponse({ error: "No active tab" }); return; }
      chrome.tabs.update(tabs[0].id, { url: message.url }, function() {
        sendResponse({ success: true });
      });
    });
    return true;
  }

  // Take screenshot
  if (message.type === "TAKE_SCREENSHOT") {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (!tabs[0]) { sendResponse({ error: "No active tab" }); return; }
      chrome.tabs.captureVisibleTab(tabs[0].windowId, { format: "jpeg", quality: 70 }, function(dataUrl) {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ screenshot: dataUrl });
        }
      });
    });
    return true;
  }

  // --- Tab Management ---

  // Open new tab
  if (message.type === "TAB_OPEN") {
    chrome.tabs.create({
      url: message.url || "about:blank",
      active: message.active !== false
    }, function(tab) {
      sendResponse({ success: true, tabId: tab.id, windowId: tab.windowId });
    });
    return true;
  }

  // Switch to tab by index
  if (message.type === "TAB_SWITCH") {
    if (message.tabId) {
      chrome.tabs.update(message.tabId, { active: true }, function(tab) {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ success: true, tabId: tab.id, url: tab.url });
        }
      });
    } else if (typeof message.index === "number") {
      chrome.tabs.query({ currentWindow: true }, function(tabs) {
        var idx = message.index;
        if (idx < 0 || idx >= tabs.length) {
          sendResponse({ error: "Tab index " + idx + " out of range (0-" + (tabs.length - 1) + ")" });
          return;
        }
        chrome.tabs.update(tabs[idx].id, { active: true }, function(tab) {
          sendResponse({ success: true, tabId: tab.id, url: tab.url });
        });
      });
    } else {
      sendResponse({ error: "Provide tabId or index" });
    }
    return true;
  }

  // Close tab
  if (message.type === "TAB_CLOSE") {
    var targetTabId = message.tabId;
    if (targetTabId) {
      chrome.tabs.remove(targetTabId, function() {
        sendResponse({ success: true });
      });
    } else {
      chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        if (tabs[0]) {
          chrome.tabs.remove(tabs[0].id, function() {
            sendResponse({ success: true });
          });
        }
      });
    }
    return true;
  }

  // List all tabs
  if (message.type === "TAB_LIST") {
    chrome.tabs.query({ currentWindow: true }, function(tabs) {
      var tabList = tabs.map(function(t, i) {
        return { index: i, id: t.id, title: t.title, url: t.url, active: t.active };
      });
      sendResponse({ success: true, tabs: tabList });
    });
    return true;
  }
});

console.log("[WattBot] Service worker v0.3.0 loaded");
