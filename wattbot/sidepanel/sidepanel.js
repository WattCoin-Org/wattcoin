/**
 * WattBot Side Panel Controller v0.2.0
 * Handles: UI events, agent lifecycle, chat history, debug log, quick actions,
 *          WattCoin quick actions, wallet status.
 */

(function() {
  "use strict";

  // DOM refs
  var chatLog = document.getElementById("chatLog");
  var taskInput = document.getElementById("taskInput");
  var btnRun = document.getElementById("btnRun");
  var btnStop = document.getElementById("btnStop");
  var btnPause = document.getElementById("btnPause");
  var btnSettings = document.getElementById("btnSettings");
  var btnWallet = document.getElementById("btnWallet");
  var walletIndicator = document.getElementById("walletIndicator");
  var chkScreenshots = document.getElementById("chkScreenshots");
  var statusBar = document.getElementById("statusBar");
  var confirmOverlay = document.getElementById("confirmOverlay");
  var confirmReason = document.getElementById("confirmReason");
  var confirmAction = document.getElementById("confirmAction");
  var btnAllow = document.getElementById("btnAllow");
  var btnDeny = document.getElementById("btnDeny");
  var debugPanel = document.getElementById("debugPanel");
  var historyList = document.getElementById("historyList");
  var btnClearHistory = document.getElementById("btnClearHistory");
  var promptInput = document.getElementById("promptInput");
  var promptBody = document.getElementById("promptBody");
  var btnPromptToggle = document.getElementById("btnPromptToggle");
  var btnPromptClear = document.getElementById("btnPromptClear");
  var promptIndicator = document.getElementById("promptIndicator");

  var agent = null;
  var confirmCallback = null;
  var debugInterval = null;
  var persistedDebugLog = [];

  // --- Wallet Status ---
  function updateWalletIndicator() {
    chrome.storage.sync.get(["walletAddress"], function(data) {
      if (data && data.walletAddress) {
        walletIndicator.className = "wallet-indicator connected";
        btnWallet.title = "Wallet: " + data.walletAddress.substring(0, 6) + "...";
      } else {
        walletIndicator.className = "wallet-indicator";
        btnWallet.title = "No wallet connected — click to set up";
      }
    });
  }
  updateWalletIndicator();

  // Listen for storage changes (e.g., settings page saves wallet)
  chrome.storage.onChanged.addListener(function(changes) {
    if (changes.walletAddress) updateWalletIndicator();
  });

  // --- WattCoin Quick Actions ---
  var qaBalance = document.getElementById("qaBalance");
  if (qaBalance) {
    qaBalance.addEventListener("click", function() {
      WattBotWallet.getSavedAddress().then(function(address) {
        if (!address) {
          addMessage("error", "⚠️ No wallet configured. Go to Settings → Wallet to add your address.");
          return;
        }

        addMessage("thinking", "Fetching WATT balance for " + address.substring(0, 6) + "...");

        Promise.all([
          WattBotWallet.getWattBalance(address),
          WattBotWallet.getSolBalance(address)
        ]).then(function(results) {
          var watt = results[0];
          var sol = results[1];
          // Remove thinking
          chatLog.querySelectorAll(".msg.thinking").forEach(function(el) { el.remove(); });
          addMessage("done",
            '<span class="done-label">⚡ Wallet Balance</span>' +
            '<strong>' + WattBotWallet.formatBalance(watt.balance) + ' WATT</strong><br>' +
            sol.balance.toFixed(4) + ' SOL<br>' +
            '<span style="color:#484f58;font-size:10px">' + address.substring(0, 8) + '...' + address.substring(address.length - 6) + ' · ' +
            '<a href="https://solscan.io/account/' + address + '" style="color:#00e5ff" target="_blank">Solscan ↗</a></span>'
          );
        }).catch(function(err) {
          chatLog.querySelectorAll(".msg.thinking").forEach(function(el) { el.remove(); });
          addMessage("error", "⚠️ Failed to fetch balance: " + err.message);
        });
      });
    });
  }

  // --- Tab Switching ---
  document.querySelectorAll(".tab-bar button").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var tab = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab-bar button").forEach(function(b) { b.classList.remove("active"); });
      document.querySelectorAll(".view-panel").forEach(function(v) { v.classList.remove("active"); });
      btn.classList.add("active");
      document.getElementById("view-" + tab).classList.add("active");
      if (tab === "history") loadHistory();
      if (tab === "debug") refreshDebug();
    });
  });

  // --- Quick Actions (generic + WATT) ---
  document.querySelectorAll(".quick-btn[data-task]").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var task = btn.getAttribute("data-task");
      if (!task) return; // qaBalance handled separately
      taskInput.value = task;
      document.querySelector('.tab-bar button[data-tab="main"]').click();
      taskInput.focus();
    });
  });

  // --- Settings / Wallet ---
  btnSettings.addEventListener("click", function() {
    chrome.runtime.openOptionsPage();
  });
  btnWallet.addEventListener("click", function() {
    chrome.runtime.openOptionsPage();
  });

  // --- Prompt Section ---
  btnPromptToggle.addEventListener("click", function() {
    var isVisible = promptBody.style.display !== "none";
    promptBody.style.display = isVisible ? "none" : "block";
    btnPromptToggle.classList.toggle("active", !isVisible);
  });

  btnPromptClear.addEventListener("click", function() {
    promptInput.value = "";
    updatePromptIndicator();
    chrome.storage.local.set({ wattbot_prompt: "" });
  });

  promptInput.addEventListener("input", function() {
    updatePromptIndicator();
    chrome.storage.local.set({ wattbot_prompt: promptInput.value });
  });

  function updatePromptIndicator() {
    promptIndicator.textContent = promptInput.value.trim() ? "●" : "";
  }

  // Load saved prompt
  chrome.storage.local.get("wattbot_prompt", function(data) {
    if (data && data.wattbot_prompt) {
      promptInput.value = data.wattbot_prompt;
      updatePromptIndicator();
    }
  });

  // --- Run / Stop / Pause ---
  btnRun.addEventListener("click", function() {
    startTask();
  });

  taskInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      startTask();
    }
  });

  btnStop.addEventListener("click", function() {
    if (agent) {
      persistedDebugLog = agent.getDebugLog().slice();
      agent.stop();
    }
    setRunning(false);
    if (debugInterval) clearInterval(debugInterval);
    refreshDebug();
  });

  btnPause.addEventListener("click", function() {
    if (!agent) return;
    if (agent.paused) {
      agent.resume();
      btnPause.textContent = "⏸";
      btnPause.title = "Pause";
    } else {
      agent.pause();
      btnPause.textContent = "▶";
      btnPause.title = "Resume";
    }
  });

  // --- Confirm ---
  btnAllow.addEventListener("click", function() {
    confirmOverlay.classList.remove("visible");
    if (confirmCallback) confirmCallback(true);
  });
  btnDeny.addEventListener("click", function() {
    confirmOverlay.classList.remove("visible");
    if (confirmCallback) confirmCallback(false);
  });

  // --- History ---
  btnClearHistory.addEventListener("click", function() {
    chrome.storage.local.set({ wattbot_history: [] }, function() {
      loadHistory();
    });
  });

  function loadHistory() {
    chrome.storage.local.get("wattbot_history", function(data) {
      var history = data.wattbot_history || [];
      if (history.length === 0) {
        historyList.innerHTML = '<div class="history-empty">No task history yet.</div>';
        return;
      }
      historyList.innerHTML = "";
      history.slice().reverse().forEach(function(item) {
        var div = document.createElement("div");
        div.className = "history-item";
        var date = new Date(item.time);
        var timeStr = date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        div.innerHTML =
          '<div class="task-text">' + escapeHtml(item.task) + '</div>' +
          '<div class="meta">' +
            '<span>' + timeStr + '</span>' +
            '<span>' + item.steps + ' steps</span>' +
            '<span>~$' + (item.cost || 0).toFixed(4) + '</span>' +
            '<span>' + (item.success ? "✅" : "❌") + '</span>' +
          '</div>';
        div.addEventListener("click", function() {
          taskInput.value = item.task;
          document.querySelector('.tab-bar button[data-tab="main"]').click();
        });
        historyList.appendChild(div);
      });
    });
  }

  function saveToHistory(task, steps, tokens, cost, success) {
    chrome.storage.local.get("wattbot_history", function(data) {
      var history = data.wattbot_history || [];
      history.push({
        task: task,
        steps: steps,
        tokens: tokens,
        cost: cost,
        success: success,
        time: Date.now()
      });
      if (history.length > 50) history = history.slice(-50);
      chrome.storage.local.set({ wattbot_history: history });
    });
  }

  // --- Debug Log ---
  function refreshDebug() {
    var log = (agent ? agent.getDebugLog() : persistedDebugLog);
    if (!log || log.length === 0) {
      debugPanel.innerHTML = '<div class="debug-empty">No debug entries yet.</div>';
      return;
    }
    debugPanel.innerHTML = "";
    log.forEach(function(entry) {
      var div = document.createElement("div");
      var cls = "debug-entry";
      if (entry.type === "error") cls += " error";
      if (entry.type === "llm_response") cls += " llm";
      if (entry.type === "parsed_action" || entry.type === "action_result") cls += " action";
      div.className = cls;

      var time = new Date(entry.time);
      var timeStr = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

      var dataStr;
      try {
        dataStr = typeof entry.data === "string" ? entry.data : JSON.stringify(entry.data, null, 1);
      } catch(e) {
        dataStr = String(entry.data);
      }
      if (dataStr.length > 500) dataStr = dataStr.substring(0, 500) + "...";

      div.innerHTML =
        '<span class="debug-time">' + timeStr + '</span>' +
        '<span class="debug-type">' + entry.type + '</span>' +
        '<span class="debug-data">' + escapeHtml(dataStr) + '</span>';
      debugPanel.appendChild(div);
    });
    debugPanel.scrollTop = debugPanel.scrollHeight;
  }

  // --- Main Task Runner ---
  function startTask() {
    var task = taskInput.value.trim();
    if (!task) return;
    if (agent && agent.running) return;

    var prompt = promptInput.value.trim();
    var fullTask = task;
    if (prompt) {
      fullTask = task + "\n\nADDITIONAL INSTRUCTIONS (you MUST follow these): " + prompt;
    }

    chatLog.innerHTML = "";
    addMessage("user-task", "Task: " + task);
    if (prompt) {
      addMessage("thinking", "🧠 Prompt: " + prompt.substring(0, 100) + (prompt.length > 100 ? "..." : ""));
    }

    chrome.storage.sync.get(["provider", "apiKey", "model", "customModel", "baseUrl", "maxSteps"], function(settings) {
      if (!settings.apiKey && settings.provider !== "ollama") {
        addMessage("error", "No API key configured. Click ⚙️ to set up.");
        return;
      }

      // Custom model overrides dropdown
      var effectiveModel = (settings.customModel && settings.customModel.trim()) || settings.model;

      var adapter;
      if (settings.provider === "anthropic") {
        adapter = new AnthropicAdapter({
          apiKey: settings.apiKey,
          model: effectiveModel || "claude-sonnet-4-20250514"
        });
      } else {
        adapter = new OpenAIAdapter({
          apiKey: settings.apiKey,
          model: effectiveModel || "gpt-4o",
          baseUrl: settings.baseUrl || OpenAIAdapter.getBaseUrl(settings.provider),
          provider: settings.provider || "openai"
        });
      }

      addMessage("thinking", "Using " + effectiveModel + " via " + (settings.provider || "openai"));

      agent = new WattBotAgent(adapter, {
        maxSteps: settings.maxSteps || 100,
        useScreenshots: chkScreenshots.checked,
        onEvent: handleEvent
      });

      setRunning(true);
      agent.run(fullTask);

      if (debugInterval) clearInterval(debugInterval);
      debugInterval = setInterval(function() {
        if (document.getElementById("view-debug").classList.contains("active")) {
          refreshDebug();
        }
      }, 1000);
    });
  }

  var currentTask = "";

  function handleEvent(type, data) {
    switch (type) {
      case "started":
        currentTask = data.task;
        break;

      case "status":
        statusBar.textContent = "Step " + data.step + " — " + data.message;
        addMessage("thinking", data.message);
        break;

      case "action":
        var act = data.action;
        var detail = "";
        if (act.action === "click") detail = "Target: " + act.params.id;
        else if (act.action === "type") detail = 'Text: "' + act.params.text + '" → ' + act.params.id;
        else if (act.action === "scroll") detail = "Direction: " + act.params.direction;
        else if (act.action === "navigate") detail = act.params.url;
        else if (act.action === "hover") detail = "Target: " + act.params.id;
        else if (act.action === "keypress") detail = "Key: " + act.params.key;
        else if (act.action === "copy") detail = act.params.id ? "From: " + act.params.id : "Text copied";
        else if (act.action === "tab_open") detail = act.params.url || "New tab";
        else if (act.action === "tab_switch") detail = "Index: " + (act.params.index !== undefined ? act.params.index : act.params.tabId);
        else if (act.action === "tab_list") detail = "Listing tabs";
        else if (act.action === "tab_close") detail = "Closing tab";
        else if (act.action === "wait") detail = act.params.ms + "ms";
        else detail = JSON.stringify(act.params);

        addMessage("action",
          '<span class="action-type">' + act.action + '</span>' +
          '<span class="action-detail">' + escapeHtml(detail) + '</span>' +
          (act.reasoning ? '<br><span class="action-detail" style="color:#484f58">' + escapeHtml(act.reasoning) + '</span>' : "")
        );
        break;

      case "done":
        addMessage("done",
          '<span class="done-label">✅ Task Complete</span>' +
          escapeHtml(data.result || "")
        );
        statusBar.textContent = data.steps + " steps · ~" + (data.tokens || 0) + " tokens · ~$" + (data.cost || 0).toFixed(4);
        setRunning(false);
        saveToHistory(currentTask, data.steps, data.tokens, data.cost, true);
        if (agent) persistedDebugLog = agent.getDebugLog().slice();
        if (debugInterval) clearInterval(debugInterval);
        refreshDebug();
        break;

      case "error":
        addMessage("error", "⚠️ " + (data.message || "Unknown error"));
        if (!agent || !agent.running) {
          setRunning(false);
          saveToHistory(currentTask, agent ? agent.stepCount : 0, 0, 0, false);
          if (debugInterval) clearInterval(debugInterval);
        }
        break;

      case "blocked":
        addMessage("blocked", "🚫 Blocked: " + (data.reason || "") + " — " + JSON.stringify(data.action));
        break;

      case "confirm_request":
        confirmCallback = data.resolve;
        confirmReason.textContent = data.reason || "This action needs your approval.";
        confirmAction.textContent = JSON.stringify(data.action, null, 2);
        confirmOverlay.classList.add("visible");
        break;
    }
  }

  // --- Helpers ---
  function setRunning(isRunning) {
    btnRun.style.display = isRunning ? "none" : "";
    btnStop.style.display = isRunning ? "" : "none";
    btnPause.style.display = isRunning ? "" : "none";
    btnPause.textContent = "⏸";
    taskInput.disabled = isRunning;
    if (!isRunning) taskInput.focus();
  }

  function addMessage(type, html) {
    if (type !== "thinking") {
      chatLog.querySelectorAll(".msg.thinking").forEach(function(el) { el.remove(); });
    }
    var div = document.createElement("div");
    div.className = "msg " + type;
    div.innerHTML = html;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function escapeHtml(text) {
    var d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }
})();

/* Resize handle — drag to resize input area */
(function() {
  var handle = document.getElementById('resizeHandle');
  var taskInput = document.getElementById('taskInput');
  var promptInput = document.getElementById('promptInput');
  var promptBody = document.getElementById('promptBody');
  var dragging = false;
  var startY = 0;
  var startTaskH = 0;
  var startPromptH = 0;

  handle.addEventListener('mousedown', function(e) {
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startTaskH = taskInput.offsetHeight;
    startPromptH = (promptBody.style.display !== 'none') ? promptInput.offsetHeight : 0;
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    var delta = startY - e.clientY; // positive = dragging up = bigger
    var newTaskH = Math.max(36, Math.min(300, startTaskH + delta * 0.6));
    taskInput.style.height = newTaskH + 'px';
    if (promptBody.style.display !== 'none' && startPromptH > 0) {
      var newPromptH = Math.max(50, Math.min(200, startPromptH + delta * 0.4));
      promptInput.style.height = newPromptH + 'px';
    }
  });

  document.addEventListener('mouseup', function() {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

