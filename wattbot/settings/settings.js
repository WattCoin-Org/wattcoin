// WattBot Settings v0.3.0 — external JS (MV3 requires no inline scripts)

var providerEl = document.getElementById("provider");
var apikeyEl = document.getElementById("apikey");
var baseurlEl = document.getElementById("baseurl");
var modelEl = document.getElementById("model");
var customModelEl = document.getElementById("custom-model");
var fieldBaseurl = document.getElementById("field-baseurl");
var apikeyHelp = document.getElementById("apikey-help");
var statusDiv = document.getElementById("status");
var maxStepsEl = document.getElementById("max-steps");
var walletAddressEl = document.getElementById("wallet-address");
var walletDot = document.getElementById("wallet-dot");
var walletStatusText = document.getElementById("wallet-status-text");

var PROVIDERS = {
  openai: {
    placeholder: "sk-...",
    help: 'Get your key from <a href="https://platform.openai.com/api-keys" target="_blank">OpenAI Dashboard</a>',
    showBaseUrl: false,
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4-turbo", "o1", "o1-mini", "o3", "o3-mini", "o4-mini"]
  },
  anthropic: {
    placeholder: "sk-ant-...",
    help: 'Get your key from <a href="https://console.anthropic.com/settings/keys" target="_blank">Anthropic Console</a>',
    showBaseUrl: false,
    baseUrl: "https://api.anthropic.com/v1",
    models: ["claude-sonnet-4-20250514", "claude-opus-4-5-20250918", "claude-haiku-4-5-20251001", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
  },
  xai: {
    placeholder: "xai-...",
    help: 'Get your key from <a href="https://console.x.ai/" target="_blank">xAI Console</a>',
    showBaseUrl: false,
    baseUrl: "https://api.x.ai/v1",
    models: ["grok-3", "grok-3-fast", "grok-3-mini", "grok-3-mini-fast", "grok-2", "grok-2-vision"]
  },
  ollama: {
    placeholder: "(leave empty for local)",
    help: 'Make sure <a href="https://ollama.com" target="_blank">Ollama</a> is running on port 11434.',
    showBaseUrl: true,
    baseUrl: "http://localhost:11434/v1",
    models: ["llama3.3", "llama3.3:70b", "llama3.1", "llama3.1:70b", "qwen2.5", "qwen2.5:72b", "mistral", "codellama", "llava", "deepseek-r1", "gemma2"]
  },
  custom: {
    placeholder: "your-api-key",
    help: "Any OpenAI-compatible endpoint (LM Studio, vLLM, etc.)",
    showBaseUrl: true,
    baseUrl: "",
    models: ["default"]
  },
  google: {
    placeholder: "AIza...",
    help: 'Get your key from <a href="https://aistudio.google.com/apikey" target="_blank">Google AI Studio</a>',
    showBaseUrl: false,
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]
  },
  deepseek: {
    placeholder: "sk-...",
    help: 'Get your key from <a href="https://platform.deepseek.com/api_keys" target="_blank">DeepSeek Platform</a>',
    showBaseUrl: false,
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"]
  }
};

function updateUI(savedModel) {
  var provider = providerEl.value;
  var cfg = PROVIDERS[provider];
  if (!cfg) return;

  apikeyEl.placeholder = cfg.placeholder;
  apikeyHelp.innerHTML = cfg.help;

  if (cfg.showBaseUrl) {
    fieldBaseurl.classList.remove("hidden");
    if (!baseurlEl.value) baseurlEl.value = cfg.baseUrl;
  } else {
    fieldBaseurl.classList.add("hidden");
  }

  modelEl.innerHTML = "";
  for (var i = 0; i < cfg.models.length; i++) {
    var opt = document.createElement("option");
    opt.value = cfg.models[i];
    opt.textContent = cfg.models[i];
    modelEl.appendChild(opt);
  }

  if (savedModel && cfg.models.indexOf(savedModel) !== -1) {
    modelEl.value = savedModel;
  }
}

function showStatus(type, message) {
  statusDiv.className = type;
  statusDiv.textContent = message;
  statusDiv.style.display = "block";
  if (type === "success") {
    setTimeout(function() { statusDiv.style.display = "none"; }, 4000);
  }
}

function getEffectiveModel() {
  var custom = customModelEl.value.trim();
  return custom || modelEl.value;
}

function updateWalletStatus() {
  chrome.storage.sync.get(["walletAddress"], function(data) {
    if (data && data.walletAddress) {
      walletDot.className = "wallet-dot connected";
      var addr = data.walletAddress;
      walletStatusText.textContent = addr.substring(0, 6) + "..." + addr.substring(addr.length - 4);
    } else {
      walletDot.className = "wallet-dot disconnected";
      walletStatusText.textContent = "Not connected";
    }
  });
}

// Provider change
providerEl.addEventListener("change", function() {
  baseurlEl.value = "";
  updateUI();
});

// Refresh Models from API
document.getElementById("btn-refresh").addEventListener("click", function() {
  var provider = providerEl.value;
  var apiKey = apikeyEl.value.trim();
  var baseUrl = baseurlEl.value.trim();

  if (provider === "anthropic") {
    showStatus("info", "Anthropic doesn't expose a /models list — use the dropdown or type a model name.");
    return;
  }

  if (!apiKey && provider !== "ollama") {
    showStatus("error", "Enter an API key first to fetch models.");
    return;
  }

  showStatus("info", "Fetching models...");

  var url = baseUrl || (PROVIDERS[provider] ? PROVIDERS[provider].baseUrl : "https://api.openai.com/v1");
  var headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = "Bearer " + apiKey;

  fetch(url + "/models", { headers: headers })
  .then(function(resp) {
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  })
  .then(function(data) {
    var models = (data.data || []).map(function(m) { return m.id; }).sort();
    if (models.length === 0) {
      showStatus("info", "No models returned. Use dropdown or type manually.");
      return;
    }

    // Save current selection
    var current = modelEl.value;

    // Populate dropdown with API models
    modelEl.innerHTML = "";
    models.forEach(function(id) {
      var opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      modelEl.appendChild(opt);
    });

    // Restore selection if still in list
    if (models.indexOf(current) !== -1) {
      modelEl.value = current;
    }

    showStatus("success", "✅ Found " + models.length + " models.");
  })
  .catch(function(e) {
    showStatus("error", "❌ Failed to fetch models: " + e.message);
  });
});

// Load saved settings
chrome.storage.sync.get(["provider", "apiKey", "model", "customModel", "baseUrl", "maxSteps", "walletAddress"], function(data) {
  if (data && data.provider) providerEl.value = data.provider;
  if (data && data.apiKey) apikeyEl.value = data.apiKey;
  if (data && data.baseUrl) baseurlEl.value = data.baseUrl;
  if (data && data.maxSteps) maxStepsEl.value = data.maxSteps;
  if (data && data.customModel) customModelEl.value = data.customModel;
  if (data && data.walletAddress) walletAddressEl.value = data.walletAddress;
  updateUI(data ? data.model : "");
  updateWalletStatus();
});

// Save
document.getElementById("btn-save").addEventListener("click", function() {
  var customModel = customModelEl.value.trim();
  var settings = {
    provider: providerEl.value,
    apiKey: apikeyEl.value.trim(),
    model: modelEl.value,
    customModel: customModel,
    baseUrl: baseurlEl.value.trim(),
    maxSteps: parseInt(maxStepsEl.value) || 100,
    walletAddress: walletAddressEl.value.trim()
  };

  chrome.storage.sync.set(settings, function() {
    if (chrome.runtime.lastError) {
      showStatus("error", "Save failed: " + chrome.runtime.lastError.message);
    } else {
      showStatus("success", "✅ Settings saved!" + (customModel ? " (using custom model: " + customModel + ")" : ""));
      updateWalletStatus();
    }
  });
});

// Test Connection
document.getElementById("btn-test").addEventListener("click", function() {
  var provider = providerEl.value;
  var apiKey = apikeyEl.value.trim();
  var model = getEffectiveModel();
  var baseUrl = baseurlEl.value.trim();

  if (!apiKey && provider !== "ollama") {
    showStatus("error", "❌ Enter an API key first.");
    return;
  }

  showStatus("info", "Testing " + model + "...");

  if (provider === "anthropic") {
    fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true"
      },
      body: JSON.stringify({
        model: model,
        max_tokens: 10,
        messages: [{ role: "user", content: "hi" }]
      })
    })
    .then(function(resp) {
      if (resp.ok) {
        showStatus("success", "✅ Connected! " + model + " is valid.");
      } else {
        return resp.json().then(function(err) {
          showStatus("error", "❌ " + (err.error ? err.error.message : "HTTP " + resp.status));
        });
      }
    })
    .catch(function(e) {
      showStatus("error", "❌ Network error: " + e.message);
    });
  } else {
    var url = baseUrl || (PROVIDERS[provider] ? PROVIDERS[provider].baseUrl : "https://api.openai.com/v1");
    var headers = { "Content-Type": "application/json" };
    if (apiKey) headers["Authorization"] = "Bearer " + apiKey;

    fetch(url + "/chat/completions", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        model: model,
        max_tokens: 10,
        messages: [{ role: "user", content: "hi" }]
      })
    })
    .then(function(resp) {
      if (resp.ok) {
        showStatus("success", "✅ Connected! " + model + " responded.");
      } else {
        return resp.json().then(function(err) {
          var msg = err.error ? (err.error.message || JSON.stringify(err.error)) : "HTTP " + resp.status;
          showStatus("error", "❌ " + msg);
        }).catch(function() {
          showStatus("error", "❌ HTTP " + resp.status);
        });
      }
    })
    .catch(function(e) {
      showStatus("error", "❌ Network error: " + e.message);
    });
  }
});

// Init
updateUI();
updateWalletStatus();
